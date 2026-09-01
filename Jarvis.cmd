@echo off
rem Start Jarvis. Needs FreeClaw running and Setup.cmd already done.
setlocal
cd /d "%~dp0src"
start "" "%~dp0.venv\Scripts\pythonw.exe" main.py
endlocal
