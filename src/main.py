"""
Jarvis — the Mark Lite shell, thinking with FreeClaw.

The front-end is the original eel UI, untouched. What changed is what sits
behind it: every turn is handed to a FreeClaw user called Jarvis over
FreeClaw's session-authenticated /chat stream (freeclaw_client.FreeClawChat),
and the reply is spoken and shown. Streaming rather than a single blocking
request is what lets the UI show a tool call in progress instead of sitting on
"Processing..." for however long the turn takes — see _run_turn.

Four things are involved:

    this app  ──/chat (SSE)──►  FreeClaw          (the brain)
        │  ▲                       │
        │  │ HTTP on 127.0.0.1     │ spawns as a child
        │  └────────────────── jarvis_mcp          (local-only tools)
        │
        └── mic ──► listen.HotwordListener ──► process_text_input(text)

The MCP server needs to reach back into this UI to draw widgets, which is what
control_server.py is for; the actions it may call are registered at the bottom
of this file. The hotword listener needs to reach the same turn path typing
does, which is why it calls process_text_input() directly rather than going
through eel at all — they're the same process.
"""

import asyncio
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import webbrowser

import eel
import eel.chrome as eel_chrome

# Two console hazards on Windows, both fatal and both avoidable.
#
#   * Under pythonw.exe — which is how Jarvis.cmd starts this, so there is no
#     console window — sys.stdout is None, and every print() in the app would
#     raise AttributeError.
#   * On a normal console it is cp1252, which cannot encode the characters
#     FreeClaw's own messages carry (its "Settings -> Providers" hint uses a
#     real arrow), so printing one would raise UnicodeEncodeError.
#
# Anything worth keeping goes to the log file either way; the console is a
# convenience, and must never be the thing that takes a thread down.
class _NullWriter:
    def write(self, _):
        return 0

    def flush(self):
        pass


for _name in ("stdout", "stderr"):
    _stream = getattr(sys, _name, None)
    if _stream is None:
        setattr(sys, _name, _NullWriter())
        continue
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

# ui/ holds the original UI.py widget back-end, which is imported for the side
# effect of its @eel.expose decorators.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui"))

import jarvis_config
import control_server
import freeclaw_client
import vocalize
from logging_setup import get_logger
from resource_path import resource_path, get_user_data_dir

logger = get_logger(__name__)

import UI  # noqa: E402  (registers the widget tools with eel)
from listen import HotwordListener  # noqa: E402

# The asyncio loop speech runs on, started in its own thread by main(). Speech
# is awaited from eel's worker threads, which have no loop of their own.
speech_loop = None

# The wake-word/STT pipeline. None until main() constructs it (or if it never
# came up — no microphone, missing dependency); every call site here checks
# for that rather than assuming it exists.
listener = None

# Guards a turn against being started twice — the UI lets you hit Enter again
# while the agent is still thinking.
_turn_lock = threading.Lock()
_turn_active = False

# One FreeClawChat per (url, user, password), rebuilt only if the config
# changes underneath it (setup.py run again while the app is up). Reused
# across turns rather than logging in fresh each time — see FreeClawChat.
_chat = None
_chat_key = None
_chat_lock = threading.Lock()


def _get_chat():
    global _chat, _chat_key
    cfg = jarvis_config.load()
    # Order matches FreeClawChat.__init__(url, password, user) — not the
    # order those fields happen to sit in the config file.
    key = (cfg["freeclaw_url"], cfg["freeclaw_password"], cfg["freeclaw_user"])
    with _chat_lock:
        if _chat is None or _chat_key != key:
            _chat = freeclaw_client.FreeClawChat(*key)
            _chat_key = key
        return _chat


# ── UI HELPERS ───────────────────────────────────────────────

def _js(name, *args):
    """Call a JS function if the page has it, swallowing the failure if not.

    The browser can be closed, mid-reload, or (during startup) not yet
    connected. None of those should surface as an error in a background thread.
    """
    try:
        func = getattr(eel, name, None)
        if func is not None:
            func(*args)
    except Exception as e:
        logger.debug("UI call %s failed: %s", name, e)


def show_response(text):
    """Put the assistant's line in the bottom-left panel, as in the original."""
    _js("updateBottomLeftOutput", text)


async def _speech_task(text):
    """Speak `text` with the orb animating for exactly as long as it plays."""
    try:
        _js("startSpeakingAnimation")
        await vocalize.speak(text, voice=jarvis_config.load().get("voice"))
    except Exception:
        logger.exception("Speech task failed")
    finally:
        _js("stopSpeakingAnimation")


