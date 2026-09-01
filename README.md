# Jarvis (Mark Lite)

The original Mark 5 heads-up display, with FreeClaw behind it instead of a
direct Groq call. Same orb, same floating widgets, same bottom-left line of
speech — different brain, and now a voice to match: say "Hey Jarvis" and talk.

```
  Jarvis app (this repo)                          FreeClaw
  ┌─────────────────────────┐                  ┌──────────────────┐
  │  eel UI       :8080     │                  │                  │
  │  ui/index.html          │   /chat (SSE)    │  user "Jarvis"   │
  │  ui/script.js           │◄────────────────►│  context.md      │
  │  ui/UI.py    (widgets)  │  session cookie  │  providers,      │
  │                         │                  │  memory, search  │
  │  control bridge  :8771  │◄──┐              └────────┬─────────┘
  │  listen.py (mic)        │   │                       │ spawns
  └─────────────────────────┘   │                       ▼
                                 │ HTTP (loopback) jarvis_mcp/server.py
                                 └──────────────── 13 local-only tools
```

Four things are involved. The app talks to FreeClaw over a session-
authenticated SSE stream — not the OpenAI-compatible `/v1` endpoint, which
deliberately hides tool calls; see [Tool-call visibility](#tool-call-visibility)
below. FreeClaw spawns the MCP server as a child; the MCP server talks back to
the app over loopback so its widget tools can reach the live UI; and the app
itself listens to the microphone for "Hey Jarvis," handing whatever follows
straight into the same turn path typing does.

**FreeClaw has to be on this machine.** The chat connection is just an address
and a password, but an MCP server spawned by FreeClaw can only screenshot
*this* screen and draw on *this* UI if it runs here too, and the microphone is
this machine's regardless.

---

## Install

Needs [FreeClaw](https://freeclaw.eedeb.dev) on the same machine, with at
least one provider configured under **Settings → Providers** — Jarvis has
nothing to think with otherwise. Install that first if you haven't:

```powershell
irm https://freeclaw.eedeb.dev/install.ps1 | iex
```

Then Jarvis:

```powershell
irm https://raw.githubusercontent.com/OWNER/REPO/main/install.ps1 | iex
```

No administrator rights, nothing else to install by hand. It clones itself
into `%LOCALAPPDATA%\Jarvis`, fetches a private copy of Python so it never
touches anything else on the machine, installs the dependencies, and connects
to FreeClaw automatically — the password comes straight out of FreeClaw's own
`.env`, since they're on the same machine as the same Windows user, so
there's nothing to type. If FreeClaw isn't installed at all, it says so and
stops rather than installing something with nothing to talk to yet; if
FreeClaw is installed but not running, it finishes everything else and tells
you to run `jarvis-setup` once it's up.

Re-running the installer is the update path — code refreshed, your settings
left alone. Uninstall with `& "$env:LOCALAPPDATA\Jarvis\uninstall.ps1"`.

Once it's running, say "Hey Jarvis" — or edit `src/jarvis_persona.md` and run
`jarvis-setup` to push the change (idempotent, safe to run any time; also
what re-connects Jarvis if FreeClaw's install ever moves).

### Local development

Working from a clone instead of the installer: `python -m venv .venv`,
`pip install -r requirements.txt`, then `python src/setup.py` and
`python src/main.py` (or `Setup.cmd` / `Jarvis.cmd`, which assume that same
`.venv` layout).

## What lives where

| Path | What it is |
|---|---|
| `src/main.py` | The app. eel UI, the turn loop, speech, the control bridge, voice wiring. |
| `src/setup.py` | One-time wiring into FreeClaw. Idempotent. |
| `src/freeclaw_client.py` | Clients for FreeClaw's chat, admin, and streaming-chat APIs. |
| `src/listen.py` | "Hey Jarvis" wake word + local speech-to-text. |
| `src/jarvis_mcp/server.py` | The stdio MCP server FreeClaw spawns. |
| `src/control_server.py` | Loopback bridge so MCP tools can drive the UI. |
| `src/vocalize.py` | Speech out, via edge-tts + pygame. |
| `src/jarvis_persona.md` | Who Jarvis is. Edit this, then re-run setup. |
| `src/jarvis_config.py` | Connection details and UI preferences. |
| `src/ui/` | The original front-end, unchanged but for a few additions/fixes. |
| `src/main_free.py` | The decompiled original entry point. Superseded — kept for reference. |
| `install.ps1` / `uninstall.ps1` | The public installer (`irm ... \| iex`) and its counterpart. |
| `windows/` | `.cmd` shims and the Start Menu icon the installer copies into place. |

## The MCP tools

Everything here has to run on this machine; anything reachable over a network
belongs in its own MCP server pointed at FreeClaw separately.

- `create_file`, `create_folder` — the real filesystem, not FreeClaw's sandbox
- `take_screenshot` — the primary monitor
- `show_text_widget`, `show_notes_widget`, `show_time_widget`,
  `show_timer_widget`, `show_reminder_widget`, `show_alarm_widget`,
  `show_calculator_widget`, `show_image_widget`
- `clear_widgets`, `list_widgets`

## Tool-call visibility

A turn that runs several tools used to look identical to a hung one: FreeClaw's
OpenAI-compatible `/v1/chat/completions` endpoint is one blocking request that
answers only once the whole turn is done, and its streaming mode says as much
— "tools run transparently," assistant text only. For a turn that searches the
web, reads a file and calls a tool or two, that could be a genuinely long wait
with a static "Processing..." the entire time.

Jarvis instead drives the same `/chat` endpoint the FreeClaw web UI itself
runs on (`freeclaw_client.FreeClawChat`), authenticated with a login session
rather than the API's bearer token. That stream narrates the turn as it
happens — which tool is running, what it returned, the reply forming token by
token — and `main.py` turns that into:

- the status line naming each tool as it starts ("Searching the web…",
  "Showing the clock…"), instead of a static "Processing..."
- a small **ACTIVITY** panel logging each step (`→ Searching the web`,
  `✓ Searching the web`), created only if a turn actually calls a tool and
  retired a few seconds after the turn ends
- the reply itself appearing as it streams in, not only once complete

**Bash approvals are declined automatically.** `/chat` runs with a human able
to answer an approval prompt in mind; Jarvis has no such UI, and FreeClaw's
own approval wait is five minutes (`APPROVAL_TIMEOUT` in `src/approvals.py`)
— exactly the kind of silent, unexplained wait this whole feature exists to
get rid of. `FreeClawChat` refuses every prompt the instant it appears, the
same as FreeClaw's own `/v1` already does for a caller with nobody to ask. A
saved always-allow rule for a command still runs without ever hitting this.

## Voice input — "Hey Jarvis"

`src/listen.py` runs three small local models, continuously, for the cost of
a rounding error in CPU time:

- **openWakeWord**'s pretrained `hey_jarvis` model scores every 20ms of
  microphone audio in a fraction of a millisecond — cheap enough to run
  against every frame, all the time, so there is nothing to turn on first.
- **webrtcvad** decides, just as cheaply, the instant the user stops talking
  — the recording ends there, not after a fixed timer.
- **faster-whisper**'s `tiny.en` model, run int8 on CPU, transcribes what was
  said in well under a second once warm.

None of it reaches a network. Say "Hey Jarvis," the orb turns green-cyan and
listens, say what you want, and it's usually transcribed and on its way to
FreeClaw before you'd have finished typing it. The mic mutes itself for the
whole of the turn that follows — thinking and speaking — so Jarvis can't hear
his own reply, and un-mutes the moment he's done.

Off automatically whenever **Do Not Disturb** is on. `start_listening()` /
`stop_listening()` are exposed for a manual override if the UI ever grows a
mic button; today it doesn't need one. Config in `jarvis_config.json`:
`hotword_enabled`, `wake_model`, `stt_model_size`, `mic_device`.

**Not yet built:** barge-in (interrupting Jarvis mid-reply with a new wake
word) and an audible cue on detection — the orb's colour is the only signal
right now. Both are straightforward additions to `listen.py`'s state machine,
just not done.

## Hard-coded commands

A short, fixed set of exact phrases (`main.py`, `_SHUTDOWN_PHRASES` /
`_CLEAR_PHRASES`) that never reach FreeClaw — checked in `process_text_input`
before a normal turn even starts, so they work immediately whether typed or
spoken, and never wait behind one:

- **"shut down"** (also: "power off", "turn off", "exit", "quit", "goodbye,"
  "that will be all," "go to sleep") — says goodbye and ends the process.
- **"clear the conversation"** (also: "new chat," "start over," "reset the
  conversation") — clears FreeClaw's conversation history for the Jarvis user.
  **History only** — persistent memory saved to `context.md` (anything the
  model has filed away with `add_context`) is untouched, same as the web UI's
  own Reset button.

Matching is exact after normalising (lowercase, trailing punctuation
stripped, a leading "Jarvis," dropped), not a keyword search — "I need to shut
down my computer, any tips?" is an ordinary question, not a command, because
the whole message has to equal one of the phrases above, not merely contain
one.

## Known gaps

- **Screenshots are taken but not always seen.** Whether FreeClaw passes an
  MCP tool's image on to the model depends on the provider and on
  `MAX_IMAGE_B64` in FreeClaw's `src/mcp_client.py` — see
  [FREECLAW-CHANGES.md](FREECLAW-CHANGES.md) for what changed here and what's
  still provider-dependent.
- **Settings-panel features are honest stubs.** API keys, long-term memory,
  Kasa lights, alarms and workspaces return the shapes the front-end expects
  and a message saying where the real thing lives, so the panel renders
  without throwing. Keys are FreeClaw providers now; memory is FreeClaw's
  `context.md`; lights and browsers belong to other MCP servers.

## Changes to the original UI

Four changes in `ui/`, none of them behavioural beyond what's described —
three pre-existing bugs found by driving the UI from a model rather than by
hand, and two small additions this feature needed:

- **Long text was clipped mid-sentence.** The text widget measured its height
  at the text's natural unwrapped width, *then* capped the width — so anything
  long enough to wrap overflowed a box sized for one line. Height is now
  re-measured at the width actually used.
- **`clearAllWidgets()` did not really clear.** It swept the DOM but left
  `WidgetManager.widgets` populated, and `getAllWidgets()` reads that registry
  first — so after clearing, `list_widgets` still reported every widget that
  had just been removed. It now delegates to `WidgetManager.clearAll()`.
- **`closeWidgetById(id)` added.** Closes one widget without disturbing any
  others — what the ACTIVITY panel above uses to retire itself, since
  `clearAllWidgets()` would also take down anything the model is actively
  showing.
- **`startListeningAnimation()` / `stopListeningAnimation()` added**, mirroring
  the existing speaking animation — the orb's green-cyan "listening" state
  while `listen.py` is recording, plus the CSS for it in `style.css`.

## Notes

- Your FreeClaw password is stored in plain text in
  `src/jarvis_config.json`, next to the loopback control token. Both are
  local-machine secrets; FreeClaw's own `.env` holds the same password the
  same way.
- The control bridge binds 127.0.0.1 only and requires the token.
- Logs: `src/logs/jarvis.log`. The MCP server logs to stderr, which FreeClaw
  drains into its own debug log.
- See [src/README.md](src/README.md) for how the original was recovered from
  `MarkLite.exe`.
