@echo off
rem Connect Jarvis to FreeClaw. Run this once, or again to push an edited persona.
setlocal
cd /d "%~dp0src"
"%~dp0.venv\Scripts\python.exe" setup.py %*
endlocal
pause