def speak_text(text):
    """Speak `text`, returning once it has finished. Safe from any thread.

    Called once per sentence during a reply (see _run_turn) rather than once
    for the whole thing — each call blocks until its own audio actually
    finishes, so back-to-back calls play in order with nothing to cut off.
    vocalize.stop() here is for the cross-turn case: a new turn starting
    while an old one's last sentence is still audible (typed input can start
    one mid-speech; the wake-word path can't, since the mic stays paused
    through a whole turn)."""
    if not text or not text.strip():
        return
    if jarvis_config.load().get("do_not_disturb"):
        return
    if speech_loop is None:
        logger.warning("No speech loop running, skipping speech")
        return
    vocalize.stop()  # cut off whatever was mid-sentence
    future = asyncio.run_coroutine_threadsafe(_speech_task(text), speech_loop)
    try:
        future.result()
    except Exception:
        logger.exception("Speech failed")


# Sentence boundary = terminal punctuation followed by actual whitespace.
# Deliberately not "punctuation at the end of the buffer so far" — the token
# stream pauses there constantly (mid-sentence, an abbreviation, a decimal
# number), and treating that as a real boundary would speak a fragment and
# then have to start a new utterance for what turns out to be the same
# sentence's second half.
_SENTENCE_BOUNDARY_RE = re.compile(r"[.!?]+\s+")


def _split_ready_sentences(buffer):
    """(complete sentences, unfinished remainder) — the remainder is never
    spoken here; it waits for more text or, at the end of the turn, gets
    spoken as whatever's left. See _run_turn."""
    sentences = []
    pos = 0
    for m in _SENTENCE_BOUNDARY_RE.finditer(buffer):
        piece = buffer[pos:m.end()].strip()
        if piece:
            sentences.append(piece)
        pos = m.end()
    return sentences, buffer[pos:]


# ── TOOL-CALL VISIBILITY ─────────────────────────────────────
#
# A turn with several tool calls used to look identical to a hung one: a
# single blocking request, a static "Processing...", and nothing until the
# whole thing finished. FreeClawChat streams the same events the FreeClaw web
# UI itself renders (see freeclaw_client.py), and what follows turns those
# into a running commentary: the status line names each tool as it starts,
# and a small "ACTIVITY" panel keeps a short log of what has happened so far.

# FreeClaw's own built-in tools (src/agent.py), by their exact names.
_BUILTIN_TOOL_LABELS = {
    "search_context": "Checking memory",
    "add_context": "Saving to memory",
    "add_header": "Adding a memory section",
    "read_file": "Reading a file",
    "list_files": "Listing files",
    "create_page": "Publishing a page",
    "create_file": "Creating a file",
    "delete_file": "Deleting a file",
    "add_ping": "Scheduling a reminder",
    "edit_file": "Editing a file",
    "get_image_description": "Looking at the image",
    "get_time": "Checking the time",
    "web_search": "Searching the web",
    "read_web": "Reading a page",
    "open_url": "Opening a page",
    "run_bash_command": "Running a command",
}

# Jarvis's own MCP tools (jarvis_mcp/server.py). FreeClaw exposes them to the
# model as mcp_jarvis_<name> (agent.py: load_mcp_tools sanitizes them as
# mcp_<server>_<tool>) — matched against the part after "mcp_jarvis_".
_JARVIS_MCP_LABELS = {
    "create_file": "Creating a file",
    "create_folder": "Creating a folder",
    "take_screenshot": "Taking a screenshot",
    "show_text_widget": "Showing a note",
    "show_notes_widget": "Opening notes",
    "show_time_widget": "Showing the clock",
    "show_timer_widget": "Starting a timer",
    "show_reminder_widget": "Showing a reminder",
    "show_alarm_widget": "Showing an alarm",
    "show_calculator_widget": "Showing the calculator",
    "show_image_widget": "Showing an image",
    "clear_widgets": "Clearing the display",
    "list_widgets": "Checking the display",
}


def _friendly_tool_label(name):
    """A short, present-tense label for a tool call, fit for a person rather
    than the model. Falls back to a readable guess for a tool this doesn't
    know by name, rather than showing the raw function name (mcp_jarvis_… or
    otherwise) verbatim."""
    name = name or ""
    if name in _BUILTIN_TOOL_LABELS:
        return _BUILTIN_TOOL_LABELS[name]
    if name.startswith("mcp_"):
        rest = name[len("mcp_"):]
        if rest.startswith("jarvis_"):
            label = _JARVIS_MCP_LABELS.get(rest[len("jarvis_"):])
            if label:
                return label
        server, _, tool = rest.partition("_")
        if tool:
            return f"Using {server}: {tool.replace('_', ' ')}"
        return f"Using {server or 'a tool'}"
    return name.replace("_", " ").capitalize() or "Doing something"


