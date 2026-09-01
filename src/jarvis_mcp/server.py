"""
Jarvis's MCP server — the things that can only happen on this machine.

FreeClaw already has files (sandboxed to its own static folder), the web,
bash and memory. What it cannot do from where it sits is touch the wider
filesystem, see the screen, or draw on the Jarvis UI. That is all this server
adds; anything reachable over a network belongs in its own MCP server rather
than here.

Transport is stdio, spawned by FreeClaw as a child process: newline-delimited
JSON-RPC 2.0 on stdin/stdout. **Nothing may ever be printed to stdout** except
protocol messages — logging goes to stderr, which FreeClaw drains into its
debug log.

Widget tools cannot draw anything themselves: this is a different process from
the running UI. They POST to the Jarvis app's loopback control bridge
(control_server.py), which holds the live eel connection.
"""

import argparse
import base64
import json
import os
import sys
import traceback

# The app's modules live one level up; this process is spawned by FreeClaw
# from FreeClaw's own working directory, so nothing on sys.path can be assumed.
SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import requests  # noqa: E402

PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "jarvis", "version": "1.0.0"}

# Where screenshots are written. Set from the config at startup.
SCREENSHOT_DIR = None
CONTROL_URL = None
CONTROL_TOKEN = None


# stdout stays as it is: json.dumps escapes non-ASCII, so the protocol channel
# is pure ASCII by construction. stderr carries arbitrary text (paths, error
# messages) and would otherwise raise UnicodeEncodeError on a cp1252 console.
try:
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass


def log(message):
    """Diagnostics go to stderr — stdout is the protocol channel."""
    print(f"[jarvis-mcp] {message}", file=sys.stderr, flush=True)


# ── THE BRIDGE BACK TO THE UI ────────────────────────────────

def call_ui(action, **args):
    """Ask the running Jarvis app to do something. Returns its result.

    Raises ToolError with a sentence the model can act on, because "Jarvis
    isn't running" and "that widget call failed" need different responses.
    """
    try:
        resp = requests.post(
            f"{CONTROL_URL}/call",
            headers={"X-Jarvis-Token": CONTROL_TOKEN or ""},
            json={"action": action, "args": args},
            timeout=(3, 30),
        )
    except requests.exceptions.ConnectionError:
        raise ToolError(
            "The Jarvis window isn't open, so there's nothing to draw on. "
            "Ask the user to start Jarvis and try again.")
    except requests.RequestException as e:
        raise ToolError(f"Couldn't reach the Jarvis UI: {e}")

    if resp.status_code == 401:
        raise ToolError("The Jarvis UI rejected this server's control token. "
                        "Re-run Jarvis setup to reissue it.")
    try:
        data = resp.json()
    except ValueError:
        raise ToolError(f"The Jarvis UI returned something unreadable "
                        f"({resp.status_code}).")
    if not data.get("ok"):
        raise ToolError(data.get("error") or "The Jarvis UI refused that call.")
    return data.get("result")


class ToolError(Exception):
    """A failure worth telling the model about in words."""


# ── TOOLS ────────────────────────────────────────────────────

def _expand(path):
    """Resolve a user-supplied path the way a person means it."""
    if not path or not str(path).strip():
        raise ToolError("A path is required.")
    return os.path.abspath(os.path.expandvars(os.path.expanduser(str(path))))


def tool_create_file(path, content="", overwrite=False):
    """Write a file anywhere on this machine, making parent folders as needed."""
    target = _expand(path)
    if os.path.isdir(target):
        raise ToolError(f"{target} is a folder, not a file.")
    if os.path.exists(target) and not overwrite:
        raise ToolError(
            f"{target} already exists. Pass overwrite=true to replace it.")
    parent = os.path.dirname(target)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(target, "w", encoding="utf-8", newline="") as f:
        f.write(content or "")
    return f"Wrote {len(content or '')} characters to {target}"


