# Changes FreeClaw needs

Nothing in the FreeClaw repo was edited. Jarvis works today by driving the
endpoints FreeClaw already exposes. The first three issues below were found
during the first integration pass — **all three are now fixed** in FreeClaw
commit `19a146b` ("Fix some bugs and add more external access"), and Jarvis's
workarounds for them are now redundant (harmless, but no longer needed). One
new item follows from building tool-call visibility on top of `/chat`.

---

## 1. Windows paths break every stdio MCP server — RESOLVED

Was: MCP commands are written to `.env` as JSON, wrapped in single quotes, then
read back with `dotenv_values` — which unescapes `\\` to `\` inside a quoted
value, turning a Windows path into invalid JSON and silently emptying
`MCP_COMMANDS` (every stdio server, builtins included).

Fixed by `mcp_client.read_env_values()`, which reads `.env` as literal text
instead of through `dotenv_values` — the file on disk was always valid JSON;
only the read path was mangling it. `agent.read_providers()` was switched to
the same reader, since provider lists hit the identical bug.

**What Jarvis did meanwhile, now redundant:** `setup.py`'s `mcp_command()`
writes its own command with forward slashes, and `normalise_mcp_commands()`
rewrites any other backslash command already in `MCP_COMMANDS`. Both are
harmless to leave in place — forward slashes are valid Windows paths — but
could be simplified back to natural paths now that the underlying bug is gone.

---

## 2. MCP image results were discarded — RESOLVED

Was: `_stringify_result` turned every non-text MCP content block into
`"[image content omitted]"`. `take_screenshot` returned a proper image block
and it was thrown away — Jarvis could take a screenshot but never see it.

Fixed: `mcp_client.ToolText` carries a tool's images alongside its text, and
`agent._with_tool_images` expands them into an `image_url` user message
immediately after the tool result, for the providers worth trying it on
(`_create_completion` builds and retries without the image-carrying variant
if a provider 400s on it). `_MAX_HISTORY_IMAGES = 2` caps how many stay
attached across a conversation, so an old screenshot doesn't get re-sent in
full forever.

**Still provider-dependent.** Whether a given turn's screenshot is actually
*seen* now depends on whether the answering provider accepts image content —
none of your three enabled providers (Groq, Cerebras, NVIDIA) currently do;
the vision-capable one (`NVIDIA-vision`) is configured but switched off. No
Jarvis-side change needed either way — `take_screenshot`'s output was already
shaped for this.

---

## 3. No endpoint for `context.md` — RESOLVED

Was: no HTTP route read or wrote a user's `context.md`, so `setup.py` had to
write the file directly — the one part of setup that required FreeClaw to be
on this machine (not actually costly here, since the MCP server needs that
anyway, but a real gap for anyone scripting FreeClaw remotely).

Fixed: `GET`/`PUT /api/users/<name>/context`. The `PUT` handler also calls the
new `agent.refresh_context()` — re-snapshotting the running conversation's
system message from the file — so a write takes effect immediately instead of
waiting for the next reset.

**What Jarvis does meanwhile, now redundant:** `setup.py`'s `write_persona()`
still writes `context.md` directly. Switching it to the new endpoint would let
setup run against a FreeClaw on a different machine — everything else it does
is already just HTTP — but the MCP server still has to be colocated for
screenshots and widgets, so that's not a capability Jarvis currently has any
use for. Left as-is; worth revisiting if that changes.

---

## 4. `/chat` has no way to say "nobody's here to answer a prompt"

**New, not a bug — a gap for a client that isn't a browser.**

`/v1/chat/completions` runs `activate_session(name, interactive=False)`, so an
API caller with no one to ask gets bash commands refused instantly rather than
blocked on `approvals.wait()`. `/chat` — the only endpoint that streams
`tool_call`/`tool_result` events, which is what Jarvis needs for
[tool-call visibility](README.md#tool-call-visibility) — always runs
`interactive=True`, on the assumption that whatever's on the other end is the
browser and can answer `POST /api/approval`.

That assumption doesn't hold for Jarvis: nothing here can render an approval
prompt, and FreeClaw's own `APPROVAL_TIMEOUT` is five minutes — exactly the
kind of unexplained, silent wait that tool-call visibility exists to get rid
of. `FreeClawChat` (Jarvis's `/chat` client) works around this by watching for
`approval_request` events and immediately `POST`ing a `deny` decision for each
one — functionally identical to what `/v1` already does, just implemented on
the client side because `/chat` gives no way to ask for that behaviour.

**Suggested fix.** An `interactive` flag on the request body (or a query
param) that `/chat`'s `generate()` passes through to `activate_session`, the
same as `/v1` already decides for itself. Any streaming, non-browser client
wired against `/chat` for its richer events — not just Jarvis — would want
this rather than reimplementing the same auto-deny.

---

## Not a change, just a prerequisite

FreeClaw needs at least one enabled LLM provider under **Settings →
Providers** before any turn can succeed — obvious, but worth stating since a
misconfigured install fails exactly the way a broken one would otherwise.
