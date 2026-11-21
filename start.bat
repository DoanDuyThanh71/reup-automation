@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [*] Lan dau khoi chay: Dang cai dat moi truong tu dong...
    powershell -ExecutionPolicy Bypass -File install.ps1
)

echo [*] Dang khoi dong Reup Automation Server...
start "" "http://localhost:8000"
".venv\Scripts\python.exe" run.py
pause
