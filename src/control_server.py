"""
Loopback bridge between the MCP server and this app's UI.

The MCP server is spawned by *FreeClaw*, not by Jarvis, so it is a separate
process with no access to this app's eel connection. When the model calls
`create_time_widget`, that call lands in the MCP process and has to get back
here to reach the browser.

So the Jarvis app listens on 127.0.0.1 and the MCP process POSTs JSON to it:

    POST /call  {"action": "create_time_widget", "args": {...}}
    -> {"ok": true, "result": ...}

Bound to loopback only and gated on a token written to the config file, so
nothing off this machine — and no other user's process — can drive the UI.
The port is written to the config so the MCP server can find it without
being told.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from logging_setup import get_logger

logger = get_logger(__name__)

# Registered by main.py at startup: {action name: callable(**args)}.
_actions = {}
_token = None
_server = None


def register(name, func):
    """Expose `func` to the MCP process under `name`."""
    _actions[name] = func


def register_all(mapping):
    for name, func in mapping.items():
        register(name, func)


def actions():
    return sorted(_actions)


class _Handler(BaseHTTPRequestHandler):
    # BaseHTTPRequestHandler logs every request to stderr by default, which in
    # a windowed app goes nowhere useful and in the MCP process would be noise.
    def log_message(self, fmt, *args):
        logger.debug("control: " + fmt, *args)

    def _reply(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        # A liveness probe, so the MCP server can tell "Jarvis isn't running"
        # from "Jarvis is running but that tool failed" and say so.
        if self.path == "/health":
            self._reply(200, {"ok": True, "actions": actions()})
        else:
            self._reply(404, {"ok": False, "error": "Not found"})

    def do_POST(self):
        if self.path != "/call":
            self._reply(404, {"ok": False, "error": "Not found"})
            return

        if _token and self.headers.get("X-Jarvis-Token") != _token:
            self._reply(401, {"ok": False, "error": "Bad control token"})
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, TypeError):
            self._reply(400, {"ok": False, "error": "Malformed JSON"})
            return

        action = data.get("action")
        args = data.get("args") or {}
        if not isinstance(args, dict):
            self._reply(400, {"ok": False, "error": "args must be an object"})
            return

        func = _actions.get(action)
        if func is None:
            self._reply(404, {"ok": False,
                              "error": f"Unknown action '{action}'. "
                                       f"Known: {', '.join(actions())}"})
            return

        try:
            result = func(**args)
        except TypeError as e:
            # Wrong argument names from the model — a usable message beats a 500.
            self._reply(400, {"ok": False, "error": f"Bad arguments for {action}: {e}"})
            return
        except Exception as e:
            logger.exception("Control action '%s' failed", action)
            self._reply(500, {"ok": False, "error": f"{action} failed: {e}"})
            return

        self._reply(200, {"ok": True, "result": result})


def start(port, token):
    """Start the bridge on 127.0.0.1:`port` in a daemon thread.

    Returns the port actually bound. Raises OSError if the port is taken,
    which main.py turns into a visible warning rather than a crash: the UI is
    still perfectly usable without MCP-driven widgets.
    """
    global _server, _token
    _token = token
    _server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    _server.daemon_threads = True
    thread = threading.Thread(target=_server.serve_forever,
                              name="jarvis-control", daemon=True)
    thread.start()
    logger.info("Control bridge listening on 127.0.0.1:%s", port)
    return _server.server_address[1]


def stop():
    if _server is not None:
        _server.shutdown()