# The turn currently narrating itself, if any — a short-lived text widget
# titled ACTIVITY that _run_turn creates on the first tool call of a turn
# (never for a turn with none) and retires a few seconds after the turn ends.
_ACTIVITY_TITLE = "ACTIVITY"
_ACTIVITY_MAX_LINES = 10
_ACTIVITY_CLOSE_DELAY = 3.5
_activity_widget_id = None
_activity_lines = []


def _activity_start():
    global _activity_widget_id, _activity_lines
    _activity_widget_id = None
    _activity_lines = []


def _activity_log(line):
    """Append one line to the turn's activity panel, creating it on first use
    so a turn with no tool calls never puts anything on screen for it."""
    global _activity_widget_id, _activity_lines
    _activity_lines.append(line)
    if len(_activity_lines) > _ACTIVITY_MAX_LINES:
        _activity_lines = _activity_lines[-_ACTIVITY_MAX_LINES:]
    content = "\n".join(_activity_lines)
    try:
        if _activity_widget_id is None:
            _activity_widget_id = UI.create_text_widget(content, title=_ACTIVITY_TITLE)
        else:
            UI.update_widget_content(_activity_widget_id, content)
    except Exception:
        logger.debug("Could not update the activity panel", exc_info=True)


def _activity_close():
    """Retire the turn's activity panel a little after the turn ends, so the
    trail is visible for a moment rather than vanishing the instant the reply
    appears — but doesn't linger and clutter the display."""
    widget_id = _activity_widget_id
    if widget_id is None:
        return

    def _close():
        time.sleep(_ACTIVITY_CLOSE_DELAY)
        _js("closeWidgetById", widget_id)

    threading.Thread(target=_close, name="jarvis-activity-close", daemon=True).start()


# Live token text is throttled rather than pushed to the UI on every chunk —
# a provider can stream in pieces far smaller than a word, and repainting the
# bottom-left line that often is wasted work for no visible benefit.
_PARTIAL_UPDATE_INTERVAL = 0.2
_last_partial_at = 0.0


def _maybe_show_partial(text):
    global _last_partial_at
    now = time.monotonic()
    if now - _last_partial_at < _PARTIAL_UPDATE_INTERVAL:
        return
    _last_partial_at = now
    show_response(text)


# ── THE TURN ─────────────────────────────────────────────────

@eel.expose
def ui_ready():
    """Called by the page once it has loaded. Reports how things stand."""
    cfg = jarvis_config.load()
    if not jarvis_config.is_configured():
        show_response("I am not connected to FreeClaw yet, sir. "
                      "Run setup.py to point me at it.")
        return False
    logger.info("UI ready, talking to %s as '%s'",
                cfg["freeclaw_url"], cfg["freeclaw_user"])
    return True


def _run_turn(message):
    """One full agent turn, off the websocket thread so the UI stays live.

    Streamed rather than a single blocking call — see the module docstring
    and the "TOOL-CALL VISIBILITY" section above. The mic is paused for the
    duration: partly so Jarvis can't hear himself over the speakers during the
    reply, partly because there is nothing useful a second wake word could do
    while a turn is already running (process_text_input would just refuse it).

    Speech is sentence-chunked rather than one call for the whole reply: the
    previous design waited for the entire turn — every tool call, the whole
    reply — before saying a word, which for anything longer than a one-liner
    read as Jarvis having gone silent. Each complete sentence is spoken the
    moment it's formed, while the rest of the reply (and any further tool
    calls) is still streaming in behind it."""
    global _turn_active
    if listener is not None:
        listener.pause()

    text_parts = []
    speech_buffer = ""
    final_reply = None
    _activity_start()

    try:
        chat = _get_chat()
        for event in chat.turn(message):
            etype = event.get("type")

            if etype == "token":
                piece = event.get("text", "")
                text_parts.append(piece)
                _maybe_show_partial("".join(text_parts))
                speech_buffer += piece
                ready, speech_buffer = _split_ready_sentences(speech_buffer)
                for sentence in ready:
                    speak_text(sentence)

            elif etype == "tool_call":
                label = _friendly_tool_label(event.get("name", ""))
                show_response(f"{label}…")
                _activity_log(f"→ {label}")

            elif etype == "tool_result":
                _activity_log(f"✓ {_friendly_tool_label(event.get('name', ''))}")

            elif etype == "tool_throttled":
                label = _friendly_tool_label(event.get("name", ""))
                _activity_log(f"⚠ {label} kept repeating, so I stopped it")

            elif etype == "approval_resolved" and not event.get("approved"):
                _activity_log("✗ Declined a command — no one here to approve it")

            elif etype == "error":
                final_reply = event.get("error") or "Something went wrong, sir."

            elif etype == "stopped":
                final_reply = final_reply or "That was stopped, sir."

            # "intent", "provider", "reasoning", "usage", "done",
            # "approval_request" (already answered by FreeClawChat), and
            # "approval_resolved" with approved=True carry nothing the UI
            # needs to show.

    except freeclaw_client.FreeClawError as e:
        logger.warning("Turn failed: %s", e)
        final_reply = str(e)
    except Exception as e:
        logger.exception("Unexpected failure during turn")
        final_reply = f"Something went wrong reaching FreeClaw: {e}"
    finally:
        _js("hideProcessingAnimation")
        _activity_close()
        with _turn_lock:
            _turn_active = False

    reply = final_reply if final_reply is not None else "".join(text_parts).strip()
    if not reply:
        reply = "I didn't get a response that time, sir."

    show_response(reply)

    if final_reply is not None:
        # Error or stopped — this path never touched the sentence loop above,
        # so none of it has been spoken yet.
        speak_text(reply)
    else:
        # Success: every complete sentence already went out as it formed.
        # What's left is whatever never reached a trailing sentence boundary
        # — a reply with no terminal punctuation, or a short one that arrived
        # in a single piece.
        tail = speech_buffer.strip()
        if tail:
            speak_text(tail)
        elif not text_parts:
            # No tokens at all — a tool-calls-only turn, or a genuinely empty
            # reply — so the fallback message above was never spoken either.
            speak_text(reply)

    if listener is not None:
        listener.resume()


