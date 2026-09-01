"""
One-time setup: point Jarvis at a FreeClaw install and wire the two together.

Needs nothing typed in the common case — Jarvis and FreeClaw on the same
machine, FreeClaw already installed and running. It will:

  1. find the local FreeClaw install
  2. log in, reading the password straight out of FreeClaw's own .env —
     the same machine, the same Windows user, no prompt needed
  3. create the FreeClaw user "Jarvis" (or reuse the existing one)
  4. write the Jarvis persona into that user's context.md
  5. save the connection details for the app to use
  6. register this project's MCP server with FreeClaw, over stdio
  7. switch FreeClaw's OpenAI-compatible API on, which is what Jarvis talks to

Run it again any time — it is idempotent, and re-running is how you push an
edited persona back into FreeClaw, or pick up a FreeClaw that moved.

    python setup.py
    python setup.py --url http://127.0.0.1:6767 --password hunter2

Only the address and password can be overridden; everything else about the
connection is automatic. Writing the persona by hand rather than through an
API is the one thing here that actually requires FreeClaw to be on this
machine — but that is a requirement regardless, since an MCP server FreeClaw
spawns can only screenshot the screen and draw widgets if it runs beside them.
"""

import argparse
import getpass
import json
import os
import secrets
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import freeclaw_client as fc
import jarvis_config

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
PERSONA_PATH = os.path.join(SRC_DIR, "jarvis_persona.md")
MCP_SERVER = os.path.join(SRC_DIR, "jarvis_mcp", "server.py")
MCP_NAME = "jarvis"

# Where a Windows FreeClaw install puts itself. Checked first, then asked for.
DEFAULT_FC_HOME = os.path.join(
    os.environ.get("LOCALAPPDATA", ""), "FreeClaw")


def say(message=""):
    print(message, flush=True)


def step(n, message):
    say(f"  [{n}] {message}")


# ── LOCATING THINGS ──────────────────────────────────────────

def find_freeclaw_home(given=None):
    """The FreeClaw install directory, so context.md can be written."""
    candidates = [given, DEFAULT_FC_HOME,
                  os.path.join(os.path.expanduser("~"), "FreeClaw"),
                  os.path.join(os.path.expanduser("~"), "freeclaw")]
    for path in candidates:
        if path and os.path.isdir(os.path.join(path, "Flask", "static")):
            return path
    return None


def python_for_mcp():
    """The interpreter FreeClaw should spawn the MCP server with.

    Must be one that has this project's dependencies (mss, Pillow, requests)
    — so the project venv if there is one, and whatever is running setup
    otherwise. FreeClaw's own bundled Python has none of them.
    """
    venv = os.path.join(os.path.dirname(SRC_DIR), ".venv", "Scripts", "python.exe")
    if os.path.isfile(venv):
        return venv
    venv_posix = os.path.join(os.path.dirname(SRC_DIR), ".venv", "bin", "python")
    if os.path.isfile(venv_posix):
        return venv_posix
    return sys.executable


def mcp_command(config_path):
    """The command line FreeClaw will run.

    Two constraints shape this, both from how FreeClaw stores the command:

    * **Double quotes, never single.** This project lives under "Mark Lite",
      so the paths contain spaces, and FreeClaw rejects single quotes in a
      command outright.

    * **Forward slashes, never backslashes.** FreeClaw saves MCP commands to
      .env as `json.dumps(...)` wrapped in single quotes, but reads them back
      with `dotenv_values`, which collapses `\\\\` to `\\`. A Windows path
      therefore comes back as invalid JSON, `parse_env_list` gives up and
      returns an empty list, and *every* stdio server silently disappears from
      the list on the next read. The add itself appears to succeed, because
      that path uses the in-memory entry — the server only vanishes later.
      Windows accepts forward slashes in paths, and they round-trip through
      .env intact, so this sidesteps the bug without touching FreeClaw.
    """
    python = python_for_mcp().replace("\\", "/")
    server = MCP_SERVER.replace("\\", "/")
    config = str(config_path).replace("\\", "/")
    return f'"{python}" "{server}" --config "{config}"'


