@echo off
setlocal
powershell -ExecutionPolicy Bypass -File "%~dp0scripts\restart_backend.ps1" %*
