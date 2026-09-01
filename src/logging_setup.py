"""
Central logger for Jarvis.

Everything goes to logs/jarvis.log next to the user data directory, so a
failure inside a background thread (speech, the control server, an MCP call)
leaves a traceback somewhere findable instead of vanishing into a dead
console. The MCP server must never write to stdout — that channel carries
JSON-RPC — so file-only is the default and stderr is opt-in.
"""

import logging
import os

from resource_path import get_user_data_dir

_configured = False


def _log_path():
    log_dir = os.path.join(get_user_data_dir(), "logs")
    os.makedirs(log_dir, exist_ok=True)
    return os.path.join(log_dir, "jarvis.log")


def _configure():
    global _configured
    if _configured:
        return
    root = logging.getLogger("jarvis")
    root.setLevel(logging.INFO)
    root.propagate = False
    try:
        handler = logging.FileHandler(_log_path(), encoding="utf-8")
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
        root.addHandler(handler)
    except OSError:
        # An unwritable log directory must not stop the app booting.
        root.addHandler(logging.NullHandler())
    _configured = True


def get_logger(name):
    _configure()
    return logging.getLogger("jarvis").getChild(name)
