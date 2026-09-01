@echo off
rem Jarvis launcher - the counterpart of FreeClaw's windows\freeclaw.cmd.
rem The installer puts this in <install>\bin and adds that one directory to
rem the user PATH, so `jarvis` works from any console.
rem
rem Two things it has to get right:
rem
rem   * The interpreter. It must be the bundled one - that is where Jarvis's
rem     dependencies (openwakeword, faster-whisper, sounddevice, ...) live.
rem     %~dp0 is this file's own directory (with a trailing backslash), so the
rem     path holds wherever the user chose to install.
rem
rem   * The working directory. main.py's own path handling is already
rem     independent of it, but pushd/popd is what freeclaw.cmd does and there
rem     is no reason for this shim to behave differently by accident.
rem
rem python.exe rather than pythonw.exe on purpose: run from a console, a
rem startup problem (no microphone, FreeClaw unreachable) should be visible
rem rather than silently swallowed. The Start Menu shortcut uses pythonw.exe
rem instead, since a GUI launch should never flash a console window.
rem
rem Keep this file ASCII with CRLF line endings. cmd.exe reads a batch file in
rem the OEM codepage and mis-parses bare LF, which turns these rem lines into
rem commands it then tries to run. .gitattributes pins the line endings;
rem please keep both.

setlocal
pushd "%~dp0..\src"
"%~dp0..\python\python.exe" main.py %*
set JARVIS_EXIT=%ERRORLEVEL%
popd
endlocal & exit /b %JARVIS_EXIT%
