"""
Client for a running FreeClaw install — this is where Jarvis's brains live.

Three surfaces are used, all authenticated with the same FreeClaw password:

  * **/v1/chat/completions** (Bearer auth) — one full agent turn per call,
    all-or-nothing. Kept for the setup wizard's smoke test (send_message),
    where a single plain request is all that's wanted. Its streaming mode
    deliberately emits assistant text only — "tools run transparently" — so
    it cannot show a tool call in progress; see FreeClawChat for the surface
    that can.

  * **the session-authenticated admin API** (`/login`, `/api/users`,
    `/api/mcp`, `/api/api-status`) — used once, by the setup wizard, to create
    the Jarvis user and register this app's MCP server. Those routes want a
    login cookie rather than a bearer token, so `admin_session()` logs in and
    hands back a requests.Session.

  * **the session-authenticated `/chat` SSE stream** — the same endpoint the
    web UI itself runs on, driven by `FreeClawChat`. Where /v1's stream hides
    tool calls, this one narrates the turn as it actually happens: which
    intent was picked, which provider answered, every tool call and its
    result, in real time. That's what lets the Jarvis UI show something
    happening instead of sitting on "Processing..." for as long as a turn
    with several tool calls takes.

Nothing here modifies FreeClaw itself; it only drives endpoints FreeClaw
already exposes.
"""

import json
import threading

import requests

from logging_setup import get_logger

logger = get_logger(__name__)

# An agent turn can run tools, search the web and scrape pages before it says
# anything, so this is generous on read and tight on connect — a wrong IP
# should fail fast, a working one should be allowed to think.
CONNECT_TIMEOUT = 6
READ_TIMEOUT = 300


class FreeClawError(Exception):
    """Anything that stopped us getting a reply, phrased for the user."""


def _base(url):
    return (url or "").rstrip("/")


def _body(resp, limit=300):
    """Best-effort human-readable text from an error response."""
    try:
        data = resp.json()
        if isinstance(data, dict):
            err = data.get("error")
            if isinstance(err, dict):
                return str(err.get("message") or err)[:limit]
            if err:
                return str(err)[:limit]
        return str(data)[:limit]
    except ValueError:
        return (resp.text or "")[:limit]


# ── CHAT ─────────────────────────────────────────────────────

def send_message(url, password, user, message, timeout=READ_TIMEOUT):
    """Run one agent turn as `user` and return the assistant's reply text."""
    endpoint = f"{_base(url)}/v1/chat/completions"
    try:
        resp = requests.post(
            endpoint,
            headers={"Authorization": f"Bearer {password}",
                     "Content-Type": "application/json"},
            json={"model": user, "messages": [{"role": "user", "content": message}]},
            timeout=(CONNECT_TIMEOUT, timeout),
        )
    except requests.exceptions.ConnectTimeout:
        raise FreeClawError(f"FreeClaw did not answer at {_base(url)}. Is it running?")
    except requests.exceptions.ConnectionError:
        raise FreeClawError(f"Could not reach FreeClaw at {_base(url)}. Is it running?")
    except requests.exceptions.ReadTimeout:
        raise FreeClawError("FreeClaw took too long to answer.")
    except requests.RequestException as e:
        raise FreeClawError(f"Could not reach FreeClaw: {e}")

    if resp.status_code == 401:
        raise FreeClawError("FreeClaw rejected the password.")
    if resp.status_code == 503:
        # _require_api_auth answers 503 when the /v1 flag file is absent.
        raise FreeClawError(
            "FreeClaw's API is switched off. Turn it on with the API chip on its "
            "home page, or by typing /startapi in its chat.")
    if resp.status_code == 404:
        # /v1 answers 404 with the list of valid users when `model` is not one.
        raise FreeClawError(
            f"FreeClaw has no user called '{user}'. Re-run setup to create it.")
    if resp.status_code >= 400:
        raise FreeClawError(f"FreeClaw returned {resp.status_code}: {_body(resp)}")

    try:
        data = resp.json()
        return data["choices"][0]["message"]["content"] or ""
    except (ValueError, KeyError, IndexError, TypeError):
        logger.error("Unreadable /v1 response: %s", _body(resp))
        raise FreeClawError("FreeClaw sent back a reply I could not read.")


# ── ADMIN (setup only) ───────────────────────────────────────

def admin_session(url, password):
    """Log in to the web UI and return a Session carrying the cookie.

    /api/users and /api/mcp are session-authenticated rather than bearer-
    authenticated, so the setup wizard needs this rather than a token.
    """
    session = requests.Session()
    try:
        session.post(f"{_base(url)}/login", data={"password": password},
                     timeout=(CONNECT_TIMEOUT, 30), allow_redirects=False)
    except requests.exceptions.ConnectionError:
        raise FreeClawError(f"Could not reach FreeClaw at {_base(url)}. Is it running?")
    except requests.RequestException as e:
        raise FreeClawError(f"Could not reach FreeClaw: {e}")

    # A good password redirects to the home page and sets a session cookie; a
    # bad one re-renders the login form with a 200 and no cookie.
    if not session.cookies.get("session"):
        raise FreeClawError("FreeClaw rejected that password.")
    return session