def tool_create_folder(path):
    """Create a folder (and any missing parents) anywhere on this machine."""
    target = _expand(path)
    if os.path.isfile(target):
        raise ToolError(f"{target} already exists as a file.")
    existed = os.path.isdir(target)
    os.makedirs(target, exist_ok=True)
    return f"{target} already existed." if existed else f"Created {target}"


# A full-resolution screenshot is ~1.7 MB of base64, which is a lot to push
# down a line-buffered pipe on every call and more detail than a vision model
# uses. The saved PNG stays full size; only the inline copy is scaled.
INLINE_MAX_WIDTH = 1280


def tool_take_screenshot(filename=None):
    """Capture the primary monitor and return it as an image block."""
    try:
        import mss
        import mss.tools
    except ImportError:
        raise ToolError("Screenshots need the 'mss' package, which isn't installed "
                        "in the Python running this MCP server.")

    name = (filename or "screenshot").strip() or "screenshot"
    if not name.lower().endswith(".png"):
        name += ".png"
    name = os.path.basename(name)

    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    target = os.path.join(SCREENSHOT_DIR, name)

    try:
        # mss.mss() is deprecated in mss 10; MSS is the current spelling, but
        # fall back so an older install still works.
        capture = getattr(mss, "MSS", None) or mss.mss
        with capture() as sct:
            # monitors[0] is the union of every display; [1] is the primary one,
            # which is what "my screen" means to a person with two of them.
            shot = sct.grab(sct.monitors[1])
            size = (shot.width, shot.height)
            mss.tools.to_png(shot.rgb, shot.size, output=target)
    except Exception as e:
        raise ToolError(f"Couldn't capture the screen: {e}")

    encoded, mime = _inline_copy(target)

    # Both blocks on purpose. The image block is what the MCP spec says a
    # screenshot is; FreeClaw's client currently flattens results to text and
    # drops it, so the text block is what actually survives today. When
    # FreeClaw learns to pass images through, this tool already works.
    blocks = []
    if encoded:
        blocks.append({"type": "image", "data": encoded, "mimeType": mime})
    blocks.append({
        "type": "text",
        "text": f"Screenshot saved to {target} ({size[0]}x{size[1]}).",
    })
    return blocks


def _inline_copy(path):
    """(base64, mime) of `path`, scaled and re-encoded for transport.

    The file on disk stays a lossless full-size PNG. This copy exists only to
    travel down a pipe to a vision model, where a scaled JPEG is a tenth the
    size and indistinguishable in use. Returns (None, None) if it can't be read.
    """
    try:
        import io

        from PIL import Image
    except ImportError:
        # No Pillow: send the PNG as-is rather than nothing.
        try:
            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode("ascii"), "image/png"
        except OSError as e:
            log(f"Couldn't read the screenshot: {e}")
            return None, None

    try:
        with Image.open(path) as img:
            img = img.convert("RGB")
            if img.width > INLINE_MAX_WIDTH:
                height = round(img.height * INLINE_MAX_WIDTH / img.width)
                img = img.resize((INLINE_MAX_WIDTH, height), Image.LANCZOS)
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=80, optimize=True)
        return base64.b64encode(buffer.getvalue()).decode("ascii"), "image/jpeg"
    except Exception as e:
        log(f"Couldn't inline the screenshot: {e}")
        return None, None


def tool_show_text_widget(text, title="INFORMATION"):
    call_ui("create_text_widget", text=text, title=title)
    return f"Showed a '{title}' widget on the Jarvis display."


def tool_show_notes_widget(title="NOTES", initial_text=""):
    call_ui("create_notes_widget", title=title, initial_text=initial_text)
    return f"Showed a '{title}' notes widget on the Jarvis display."


def tool_show_time_widget(military_time=False):
    call_ui("create_time_widget", military_time=bool(military_time))
    return "Showed the clock on the Jarvis display."


def tool_show_timer_widget(duration_seconds):
    try:
        seconds = int(duration_seconds)
    except (TypeError, ValueError):
        raise ToolError("duration_seconds must be a whole number of seconds.")
    if seconds <= 0:
        raise ToolError("A timer needs a positive number of seconds.")
    call_ui("create_timer_widget", duration_seconds=seconds)
    return f"Started a {seconds}-second timer on the Jarvis display."