# ── HARD-CODED COMMANDS ──────────────────────────────────────
#
# A short, fixed set of exact phrases that never reach FreeClaw at all —
# these are about the app itself ("turn off", "clear the conversation"), not
# something to ask the model. Checked before the busy/turn-lock guard in
# process_text_input, so they always go through immediately rather than
# waiting behind — or being refused because of — an in-flight turn.
#
# Deliberately whole-message matching after normalising, not a keyword or
# substring search: "I need to shut down my computer, any tips?" must not be
# mistaken for a command to Jarvis himself. A person typing or speaking one of
# these means exactly this and nothing else.

_SHUTDOWN_PHRASES = {
    "shut down", "shut yourself down", "power down", "power off",
    "turn yourself off", "turn off", "shutdown", "exit", "quit", "goodbye",
    "that will be all", "that'll be all", "go to sleep",
}

_CLEAR_PHRASES = {
    "clear the conversation", "clear conversation", "clear our conversation",
    "reset the conversation", "reset conversation", "clear the chat",
    "clear chat", "new conversation", "new chat", "start a new conversation",
    "start a new chat", "start over", "forget this conversation",
    "wipe the conversation",
}


def _normalize_command(text):
    """Fold away the variation a real "hard-coded" match has to tolerate: a
    leading "Jarvis," a person types out of habit but the wake word already
    strips off the spoken version of, letter case, and trailing punctuation
    speech-to-text tends to add."""
    text = text.strip()
    text = re.sub(r"^(hey\s+)?jarvis[,:\s]+", "", text, flags=re.IGNORECASE)
    text = text.strip().lower()
    text = re.sub(r"[.!?]+$", "", text)
    return text.strip()


def _handle_hardcoded_command(message):
    """If `message` is one of the fixed commands above, act on it and return
    True. False means it wasn't one — the caller should proceed with a normal
    FreeClaw turn.

    Each handler owns its own resume() of the listener, the same rule
    process_text_input's docstring lays out for its own early returns: a
    message can only arrive here already paused by the hotword path (see
    listen.py), and nothing else will resume it if a handler doesn't."""
    normalized = _normalize_command(message)

    if normalized in _SHUTDOWN_PHRASES:
        threading.Thread(target=_shutdown, name="jarvis-shutdown", daemon=True).start()
        return True

    if normalized in _CLEAR_PHRASES:
        threading.Thread(target=_clear_conversation, name="jarvis-clear", daemon=True).start()
        return True

    return False


_terminate_once = threading.Lock()