def list_users(session, url):
    resp = session.get(f"{_base(url)}/api/users", timeout=(CONNECT_TIMEOUT, 30))
    if resp.status_code != 200:
        raise FreeClawError(f"Could not list FreeClaw users: {_body(resp)}")
    return [u.get("name") for u in resp.json().get("users", [])]


def create_user(session, url, name):
    """Create a FreeClaw user. Returns True if created, False if already there."""
    resp = session.post(f"{_base(url)}/api/users", json={"name": name},
                        timeout=(CONNECT_TIMEOUT, 30))
    if resp.status_code == 409:
        return False
    if resp.status_code != 200:
        raise FreeClawError(f"Could not create the '{name}' user: {_body(resp)}")
    return True


def list_mcp_servers(session, url):
    resp = session.get(f"{_base(url)}/api/mcp", timeout=(CONNECT_TIMEOUT, 30))
    if resp.status_code != 200:
        raise FreeClawError(f"Could not list MCP servers: {_body(resp)}")
    return resp.json().get("servers", [])


def add_stdio_mcp_server(session, url, name, command):
    """Register a local stdio MCP server install-wide.

    FreeClaw spawns the command immediately to count its tools, so a bad
    command line surfaces here rather than mid-conversation. Returns
    (tool_count, warning_or_None).
    """
    resp = session.post(
        f"{_base(url)}/api/mcp",
        json={"name": name, "transport": "stdio", "command": command},
        # Spawning a cold Python interpreter and listing its tools is the slow
        # part of setup; give it room before calling it a failure.
        timeout=(CONNECT_TIMEOUT, 120),
    )
    if resp.status_code == 409:
        raise FreeClawError(f"An MCP server named '{name}' already exists in FreeClaw.")
    if resp.status_code != 200:
        raise FreeClawError(f"Could not add the MCP server: {_body(resp)}")
    data = resp.json()
    return data.get("tool_count", 0), data.get("warning")


def remove_mcp_server(session, url, name):
    resp = session.delete(f"{_base(url)}/api/mcp/{name}",
                          timeout=(CONNECT_TIMEOUT, 60))
    return resp.status_code == 200


def api_enabled(session, url):
    resp = session.get(f"{_base(url)}/api/api-status", timeout=(CONNECT_TIMEOUT, 30))
    if resp.status_code != 200:
        return False
    return bool(resp.json().get("enabled"))


def set_api_enabled(session, url, enabled=True):
    """Turn FreeClaw's OpenAI-compatible API on. Without this, /v1 is closed."""
    resp = session.post(f"{_base(url)}/api/api-status", json={"enabled": bool(enabled)},
                        timeout=(CONNECT_TIMEOUT, 30))
    if resp.status_code != 200:
        raise FreeClawError(f"Could not switch FreeClaw's API on: {_body(resp)}")
    return True


def list_providers(session, url):
    """The LLM providers FreeClaw can call. Empty means it cannot answer at all."""
    resp = session.get(f"{_base(url)}/api/providers", timeout=(CONNECT_TIMEOUT, 30))
    if resp.status_code != 200:
        return []
    return resp.json().get("providers", [])


# ── STREAMING CHAT (tool-call visibility) ────────────────────

# The event vocabulary agent_stream() yields over /chat, straight from
# FreeClaw's src/agent.py. Reproduced here as the contract this class relies
# on — nothing enforces it stays in sync, so a FreeClaw update that renames or
# drops one of these is a place to look if events stop showing up.
#   intent, provider, token, reasoning, usage           - narration
#   tool_call {name, arguments}                         - a tool is starting
#   tool_result {name, result}                          - it finished
#   tool_throttled {name, limit}                         - held back, looping
#   approval_request {id, command, program, timeout}    - see deny_bash below
#   approval_resolved {id, decision, approved}
#   stopped                                              - turn was cancelled
#   done {conversation, updated_at}                      - terminal, success
#   error {error}                                        - terminal, failure


