@echo off
REM ===============================
REM Run World Pulse Orchestrator
REM ===============================

REM Set the working directory
cd /d C:\Projects\world_pulse

REM Optional: log output to a file
set LOGFILE=C:\Projects\world_pulse\orchestrator.log

REM Run Python script
"C:\Users\ROG\AppData\Local\Programs\Python\Python310\python.exe" orchestrator.py >> "%LOGFILE%" 2>&1