def _terminate(reason, say_goodbye=False):
    """End the process, having first stopped everything Jarvis itself owns —
    the microphone and the loopback control bridge — so nothing of Jarvis's
    is left running once this returns. Shared by the "shut down" command and
    by the window being closed (see main()'s close_callback): both mean the
    same thing, just said two different ways.

    Not FreeClaw, and not its MCP server subprocess: that process belongs to
    FreeClaw, which keeps its MCP servers running across the app's own
    lifetime by design (auto-respawned if it dies) — it isn't Jarvis's to
    stop, and doing so would just make FreeClaw start it again on the next
    tool call.

    os._exit() rather than sys.exit(): this can run from a background thread
    (a command) or from eel's own internal thread (the window closing), and a
    plain SystemExit only ends whichever thread raises it — the main thread
    sitting in eel.start() would never notice.

    Every step below is its own try/except, on purpose: os._exit(0) at the
    end is the actual point of this function, and one misbehaving cleanup
    step raising must never be able to leave it unreached — that would trade
    a clean exit for a process that silently keeps running in the
    background, exactly what this exists to prevent.

    Guarded to run once: two independent watchdogs (the app window's process
    exiting, eel's own websocket bookkeeping) can both notice the same close
    within moments of each other."""
    if not _terminate_once.acquire(blocking=False):
        return
    logger.info("Shutting down (%s)", reason)
    if say_goodbye:
        try:
            reply = "Shutting down. Goodbye, sir."
            show_response(reply)
            speak_text(reply)
        except Exception:
            logger.exception("Goodbye message failed")
    if listener is not None:
        try:
            listener.stop()
        except Exception:
            logger.exception("Stopping the listener failed")
    try:
        control_server.stop()
    except Exception:
        logger.exception("Stopping the control bridge failed")
    try:
        vocalize.stop()
    except Exception:
        logger.exception("Stopping playback failed")
    os._exit(0)


def _shutdown():
    """The "shut down" hard-coded command — see _handle_hardcoded_command."""
    _terminate("hard-coded command", say_goodbye=True)


def _clear_conversation():
    """Reset the FreeClaw conversation — history only, not context.md."""
    if listener is not None:
        listener.pause()
    try:
        _get_chat().reset()
        reply = "Done. The conversation is cleared, sir."
    except freeclaw_client.FreeClawError as e:
        logger.warning("Clear conversation failed: %s", e)
        reply = str(e)
    except Exception as e:
        logger.exception("Unexpected failure clearing the conversation")
        reply = f"Something went wrong clearing the conversation: {e}"

    show_response(reply)
    speak_text(reply)
    if listener is not None:
        listener.resume()


@eel.expose
def reset_conversation():
    """The UI's reset button — same effect as saying or typing "clear the
    conversation", just reachable without talking to Jarvis first. Threaded
    for the same reason process_text_input's turns are: this call has to
    return to the browser immediately, not block on the FreeClaw round trip."""
    threading.Thread(target=_clear_conversation, name="jarvis-clear-btn",
                     daemon=True).start()
    return True


@eel.expose
def process_text_input(message):
    """Entry point for anything typed into the UI — or heard: the hotword
    listener calls this too (see _on_wake_transcript), directly rather than
    through eel, since it already runs in this same process. Fire-and-forget
    by design: neither caller waits on it, they watch for the reply to appear.

    Checked against the hard-coded commands first — "shut down", "clear the
    conversation" — before anything about a FreeClaw turn even comes up; see
    the HARD-CODED COMMANDS section above.

    Every early return here that skips _run_turn has to resume the listener
    itself, since _run_turn — the only other thing that does — never starts.
    A message can only reach here from the hotword path already paused mid
    wake-word handling (see listen.py), so leaving one of these paths short
    would leave Jarvis permanently deaf after the first time it was hit."""
    global _turn_active
    message = (message or "").strip()
    if not message:
        return

    if _handle_hardcoded_command(message):
        return

    with _turn_lock:
        if _turn_active:
            show_response("One moment, sir — I am still working on the last one.")
            # Not resumed here: whichever _run_turn is already in flight owns
            # that, and it can only be in flight while the listener was
            # already paused for it — so there's nothing this call disturbed.
            return
        _turn_active = True

    if not jarvis_config.is_configured():
        with _turn_lock:
            _turn_active = False
        show_response("I am not connected to FreeClaw yet, sir. Run setup.py first.")
        if listener is not None:
            listener.resume()
        return

    _js("showProcessingAnimation")
    threading.Thread(target=_run_turn, args=(message,),
                     name="jarvis-turn", daemon=True).start()


# Kept because the original exposed it under this name; the front-end has both
# spellings in different places.
@eel.expose
def process_user_input(user_input):
    return process_text_input(user_input)


@eel.expose
def toggle_chat_mode(enabled=None):
    """The UI's chat-mode switch. Purely a front-end display mode here."""
    return bool(enabled)


# ── SETTINGS THE UI OWNS ─────────────────────────────────────

@eel.expose
def get_assistant_name():
    return jarvis_config.load().get("assistant_name", "JARVIS")


@eel.expose
def set_assistant_name(name):
    name = (name or "").strip()
    if not name:
        return False
    jarvis_config.update(assistant_name=name)
    return True


