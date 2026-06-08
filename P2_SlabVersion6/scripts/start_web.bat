@echo off
cd /d "%~dp0.."
set PYTHONPATH=%CD%\src
echo Starting SDIE V6 web UI at http://127.0.0.1:8765
echo Press Ctrl+C to stop.
python scripts\run_server.py
