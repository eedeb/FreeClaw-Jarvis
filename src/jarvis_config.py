"""
Jarvis configuration — how to reach FreeClaw, plus UI preferences.

Stored as JSON next to the executable (or next to this file when run from
source), in the same place the original build kept cache/config.json. The
FreeClaw password is held in plain text here: it is a local-machine file, and
FreeClaw's own .env stores the same secret the same way.
"""

import json
import os
import threading

from resource_path import get_user_data_dir

CONFIG_NAME = "jarvis_config.json"

# The FreeClaw user whose memory, conversation and MCP switches this app drives.
DEFAULT_FC_USER = "Jarvis"

# Loopback-only bridge the MCP server posts to so its tools can drive this UI.
DEFAULT_CONTROL_PORT = 8771

# Every key the app persists has to appear here: load() drops anything it does
# not recognise, so a key missing from this table silently fails to round-trip.
DEFAULTS = {
    "freeclaw_url": "http://127.0.0.1:6767",
    "freeclaw_password": "",
    "freeclaw_user": DEFAULT_FC_USER,
    "assistant_name": "JARVIS",
    "do_not_disturb": False,
    "voice": "en-GB-RyanNeural",
    "control_port": DEFAULT_CONTROL_PORT,
    # Voice input — see listen.py. Off automatically whenever Do Not Disturb
    # is on; this is the separate "should it ever come on at all" switch,
    # e.g. for a machine with no microphone worth listening on.
    "hotword_enabled": True,
    "wake_model": "hey_jarvis",
    "stt_model_size": "tiny.en",
    # None/null = the system's default input device. A specific device can be
    # set here (sounddevice's index or name) if the wrong mic gets picked up.
    "mic_device": None,
    # Shared secret for the loopback control bridge. Minted on first run and
    # then kept: the MCP server reads it from this file, and a token that
    # changed on every start would leave that long-lived process holding a
    # stale one and every widget call answering 401.
    "control_token": "",
    "configured": False,
}

_lock = threading.Lock()


def config_path():
    return os.path.join(get_user_data_dir(), CONFIG_NAME)


def load():
    """Read the config, filling in any key the file predates."""
    data = dict(DEFAULTS)
    try:
        with open(config_path(), "r", encoding="utf-8") as f:
            saved = json.load(f)
        if isinstance(saved, dict):
            data.update({k: v for k, v in saved.items() if k in DEFAULTS})
    except (OSError, json.JSONDecodeError):
        pass
    return data


def save(data):
    """Write the whole config back, atomically enough for a single-writer app."""
    with _lock:
        path = config_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
    return data


def update(**changes):
    """Merge `changes` into the saved config and return the result."""
    data = load()
    data.update(changes)
    return save(data)


def is_configured():
    """Whether setup has run and left us something to talk to."""
    data = load()
    return bool(data.get("configured") and data.get("freeclaw_password")
                and data.get("freeclaw_url"))