@eel.expose
def get_do_not_disturb():
    return bool(jarvis_config.load().get("do_not_disturb", False))


@eel.expose
def set_do_not_disturb(enabled):
    enabled = bool(enabled)
    jarvis_config.update(do_not_disturb=enabled)
    if listener is not None:
        # DND means Jarvis stays quiet in both directions: speak_text()
        # already checks the flag before saying anything, and disarming here
        # is the matching half — no point listening for a wake word he isn't
        # allowed to answer.
        if enabled:
            listener.disarm()
        elif jarvis_config.load().get("hotword_enabled", True):
            listener.arm()
    return True


@eel.expose
def start_listening():
    """Manually arm the wake-word listener. Not needed in normal use — it
    arms itself at startup and after Do Not Disturb is turned back off — but
    kept under the original main_free.py names for a future manual control
    (a mic button) to call, and so voice input can be re-armed by hand after
    the model or microphone failed to load the first time this run."""
    if listener is None:
        return False
    listener.arm()
    return True


@eel.expose
def stop_listening():
    """Manually disarm the wake-word listener, independent of Do Not Disturb."""
    if listener is None:
        return False
    listener.disarm()
    return True


# ── FEATURES THAT NOW LIVE IN FREECLAW ───────────────────────
#
# API keys, long-term memory and the rest were Jarvis's own subsystems in the
# original. The brain transplant moved them: keys are FreeClaw providers,
# memory is FreeClaw's context.md, and anything touching the outside world
# (lights, browsers) belongs to whatever MCP server you point FreeClaw at.
#
# These stay exposed and return the shapes the front-end expects, so the
# settings panel renders instead of throwing — they just say where the real
# thing lives rather than pretending to work.

_ELSEWHERE = "Managed by FreeClaw now — see Settings in the FreeClaw web UI."

import json as _json  # noqa: E402  (only these shims need it)


@eel.expose
def get_all_api_keys():
    """Object keyed by service. Empty: LLM keys are FreeClaw providers now."""
    return {}


@eel.expose
def add_api_key(service_name=None, key=None, name=None):
    return {"success": False, "message":
            "Add API keys in FreeClaw under Settings -> Providers."}


@eel.expose
def delete_api_key(service_name=None, key_id=None):
    return {"success": False, "message": _ELSEWHERE}


@eel.expose
def rename_api_key(service_name=None, key_id=None, new_name=None):
    return {"success": False, "message": _ELSEWHERE}


@eel.expose
def check_api_key_availability(service_name=None, key_id=None):
    return {"success": False, "quota_remaining": "Unknown", "message": _ELSEWHERE}


@eel.expose
def get_long_term_memories():
    """JSON string — the front-end parses this one."""
    return _json.dumps([])


@eel.expose
def delete_long_term_memory(memory_id=None):
    return {"success": False, "message":
            "Jarvis's memory is FreeClaw's context.md — edit it there."}


@eel.expose
def get_alarms():
    return _json.dumps([])


@eel.expose
def delete_alarm(alarm_id=None):
    return {"success": False, "message": _ELSEWHERE}


@eel.expose
def get_workspaces():
    return _json.dumps([])


@eel.expose
def save_current_workspace(name=None):
    return {"success": False, "message": "Workspaces are not wired up yet."}


@eel.expose
def restore_workspace(workspace_id=None):
    return {"success": False, "message": "Workspaces are not wired up yet."}


@eel.expose
def delete_workspace(workspace_id=None):
    return {"success": False, "message": "Workspaces are not wired up yet."}


@eel.expose
def get_kasa_devices():
    """Array — the front-end checks Array.isArray on this one."""
    return []


@eel.expose
def discover_kasa_devices():
    return []


@eel.expose
def save_kasa_device(device=None, **kwargs):
    return {"success": False, "message":
            "Smart-home control belongs to a FreeClaw MCP server now."}


@eel.expose
def remove_kasa_device(device_id=None):
    return {"success": False, "message": _ELSEWHERE}


@eel.expose
def control_kasa_device(device_id=None, action=None, **kwargs):
    return {"success": False, "message":
            "Smart-home control belongs to a FreeClaw MCP server now."}


@eel.expose
def test_kasa_device_connection(ip=None, **kwargs):
    return {"success": False, "message": _ELSEWHERE}


@eel.expose
def test_weather_widget():
    """Draws a sample weather widget so the panel's test button does something."""
    return UI.create_weather_widget(
        {"temperature": "72", "condition": "Clear", "location": "Sample"},
        title="WEATHER")


# ── STARTUP ──────────────────────────────────────────────────

