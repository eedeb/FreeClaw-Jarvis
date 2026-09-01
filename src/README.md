# How the original was recovered

Provenance notes for the code that came out of `MarkLite.exe` (PyInstaller
onedir, CPython 3.11). For the app as it now stands, see
[the project README](../README.md).

## What was recovered

| File | Origin | Status |
|---|---|---|
| `main_free.py` | decompiled from `main_free.pyc` (PYZ entry point) | reconstructed, verified — **superseded by `main.py`** |
| `resource_path.py` | decompiled from `resource_path.pyc` | reconstructed, verified — still in use |
| `ui/index.html`, `ui/script.js`, `ui/style.css` | shipped verbatim in `_internal/ui` | original, one bug fix (see project README) |
| `ui/UI.py` | shipped verbatim as a data file | original source, now genuinely imported |
| `Assets/`, `audio/` | copied from `_internal` | original (`chromedriver.exe`, 18 MB, left in `_internal/Assets`) |

### Verification

Both reconstructed files were checked against the original bytecode: every
function lands on its **exact original line number**, and all constants, global
names, local variable names and argument counts match. The only deltas are
Python 3.13 compiler artifacts (constant dedup, and 3.13's automatic docstring
dedenting), not source differences.

## What was broken in the shipped build

**`modules.vocalize` was missing entirely.** `main_free.py` imported
`modules.vocalize.coqui` (`speak`) and `modules.vocalize.speechjs`
(`SpeechToTextListener`), but no `modules/` package existed in the exe's PYZ
archive or in `_internal/`, so the app raised `ImportError` at startup and
could never have run. `vocalize.py` now supplies `speak()`; voice input is
still a placeholder.

**The front-end and back-end did not match.** `ui/` is the full version's UI
and calls ~43 Python functions; `main_free.py` exposed four, and the names did
not even line up (the JS calls `process_text_input`, the Python defined
`process_user_input`). `main.py` exposes both spellings, imports `ui/UI.py` for
the widget functions, and stubs the rest.

**`ui/UI.py` was dead code.** 1250 lines of the paid version's back-end, 23
`@eel.expose` widget functions, shipped as a plain data file and never
imported. It is now the widget layer, imported by `main.py` and driven by the
MCP server.

## Where the old config lived

`main_free.py`'s `load_api_key()` read `<user_data_dir>/cache/config.json`,
looking for `groq_api_key_api_keys[]` (preferring the entry matching
`groq_api_key_preferred_key_id` with `status == "active"`), then the first
active entry, then a flat `groq_api_key`. None of that is used any more — LLM
credentials are FreeClaw providers now.

The `.env` at the project root was never read by this code path: `main_free.py`
imported `os.environ` but never used it.
