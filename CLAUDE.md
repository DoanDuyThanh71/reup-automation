# CLAUDE.md — Instructions for Claude Code & AI Agents

Please read [AGENTS.md](AGENTS.md) for the complete zero-failure installation, diagnostics (`python doctor.py`), testing (`pytest -v`), and REST API configuration playbook across Linux VPS, macOS, and Windows.

## Quick Commands
- **Linux VPS / macOS 1-Command Install & Start**: `bash install.sh`
- **Windows 1-Command Install**: `powershell -ExecutionPolicy Bypass -File install.ps1`
- **Windows Start Server**: `.\.venv\Scripts\python.exe run.py` (or `start.bat`)
- **System Self-Diagnostic**: `python doctor.py`
- **Run Offline Test Suite**: `pytest -v`
- **Healthcheck Endpoint**: `GET /api/health`