def _start_speech_loop():
    """Run an asyncio loop forever in a daemon thread, for speech to live on."""
    global speech_loop
    loop = asyncio.new_event_loop()
    speech_loop = loop

    def runner():
        asyncio.set_event_loop(loop)
        loop.run_forever()

    threading.Thread(target=runner, name="jarvis-speech", daemon=True).start()
    return loop


def _start_control_bridge():
    """Bring up the loopback bridge the MCP server calls into.

    A token is minted on first run and saved, so the MCP server (which reads
    the same config file) can authenticate without being passed a secret on
    its command line, where it would be visible in the process list.
    """
    cfg = jarvis_config.load()
    token = cfg.get("control_token")
    if not token:
        token = secrets.token_urlsafe(24)
        jarvis_config.update(control_token=token)

    port = int(cfg.get("control_port") or jarvis_config.DEFAULT_CONTROL_PORT)

    control_server.register_all({
        # Everything here runs on this machine, in this process, because it
        # has to: these touch the live UI.
        "create_text_widget": UI.create_text_widget,
        "create_notes_widget": UI.create_notes_widget,
        "create_time_widget": UI.create_time_widget,
        "create_timer_widget": UI.create_timer_widget,
        "create_alarm_widget": UI.create_alarm_widget,
        "create_reminder_widget": UI.create_reminder_widget,
        "create_calculator_widget": UI.create_calculator_widget,
        "create_image_widget": UI.create_image_widget,
        "create_weather_widget": UI.create_weather_widget,
        "update_widget_content": UI.update_widget_content,
        "get_all_widgets": UI.get_all_widgets,
        "clear_widgets": lambda: (_js("clearAllWidgets"), "cleared")[1],
    })

    try:
        control_server.start(port, token)
    except OSError as e:
        # Widgets-from-MCP stop working; everything else is fine. Say so and
        # carry on rather than refusing to start.
        logger.error("Control bridge could not bind port %s: %s", port, e)
        print(f"[jarvis] Warning: control bridge port {port} is in use. "
              f"MCP tools that draw widgets will not work.")


def _on_wake_transcript(text):
    """Called on listen.py's own worker thread once "Hey Jarvis" was heard
    and the command after it transcribed. Handing off to process_text_input
    and returning is the whole job — see its docstring for why every path out
    of it has to resume the listener, since this thread won't."""
    process_text_input(text)


def _on_listen_state(state):
    """Mirrors listen.py's state machine onto the display, so hearing the
    wake word is visible the instant it happens rather than only once a
    transcript — which can be a second or more later — comes back."""
    if state == "capturing":
        _js("startListeningAnimation")
        show_response("Yes, sir?")
    elif state == "transcribing":
        _js("stopListeningAnimation")
        _js("showProcessingAnimation")
    elif state == "armed":
        _js("stopListeningAnimation")
        _js("hideProcessingAnimation")
    elif state == "paused":
        _js("stopListeningAnimation")


def _start_listener():
    """Load the wake-word/STT models and open the microphone, off the startup
    path — model loading costs a couple of seconds and there's no reason the
    window shouldn't open first. Arms immediately unless Do Not Disturb is on
    or voice input is switched off in config."""
    cfg = jarvis_config.load()
    if not cfg.get("hotword_enabled", True):
        logger.info("Voice input is disabled in config (hotword_enabled=false)")
        return

    def load_and_arm():
        global listener
        candidate = HotwordListener(
            on_transcript=_on_wake_transcript, on_state=_on_listen_state,
            wake_model=cfg.get("wake_model", "hey_jarvis"),
            stt_model_size=cfg.get("stt_model_size", "tiny.en"),
            device=cfg.get("mic_device"))
        if not candidate.start():
            print("[jarvis] Voice input is unavailable this run "
                  "(no microphone, or a dependency is missing) — type instead.")
            return
        listener = candidate
        if not jarvis_config.load().get("do_not_disturb"):
            listener.arm()

    threading.Thread(target=load_and_arm, name="jarvis-listen-startup", daemon=True).start()


def _on_window_close(page, sockets):
    """eel's close_callback — fires whenever a websocket disconnects, which
    for this app means the window was closed. `sockets` is what's still
    connected, not what just dropped, so this only actually shuts down once
    nothing is — a reload or a momentary reconnect must not kill the app out
    from under itself, even though in practice this UI only ever opens the
    one window.

    In testing this did not reliably fire in the full app the way it does in
    an eel app with nothing else going on — plausibly because eel's gevent
    scheduling was never monkey-patched in (neither eel nor bottle_websocket
    call gevent.monkey.patch_all()), and this app's other, ordinary OS
    threads — the microphone, the control bridge, the speech loop — aren't
    gevent-aware and can starve it. Kept as the fast path for when it does
    fire; _start_close_watchdog below is what actually guarantees the window
    closing ends the process."""
    if sockets:
        return
    _terminate("window closed (close_callback)")


