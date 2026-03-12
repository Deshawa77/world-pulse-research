@echo off
setlocal

set "ROOT=%~dp0"
cd /d "%ROOT%"

if not exist "%ROOT%logs" mkdir "%ROOT%logs"
set "LOGFILE=%ROOT%logs\orchestrator.log"

set "PYTHON_EXE=%ROOT%venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

"%PYTHON_EXE%" orchestrator.py >> "%LOGFILE%" 2>&1
