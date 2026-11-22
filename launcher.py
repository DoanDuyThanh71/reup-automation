"""
Standalone Windows Desktop Launcher (`ReupAutomationStudio.exe` entry point).
- Automatically opens the 1-Click Web Studio in the user's default browser.
- Stores all SQLite progress, configs, and rendered MP4s locally right next to the `.exe`.
- Zero terminal or Python knowledge required.
"""
import os
import sys
import time
import socket
import threading
import webbrowser


def _setup_runtime_paths():
    os.environ["PYTHONIOENCODING"] = "utf-8"
    for stream in (sys.stdout, sys.stderr):
        if stream and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        os.chdir(exe_dir)
        os.environ["REUP_COMMERCIAL_EXE"] = "1"
        data_dir = os.path.join(exe_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        os.makedirs(os.path.join(exe_dir, "outputs"), exist_ok=True)
        os.makedirs(os.path.join(exe_dir, "temp"), exist_ok=True)
        os.environ.setdefault("DATABASE_URL", f"sqlite:///{os.path.join(data_dir, 'reup_automation.db')}")


def _is_port_busy(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _pick_port(preferred: int = 8000) -> int:
    for p in range(preferred, preferred + 25):
        if not _is_port_busy(p):
            return p
    return preferred


def _open_browser_when_ready(url: str):
    for _ in range(40):
        time.sleep(0.5)
        try:
            port = int(url.rsplit(":", 1)[1].split("/")[0])
            if _is_port_busy(port):
                webbrowser.open(url)
                return
        except Exception:
            pass
    webbrowser.open(url)


def main():
    _setup_runtime_paths()
    import uvicorn
    from app.main import app

    port = _pick_port(int(os.getenv("PORT", "8000")))
    url = f"http://127.0.0.1:{port}"

    print("=" * 62)
    print("  REUP AUTOMATION STUDIO - 1-CLICK AI VIDEO DESKTOP")
    print(f"  Giao dien dieu khien: {url}")
    print("  Tien trinh & Video luu tai thu muc ./data va ./outputs")
    print("  (Giu cua so nay mo trong khi su dung phan mem)")
    print("=" * 62)

    if os.getenv("REUP_NO_BROWSER") != "1":
        threading.Thread(target=_open_browser_when_ready, args=(url,), daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
