@echo off
rem Dev launcher (no console window). Run scripts\setup_dev.ps1 once first.
start "" "%USERPROFILE%\.customdic\venv\Scripts\pythonw.exe" "%~dp0customdic.pyw"
