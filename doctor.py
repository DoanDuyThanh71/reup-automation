"""
Reup Automation - Self-Diagnostic & Environment Doctor
Run `python doctor.py` to verify all dependencies, directories, database, and FFmpeg binary.
"""
import os
import sys
import shutil
import subprocess

def run_doctor() -> int:
    print("====================================================")
    print("🩺 REUP AUTOMATION - SYSTEM DOCTOR & DIAGNOSTICS")
    print("====================================================")
    issues = []

    # 1. Python version check
    py_ver = sys.version_info
    print(f"[✓] Python Version: {py_ver.major}.{py_ver.minor}.{py_ver.micro}")
    if (py_ver.major, py_ver.minor) < (3, 10):
        issues.append("Yêu cầu Python >= 3.10")

    # 2. Directories & Write Permissions
    base_dir = os.path.dirname(os.path.abspath(__file__))
    for folder in ("data", "outputs", "temp"):
        path = os.path.join(base_dir, folder)
        os.makedirs(path, exist_ok=True)
        if os.access(path, os.W_OK):
            print(f"[✓] Directory writable: {folder}/")
        else:
            issues.append(f"Không có quyền ghi vào thư mục: {path}")

    # 3. .env provisioning
    env_path = os.path.join(base_dir, ".env")
    env_example = os.path.join(base_dir, ".env.example")
    if not os.path.exists(env_path) and os.path.exists(env_example):
        shutil.copyfile(env_example, env_path)
        print("[✓] Auto-created .env from .env.example")
    else:
        print("[✓] Configuration file .env ready")

    # 4. FFmpeg check (System or imageio-ffmpeg fallback)
    try:
        from app.config import get_ffmpeg_exe
        ffmpeg_bin = get_ffmpeg_exe()
        res = subprocess.run([ffmpeg_bin, "-version"], capture_output=True, text=True, timeout=10)
        if res.returncode == 0:
            first_line = res.stdout.splitlines()[0] if res.stdout else "OK"
            print(f"[✓] FFmpeg Binary: {ffmpeg_bin} ({first_line})")
        else:
            issues.append("FFmpeg thực thi bị lỗi")
    except Exception as e:
        issues.append(f"Không tìm thấy FFmpeg khả dụng: {e}")

    # 5. Database & FastAPI App Initialization
    try:
        from app.database import SessionLocal
        from app.models import ConfigModel
        from app.config import config
        db = SessionLocal()
        count = db.query(ConfigModel).count()
        db.close()
        print(f"[✓] SQLite Database initialized ({count} config keys loaded)")
    except Exception as e:
        issues.append(f"Lỗi khởi tạo SQLite Database: {e}")

    print("====================================================")
    if issues:
        print("❌ PHÁT HIỆN LỖI CẦN KHẮC PHỤC:")
        for i in issues:
            print(f"   - {i}")
        return 1

    print("✅ HỆ THỐNG ĐẠT 100% TIÊU CHUẨN VÀ SẴN SÀNG CHẠY!")
    return 0

if __name__ == "__main__":
    sys.exit(run_doctor())