def tool_show_reminder_widget(label):
    if not (label or "").strip():
        raise ToolError("A reminder needs something to say.")
    call_ui("create_reminder_widget", label=label)
    return f"Showed a reminder: {label}"


def tool_show_alarm_widget(label):
    if not (label or "").strip():
        raise ToolError("An alarm needs a label.")
    call_ui("create_alarm_widget", label=label)
    return f"Showed an alarm: {label}"


def tool_show_calculator_widget():
    call_ui("create_calculator_widget")
    return "Showed the calculator on the Jarvis display."


def tool_show_image_widget(image_path, title="IMAGE"):
    target = _expand(image_path)
    if not os.path.isfile(target):
        raise ToolError(f"There's no file at {target}.")
    call_ui("create_image_widget", image_path=target, title=title)
    return f"Showed {os.path.basename(target)} on the Jarvis display."


def tool_clear_widgets():
    call_ui("clear_widgets")
    return "Cleared the Jarvis display."


def tool_list_widgets():
    widgets = call_ui("get_all_widgets")
    if not widgets:
        return "Nothing is on the Jarvis display right now."
    return json.dumps(widgets, indent=2, default=str)


# name -> (handler, description, JSON-Schema properties, required)
TOOLS = {
    "create_file": (
        tool_create_file,
        "Create or overwrite a file anywhere on the user's computer. Parent "
        "folders are created automatically. Use this rather than FreeClaw's "
        "own create_file when the user means a real path on their machine.",
        {"path": {"type": "string",
                  "description": "Absolute or ~-relative path to write."},
         "content": {"type": "string", "description": "Text to write."},
         "overwrite": {"type": "boolean",
                       "description": "Replace the file if it already exists."}},
        ["path"],
    ),
    "create_folder": (
        tool_create_folder,
        "Create a folder anywhere on the user's computer, including any "
        "missing parent folders.",
        {"path": {"type": "string", "description": "Folder path to create."}},
        ["path"],
    ),
    "take_screenshot": (
        tool_take_screenshot,
        "Capture what is currently on the user's primary monitor.",
        {"filename": {"type": "string",
                      "description": "Optional name for the saved PNG."}},
        [],
    ),
    "show_text_widget": (
        tool_show_text_widget,
        "Display a panel of text on the Jarvis heads-up display.",
        {"text": {"type": "string", "description": "Body text to show."},
         "title": {"type": "string", "description": "Panel heading."}},
        ["text"],
    ),
    "show_notes_widget": (
        tool_show_notes_widget,
        "Display an editable notes panel on the Jarvis display.",
        {"title": {"type": "string", "description": "Panel heading."},
         "initial_text": {"type": "string", "description": "Starting contents."}},
        [],
    ),
    "show_time_widget": (
        tool_show_time_widget,
        "Show a live clock on the Jarvis display.",
        {"military_time": {"type": "boolean",
                           "description": "True for 24-hour, false for AM/PM."}},
        [],
    ),
    "show_timer_widget": (
        tool_show_timer_widget,
        "Start a visible countdown timer on the Jarvis display.",
        {"duration_seconds": {"type": "integer",
                              "description": "How long to count down, in seconds."}},
        ["duration_seconds"],
    ),
    "show_reminder_widget": (
        tool_show_reminder_widget,
        "Pin a reminder on the Jarvis display.",
        {"label": {"type": "string", "description": "What to be reminded of."}},
        ["label"],
    ),
    "show_alarm_widget": (
        tool_show_alarm_widget,
        "Show an alarm on the Jarvis display.",
        {"label": {"type": "string", "description": "What the alarm is for."}},
        ["label"],
    ),
    "show_calculator_widget": (
        tool_show_calculator_widget,
        "Put a calculator on the Jarvis display.",
        {}, [],
    ),
    "show_image_widget": (
        tool_show_image_widget,
        "Display an image file from this computer on the Jarvis display.",
        {"image_path": {"type": "string", "description": "Path to the image."},
         "title": {"type": "string", "description": "Panel heading."}},
        ["image_path"],
    ),
    "clear_widgets": (
        tool_clear_widgets,
        "Remove every panel from the Jarvis display.",
        {}, [],
    ),
    "list_widgets": (
        tool_list_widgets,
        "List what is currently on the Jarvis display.",
        {}, [],
    ),
}


