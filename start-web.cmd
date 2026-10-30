@echo off
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
"%~dp0.venv-local\Scripts\python.exe" web.py
pause