def normalise_mcp_commands(fc_home):
    """Rewrite FreeClaw's MCP_COMMANDS so every path uses forward slashes.

    Works around the .env round-trip bug described in mcp_command(). Our own
    entry is already backslash-free, but FreeClaw persists its built-in
    browser server with a Windows path, and MCP_COMMANDS is a single JSON
    list — one backslash anywhere in it makes the whole list unparseable, so
    every stdio server disappears, ours included.

    The file itself is fine: `json.dumps` wrote correct `\\\\` escapes, and only
    `dotenv_values` mangles them on the way back in. So the raw line is read
    and parsed here directly rather than through dotenv.

    Returns a description of what changed, or None if nothing needed to.
    """
    env_path = os.path.join(fc_home, ".env")
    if not os.path.isfile(env_path):
        return None

    with open(env_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for i, line in enumerate(lines):
        if not line.strip().startswith("MCP_COMMANDS="):
            continue
        raw = line.strip().split("=", 1)[1].strip()
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "'\"":
            raw = raw[1:-1]
        try:
            commands = json.loads(raw)
        except json.JSONDecodeError:
            # Already corrupted by an earlier write, or a shape we don't know.
            # Leave it alone rather than guess at what it meant.
            return None
        if not any("\\" in c for c in commands):
            return None

        fixed = [c.replace("\\", "/") for c in commands]
        lines[i] = f"MCP_COMMANDS='{json.dumps(fixed)}'\n"
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        changed = [c for c, g in zip(commands, fixed) if c != g]
        return f"{len(changed)} command(s) in {env_path}"
    return None


# ── THE PERSONA ──────────────────────────────────────────────

def write_persona(fc_home, user):
    """Put the Jarvis persona in the user's context.md.

    FreeClaw seeds a new user's context.md with a bare set of headings; this
    replaces it. It has to be a file write because FreeClaw exposes no endpoint
    for context.md — which is the one part of setup that needs FreeClaw to be
    on this machine.
    """
    if not os.path.isfile(PERSONA_PATH):
        raise SystemExit(f"Persona file is missing: {PERSONA_PATH}")

    with open(PERSONA_PATH, "r", encoding="utf-8") as f:
        persona = f.read()

    files_dir = os.path.join(fc_home, "Flask", "static", user, "files")
    os.makedirs(files_dir, exist_ok=True)
    target = os.path.join(files_dir, "context.md")

    # Back up only real memory. A user FreeClaw created moments ago holds
    # nothing but its bare heading template, and saving a .bak of that just
    # leaves confusing litter beside a first install.
    backed_up = False
    if os.path.isfile(target):
        with open(target, "r", encoding="utf-8") as f:
            current = f.read()
        has_content = any(line.strip() and not line.lstrip().startswith("#")
                          for line in current.splitlines())
        if has_content:
            shutil.copy2(target, target + ".bak")
            backed_up = True

    with open(target, "w", encoding="utf-8") as f:
        f.write(persona)
    return target, backed_up


# ── MAIN ─────────────────────────────────────────────────────

def read_freeclaw_password(fc_home):
    """FC_PASSWORD straight out of a local FreeClaw install's own .env, or
    None if it isn't there to read.

    Not python-dotenv, and not by accident: dotenv unescapes backslashes
    inside a quoted value, which is exactly the bug FreeClaw's own
    mcp_client.read_env_values() was written to route around (see
    normalise_mcp_commands above). A plain password is unlikely to contain
    one, but there's no reason to reintroduce the failure mode for a value
    this is trivial to parse by hand."""
    env_path = os.path.join(fc_home, ".env")
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return None
    for line in lines:
        line = line.strip()
        if not line.startswith("FC_PASSWORD="):
            continue
        value = line[len("FC_PASSWORD="):].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        return value or None
    return None


def resolve_connection(args, fc_home):
    """Work out the URL and password to connect with — asking the user only
    for whatever couldn't be worked out on its own.

    The common case (Jarvis and FreeClaw on the same machine, which is the
    only case Jarvis supports today — see the module docstring) needs no
    prompt at all: the address is always localhost, and the password sits
    right there in FreeClaw's own .env, on the same machine, readable by the
    same Windows user setup.py itself runs as. --url/--password stay
    available for anyone who wants to type them anyway.
    """
    url = args.url or jarvis_config.load().get("freeclaw_url") or "http://127.0.0.1:6767"
    if not url.startswith(("http://", "https://")):
        url = "http://" + url
    # Bare IP or hostname: assume FreeClaw's default port rather than :80.
    if url.count(":") < 2 and not url.rsplit(":", 1)[-1].isdigit():
        url = url + ":6767"

    password = args.password
    source = "given on the command line"
    if not password and fc_home:
        password = read_freeclaw_password(fc_home)
        source = f"read from {os.path.join(fc_home, '.env')}"
    if not password:
        if not sys.stdin.isatty():
            # Running unattended (install.ps1, a scheduled task, anything
            # without a human to answer a prompt) — input() would just hang
            # forever waiting on a stdin nobody is going to type into.
            raise SystemExit(
                "No FreeClaw password available: none was given with "
                "--password, and none could\n"
                "      be read from FreeClaw's .env" +
                (f" ({fc_home} has none set)" if fc_home else
                 " (no FreeClaw install was found)") +
                ".\n      Pass --password explicitly, or run this from a "
                "terminal where it can ask.")
        password = getpass.getpass("  FreeClaw password: ").strip()
        source = "typed just now"
    if not password:
        raise SystemExit("A password is required.")
    return url, password, source


def main():
    parser = argparse.ArgumentParser(
        description="Connect Jarvis to a FreeClaw install.")
    parser.add_argument("--url", help="FreeClaw address, e.g. http://127.0.0.1:6767")
    parser.add_argument("--password", help="FreeClaw web UI password")
    parser.add_argument("--user", default=jarvis_config.DEFAULT_FC_USER,
                        help="FreeClaw user to drive (default: Jarvis)")
    parser.add_argument("--freeclaw-home",
                        help="FreeClaw install directory, if it is not autodetected")
    parser.add_argument("--keep-persona", action="store_true",
                        help="Leave an existing context.md alone")
    args = parser.parse_args()

    say()
    say("  Jarvis - FreeClaw setup")
    say("  " + "-" * 40)
    say()

    # 1 — find the install on disk, before anything that needs a password —
    #     resolve_connection reads it straight out of here when it can.
    fc_home = find_freeclaw_home(args.freeclaw_home)
    if not fc_home:
        raise SystemExit(
            "  FreeClaw isn't installed on this machine.\n\n"
            "  Jarvis needs FreeClaw right here — its MCP server runs as a "
            "child process\n"
            "  of FreeClaw, and can only screenshot this screen or draw on "
            "this UI if it's\n"
            "  running beside them. Install it, then run this again:\n\n"
            "      irm https://freeclaw.eedeb.dev/install.ps1 | iex\n")
    step(1, f"Found FreeClaw at {fc_home}")

    url, password, password_source = resolve_connection(args, fc_home)
    user = args.user

    # 2 — reach it
    step(2, f"Connecting to FreeClaw at {url} (password {password_source}) ...")
    try:
        session = fc.admin_session(url, password)
    except fc.FreeClawError as e:
        raise SystemExit(
            f"      {e}\n\n"
            "      FreeClaw is installed but isn't answering, or the "
            "password on file is stale.\n"
            "      Start it from the tray (or run \"freeclaw\" from a "
            "terminal), then try again.\n"
            "      A password can also be given explicitly with "
            "--password.")
    say("      Connected.")

    # 3 — the user, created through FreeClaw's own API so it gets the whole
    #     set-up a user is meant to have: context.md, ping.md and a
    #     conversation.json. Writing files into static/<user>/ ourselves first
    #     would make FreeClaw consider the user to already exist (it lists
    #     users by scanning directories) and skip all of that.
    if user in fc.list_users(session, url):
        step(3, f"FreeClaw user '{user}' already exists.")
    else:
        fc.create_user(session, url, user)
        step(3, f"Created FreeClaw user '{user}'.")

    # 4 — the persona, over the template FreeClaw just seeded
    if args.keep_persona:
        step(4, "Leaving the existing context.md alone (--keep-persona).")
    else:
        target, had_one = write_persona(fc_home, user)
        step(4, f"Wrote the Jarvis persona to {target}"
                + (" (previous version saved as context.md.bak)" if had_one else ""))

        # The conversation created a moment ago snapshotted context.md as it
        # was — the bare template. That snapshot lasts until the next reset, so
        # without this the first turn would not know who it is. Selecting the
        # user is what /reset acts on.
        session.get(f"{url.rstrip('/')}/chat", params={"user": user}, timeout=30)
        reset = session.post(f"{url.rstrip('/')}/reset", timeout=60)
        if reset.status_code == 200:
            say("      Reset the conversation so the persona takes effect.")
        else:
            say(f"      Note: could not reset the conversation "
                f"({reset.status_code}); type /reset in FreeClaw to apply it.")

    # 5 — config file, needed before the MCP server is registered so the
    #     server has a control token to read on its very first spawn
    saved = jarvis_config.load()
    token = saved.get("control_token") or secrets.token_urlsafe(24)
    jarvis_config.update(
        freeclaw_url=url.rstrip("/"), freeclaw_password=password,
        freeclaw_user=user, control_token=token, configured=True)
    config_path = jarvis_config.config_path()
    step(5, f"Saved connection details to {config_path}")

    # 6 — the MCP server
    command = mcp_command(config_path)
    existing = [s.get("name") for s in fc.list_mcp_servers(session, url)]
    if MCP_NAME in existing:
        fc.remove_mcp_server(session, url, MCP_NAME)
    try:
        tool_count, warning = fc.add_stdio_mcp_server(session, url, MCP_NAME, command)
    except fc.FreeClawError as e:
        raise SystemExit(f"      Could not register the MCP server: {e}")
    step(6, f"Registered the '{MCP_NAME}' MCP server - {tool_count} tools.")
    if warning:
        say(f"      Note: {warning}")

    # FreeClaw has just rewritten .env, and that write may have put a Windows
    # path into MCP_COMMANDS for its own built-in server, which breaks the
    # whole list on the next read. Repair it before checking.
    repaired = normalise_mcp_commands(fc_home)
    if repaired:
        say(f"      Converted {repaired} to forward slashes "
            f"(see mcp_command() for why).")

    # Adding reports success from the in-memory entry, so a command that
    # cannot survive the .env round trip still looks like it worked and only
    # goes missing on the next read. Read it back and say so now.
    if MCP_NAME not in [s.get("name") for s in fc.list_mcp_servers(session, url)]:
        raise SystemExit(
            f"      The '{MCP_NAME}' server did not survive being saved to "
            f"FreeClaw's .env.\n"
            f"      This is the backslash-escaping bug described in "
            f"mcp_command().\n"
            f"      The command itself is fine:\n"
            f"        {command}")

    # 7 — the API Jarvis actually talks to
    if fc.api_enabled(session, url):
        step(7, "FreeClaw's API is already on.")
    else:
        fc.set_api_enabled(session, url, True)
        step(7, "Switched FreeClaw's OpenAI-compatible API on.")

    # 8 — prove the whole path works, without spending a token on it
    say()
    ok = verify(session, url, password, user)

    say()
    if ok:
        say("  Ready. Start Jarvis with:  python main.py")
    else:
        say("  Setup finished, but see the warnings above before starting Jarvis.")
    say()


def verify(session, url, password, user):
    """Check the things that silently produce a mute Jarvis."""
    ok = True

    providers = fc.list_providers(session, url)
    enabled = [p for p in providers if p.get("enabled", True)]
    if not enabled:
        ok = False
        say("  ! FreeClaw has no LLM provider configured, so it cannot answer "
            "anything.")
        say("    Open FreeClaw -> Settings -> Providers and add one, then try "
            "Jarvis again.")
    else:
        say(f"  - Providers: {', '.join(p.get('name', '?') for p in enabled)}")

    # /v1/models is the cheapest possible end-to-end test: it exercises the
    # same auth and the same enabled-flag the chat endpoint does.
    try:
        import requests
        resp = requests.get(f"{url.rstrip('/')}/v1/models",
                            headers={"Authorization": f"Bearer {password}"},
                            timeout=(6, 30))
        if resp.status_code == 200:
            users = [m.get("id") for m in resp.json().get("data", [])]
            if user in users:
                say(f"  - API reachable, and '{user}' is there.")
            else:
                ok = False
                say(f"  ! API reachable but '{user}' is not in {users}.")
        else:
            ok = False
            say(f"  ! API check failed ({resp.status_code}).")
    except Exception as e:
        ok = False
        say(f"  ! API check failed: {e}")

    return ok


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        say("\n  Cancelled.")
        sys.exit(1)