def tools_schema():
    return [
        {"name": name,
         "description": desc,
         "inputSchema": {"type": "object", "properties": props,
                         "required": required}}
        for name, (_, desc, props, required) in TOOLS.items()
    ]


# ── JSON-RPC PLUMBING ────────────────────────────────────────

def _result(request_id, payload):
    return {"jsonrpc": "2.0", "id": request_id, "result": payload}


def _error(request_id, code, message):
    return {"jsonrpc": "2.0", "id": request_id,
            "error": {"code": code, "message": message}}


def _content(value):
    """Normalise a handler's return into MCP content blocks."""
    if isinstance(value, list):
        return value
    return [{"type": "text", "text": str(value)}]


def handle(message):
    """Handle one JSON-RPC message. Returns a reply, or None for notifications."""
    method = message.get("method")
    request_id = message.get("id")

    # Notifications carry no id and must never be answered.
    if request_id is None:
        return None

    if method == "initialize":
        return _result(request_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
        })

    if method == "ping":
        return _result(request_id, {})

    if method == "tools/list":
        return _result(request_id, {"tools": tools_schema()})

    if method == "tools/call":
        params = message.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        entry = TOOLS.get(name)
        if entry is None:
            return _error(request_id, -32602, f"No such tool: {name}")
        handler = entry[0]
        try:
            value = handler(**args)
        except ToolError as e:
            # A tool failing is a normal outcome the model should read and act
            # on, so it comes back as content with isError rather than as a
            # protocol-level error.
            return _result(request_id,
                           {"content": [{"type": "text", "text": str(e)}],
                            "isError": True})
        except TypeError as e:
            return _result(request_id,
                           {"content": [{"type": "text",
                                         "text": f"Bad arguments for {name}: {e}"}],
                            "isError": True})
        except Exception as e:
            log(f"Tool {name} crashed: {traceback.format_exc()}")
            return _result(request_id,
                           {"content": [{"type": "text",
                                         "text": f"{name} failed: {e}"}],
                            "isError": True})
        return _result(request_id, {"content": _content(value)})

    return _error(request_id, -32601, f"Method not found: {method}")


def load_settings(config_path):
    """Work out where the UI bridge is and where screenshots go."""
    global CONTROL_URL, CONTROL_TOKEN, SCREENSHOT_DIR

    data = {}
    if config_path and os.path.isfile(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
        except (OSError, json.JSONDecodeError) as e:
            log(f"Couldn't read config at {config_path}: {e}")
    else:
        log(f"No config at {config_path}; using defaults.")

    port = data.get("control_port") or 8771
    CONTROL_URL = f"http://127.0.0.1:{port}"
    CONTROL_TOKEN = data.get("control_token") or ""
    SCREENSHOT_DIR = os.path.join(
        os.path.dirname(config_path) if config_path else SRC_DIR, "screenshots")


def main():
    parser = argparse.ArgumentParser(description="Jarvis MCP server (stdio)")
    parser.add_argument("--config", default=os.path.join(SRC_DIR, "jarvis_config.json"),
                        help="Path to jarvis_config.json")
    args = parser.parse_args()

    load_settings(args.config)
    log(f"Ready. UI bridge at {CONTROL_URL}, {len(TOOLS)} tools.")

    # Line-delimited JSON both ways. Reading line by line matches how FreeClaw
    # writes; flushing every reply matters because the parent blocks on it.
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            log(f"Ignoring unparseable line: {line[:200]}")
            continue

        try:
            reply = handle(message)
        except Exception:
            log(f"Handler crashed: {traceback.format_exc()}")
            reply = _error(message.get("id"), -32603, "Internal server error")

        if reply is not None:
            sys.stdout.write(json.dumps(reply) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
