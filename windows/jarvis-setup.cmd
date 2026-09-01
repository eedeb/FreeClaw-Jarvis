@echo off
rem Re-run Jarvis's FreeClaw setup (src\setup.py) - see windows\jarvis.cmd for
rem why this shim exists and how it locates the bundled interpreter.
rem
rem Needed after: editing src\jarvis_persona.md (this pushes the new persona
rem and resets the conversation so it takes effect), or if FreeClaw's install
rem moved. Safe to run any time - setup.py is idempotent.
rem
rem Keep this file ASCII with CRLF line endings - see jarvis.cmd.

setlocal
pushd "%~dp0..\src"
"%~dp0..\python\python.exe" setup.py %*
set JARVIS_EXIT=%ERRORLEVEL%
popd
endlocal & exit /b %JARVIS_EXIT%
