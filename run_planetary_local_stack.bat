@echo off
setlocal
powershell -ExecutionPolicy Bypass -File "%~dp0scripts\start_planetary_local_stack.ps1" %*