def _start_close_watchdog():
    """Poll eel's own connected-sockets list directly, on a plain thread —
    not dependent on gevent's scheduling at all, unlike _on_window_close
    above. This is the mechanism that's actually guaranteed to notice the
    window closing and end the process; see that function's docstring for
    why the callback alone wasn't enough.

    Waits for a first real connection before it will ever consider shutting
    down — eel._websockets starts empty before the window has even opened,
    and this must not race that. `eel._websockets` is a private attribute,
    so a future eel version is free to rename or drop it; if that ever
    raises, this thread quietly stops rather than crashing the app, leaving
    _on_window_close as the sole (best-effort) mechanism."""
    def watch():
        connected_once = False
        empty_checks = 0
        while True:
            time.sleep(1.5)
            try:
                count = len(eel._websockets)
            except Exception:
                logger.exception("Close watchdog couldn't read eel._websockets")
                return
            if count > 0:
                if not connected_once:
                    logger.debug("Close watchdog: first connection seen")
                connected_once = True
                empty_checks = 0
                continue
            if not connected_once:
                continue
            empty_checks += 1
            if empty_checks >= 2:  # ~3s of nothing connected
                _terminate("window closed (watchdog)")
                return

    threading.Thread(target=watch, name="jarvis-close-watchdog", daemon=True).start()


def _launch_chrome_app(url, profile_dir):
    """Launch the app window ourselves rather than letting eel.start() do it,
    so we keep the Popen handle. eel's own launch-and-forget leaves window-
    close detection entirely to the websocket bookkeeping above, which this
    app has seen fail to notice a real close — most likely a stale entry in
    eel._websockets from gevent's scheduling being starved (see
    _on_window_close's docstring) never getting pruned, so the "any
    connections left?" check never legitimately reaches zero again for the
    rest of that process's life. Watching the actual OS process exit instead
    sidesteps eel/gevent entirely.

    Returns the Popen, or None if Chrome isn't installed (caller falls back
    to the default browser)."""
    path = eel_chrome.find_path()
    if not path:
        return None
    return subprocess.Popen(
        [path, f'--app={url}', '--disable-http-cache', f'--user-data-dir={profile_dir}'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)


def _start_process_watchdog(proc):
    """Block on the app window's own process exiting — a plain OS-level
    signal, true the instant the user closes it regardless of anything eel
    or gevent has or hasn't noticed. The primary close-detection path
    whenever Chrome launched successfully; _on_window_close and
    _start_close_watchdog remain as a best-effort fallback for the case
    where there's no such process to watch (the default-browser path)."""
    def watch():
        proc.wait()
        _terminate("window closed (process exited)")

    threading.Thread(target=watch, name="jarvis-close-process-watchdog", daemon=True).start()


def main():
    """Start the speech loop, the control bridge, voice input, and the UI."""
    if getattr(sys, "frozen", False):
        eel.init(resource_path("ui"))
    else:
        eel.init(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui"))

    _start_speech_loop()
    _start_control_bridge()
    vocalize.warm_up()
    _start_listener()
    _start_close_watchdog()

    if not jarvis_config.is_configured():
        print("[jarvis] Not connected to FreeClaw yet - run setup.py first.")

    # A dedicated profile keeps this launch from being absorbed by an
    # already-running Chrome via its single-instance IPC: without one, when
    # the user has Chrome open for regular browsing, --app is silently
    # ignored and the page opens as an ordinary tab there instead of its own
    # app window.
    chrome_profile_dir = os.path.join(get_user_data_dir(), "chrome-profile")
    os.makedirs(chrome_profile_dir, exist_ok=True)

    # Launched ourselves (mode=None below) rather than via eel's mode='chrome'
    # so we keep the process handle — see _launch_chrome_app / _start_process_watchdog.
    chrome_proc = _launch_chrome_app('http://localhost:8080/index.html', chrome_profile_dir)
    if chrome_proc is not None:
        _start_process_watchdog(chrome_proc)
    else:
        logger.warning("Chrome not found, falling back to the default browser")
        print("[jarvis] Chrome not found - opening in your default browser.")
        webbrowser.open('http://localhost:8080/index.html')

    try:
        eel.start('index.html', size=(1200, 800), port=8080, mode=None,
                  block=True, close_callback=_on_window_close)
    except (SystemExit, KeyboardInterrupt):
        pass
    except Exception as e:
        logger.exception("Application failed to start")
        print(f"Error starting application: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
