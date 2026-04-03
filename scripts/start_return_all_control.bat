@echo off
setlocal
set SCRIPT_DIR=%~dp0
start "" http://127.0.0.1:5052/
python "%SCRIPT_DIR%return_all_control.py" --host 127.0.0.1 --port 5052