class FreeClawChat:
    """A persistent, session-authenticated connection to one FreeClaw user's
    conversation, narrating each turn in real time.

    One instance per (url, password, user), reused across turns: logging in
    and selecting the user only has to happen once, and the Flask session
    cookie it earns is what lets `/chat` (unlike /v1) hand back tool_call and
    tool_result events as they happen rather than only the final text.

    Not thread-safe for concurrent turns — callers serialize with their own
    lock. Jarvis only ever runs one turn at a time (main.py's _turn_lock), so
    that's the only guarantee this needs.
    """

    def __init__(self, url, password, user):
        self.url = url.rstrip("/")
        self.password = password
        self.user = user
        self._session = None
        self._lock = threading.Lock()

    def _login(self):
        """(Re)establish the session and point it at this user's conversation.

        `admin_session` already raises FreeClawError with a clear "wrong
        password" / "unreachable" message, so there's nothing to add here."""
        session = admin_session(self.url, self.password)
        resp = session.get(f"{self.url}/chat", params={"user": self.user},
                           timeout=(CONNECT_TIMEOUT, 30))
        if resp.status_code != 200:
            raise FreeClawError(
                f"Could not select the FreeClaw user '{self.user}' "
                f"(HTTP {resp.status_code}). Does that user exist? Re-run setup.py.")
        self._session = session
        return session

    def _deny_bash(self, session, event):
        """Refuse a bash approval request rather than let the turn sit on it.

        There is nobody at this end to answer one: Jarvis has no approval UI,
        and APPROVAL_TIMEOUT (FreeClaw's src/approvals.py) is 300 seconds — a
        turn that hit this and got no answer would sit exactly as "hung" as
        the symptom this whole streaming path exists to fix, just five
        minutes later instead of never. Denying immediately matches what /v1
        already does for an API caller with nobody to ask (interactive=False)
        — this keeps that same safety behaviour while gaining visibility into
        every other tool. A saved always-allow rule for a command still runs
        without ever reaching here; only a fresh, unrecognised command hits
        this refusal."""
        req_id = event.get("id")
        if not req_id:
            return
        try:
            session.post(f"{self.url}/api/approval",
                        json={"id": req_id, "decision": "deny"},
                        timeout=(CONNECT_TIMEOUT, 15))
        except requests.RequestException as e:
            logger.warning("Could not auto-deny bash approval %s: %s", req_id, e)

    def turn(self, message, timeout=READ_TIMEOUT):
        """Run one agent turn as this user, yielding its events as they
        arrive. The last event is always "done" (success) or "error"
        (failure) — callers should stop at either.

        Raises FreeClawError only for failures before the stream starts
        (can't reach FreeClaw, bad password, no such user); a failure during
        the turn itself comes through as an "error" event instead, the same
        as the web UI sees it.
        """
        with self._lock:
            session = self._session or self._login()
            resp = self._post(session, message, timeout)
            if resp.status_code == 401:
                # Session cookie expired or FreeClaw restarted with a new
                # SECRET_KEY — log in fresh, once, and retry this same turn.
                session = self._login()
                resp = self._post(session, message, timeout)
            if resp.status_code != 200:
                raise FreeClawError(
                    f"FreeClaw returned {resp.status_code} starting the turn.")

            for raw_line in resp.iter_lines(decode_unicode=True):
                if not raw_line or not raw_line.startswith("data:"):
                    continue
                payload = raw_line[len("data:"):].strip()
                if not payload:
                    continue
                try:
                    event = json.loads(payload)
                except json.JSONDecodeError:
                    logger.debug("Unparseable SSE line: %.200r", payload)
                    continue
                if event.get("type") == "approval_request":
                    self._deny_bash(session, event)
                yield event

    def reset(self):
        """Clear this user's conversation history on FreeClaw — the history
        only; the persona and long-term memory in context.md are untouched.

        Calls /reset directly rather than sending the text "/reset" through
        turn(): that route is where the web UI's own reset button lands, but
        it answers with one plain JSON body, not the SSE stream turn()
        parses — turn() would just see zero "data:" lines and report nothing
        happened, though the reset itself would have gone through regardless.

        Blocks until FreeClaw's own per-user conversation lock is free, so a
        reset that lands mid-turn waits that turn out rather than racing it —
        same as the web UI's reset button would.
        """
        with self._lock:
            session = self._session or self._login()
            resp = self._reset_request(session)
            if resp.status_code != 200:
                # Could be an expired session cookie (turn() sees this as a
                # clean 401) or, on this route specifically, a 302 back to
                # /login — reset() redirects on POST too, where /chat answers
                # 401 outright. Either way: log in fresh, once, and retry.
                session = self._login()
                resp = self._reset_request(session)
            if resp.status_code != 200:
                raise FreeClawError(
                    f"FreeClaw returned {resp.status_code} clearing the conversation.")

    def _reset_request(self, session):
        try:
            # allow_redirects=False so a not-logged-in 302 to /login is
            # visible as a non-200 rather than quietly followed and read as
            # success — the login page is itself a 200 response.
            return session.post(f"{self.url}/reset", timeout=(CONNECT_TIMEOUT, 60),
                                allow_redirects=False)
        except requests.exceptions.ConnectionError:
            raise FreeClawError(f"Could not reach FreeClaw at {self.url}. Is it running?")
        except requests.RequestException as e:
            raise FreeClawError(f"Could not reach FreeClaw: {e}")

    def _post(self, session, message, timeout):
        try:
            return session.post(f"{self.url}/chat", json={"message": message},
                                stream=True, timeout=(CONNECT_TIMEOUT, timeout))
        except requests.exceptions.ConnectionError:
            raise FreeClawError(f"Could not reach FreeClaw at {self.url}. Is it running?")
        except requests.exceptions.ReadTimeout:
            raise FreeClawError("FreeClaw took too long to answer.")
        except requests.RequestException as e:
            raise FreeClawError(f"Could not reach FreeClaw: {e}")
