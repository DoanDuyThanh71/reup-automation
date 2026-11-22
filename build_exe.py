"""
Builds the clean, customer-ready Windows `.exe` package (`dist/ReupAutomationStudio/ReupAutomationStudio.exe`).
- Automatically bundles FastAPI, Uvicorn, SQLite, FFmpeg binary (`imageio-ffmpeg`), Edge-TTS, yt-dlp, and the Web Studio UI.
- Does NOT include your personal `.env`, `data/reup_automation.db`, or `outputs/`!
"""
import os
import sys
import shutil
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def build():
    os.chdir(BASE_DIR)
    dist_dir = os.path.join(BASE_DIR, "dist", "ReupAutomationStudio")
    if os.path.exists(dist_dir):
        shutil.rmtree(dist_dir, ignore_errors=True)

    static_src = os.path.join(BASE_DIR, "app", "static")
    add_data_arg = f"{static_src};app/static"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--name", "ReupAutomationStudio",
        "--add-data", add_data_arg,
        "--collect-binaries", "imageio_ffmpeg",
        "--collect-all", "sherpa_onnx",
        "--collect-submodules", "uvicorn",
        "--collect-submodules", "fastapi",
        "--collect-submodules", "sqlalchemy",
        "--collect-submodules", "edge_tts",
        "--collect-submodules", "app",
        "--exclude-module", "pytest",
        "--exclude-module", "tkinter",
        "launcher.py",
    ]
    print("Building ReupAutomationStudio.exe with PyInstaller...")
    subprocess.run(cmd, check=True)

    # Create clean empty customer directories & quick-start README inside dist/ReupAutomationStudio
    for sub in ("data", "outputs", "temp"):
        os.makedirs(os.path.join(dist_dir, sub), exist_ok=True)

    readme_txt = (
        "============================================================\n"
        "  REUP AUTOMATION STUDIO - BẢN DESKTOP 1-CLICK (.EXE)\n"
        "============================================================\n\n"
        "CÁCH SỬ DỤNG CỰC ĐƠN GIẢN:\n"
        "1. Bấm đúp vào file 'ReupAutomationStudio.exe'.\n"
        "2. Trình duyệt sẽ tự động mở giao diện điều khiển.\n"
        "3. Ở lần mở đầu tiên: Nhập Gmail của bạn để kích hoạt Mã Vân Tay Máy (HWID)\n"
        "   và dán 1 mã Gemini API miễn phí (lấy tại https://aistudio.google.com/app/apikey).\n"
        "4. Từ lần sau: Chỉ cần dán link Douyin / TikTok và bấm 'Chạy 1-Click Toàn Trình'!\n\n"
        "LƯU Ý:\n"
        "- Toàn bộ tiến trình, phụ đề SRT và video MP4 của bạn được lưu riêng tư\n"
        "  ngay tại thư mục ./data và ./outputs trên máy tính của bạn.\n"
    )
    with open(os.path.join(dist_dir, "HUONG_DAN_SU_DUNG.txt"), "w", encoding="utf-8") as f:
        f.write(readme_txt)

    exe_path = os.path.join(dist_dir, "ReupAutomationStudio.exe")
    print(f"\nBUILD SUCCESS! File EXE san sang tai: {exe_path}")


if __name__ == "__main__":
    build()
