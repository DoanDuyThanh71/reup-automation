# ==============================================================================
# REUP AUTOMATION - WINDOWS 1-COMMAND INSTALLER (PowerShell)
# Usage: powershell -ExecutionPolicy Bypass -File install.ps1
# ==============================================================================

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "   🚀 REUP AUTOMATION - WINDOWS 1-COMMAND INSTALLER             " -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan

# 1. Create required folders
foreach ($dir in @("data", "outputs", "temp")) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
    }
}

# 2. Provision .env if missing
if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Host "[+] Đã tạo file .env từ .env.example" -ForegroundColor Green
    } else {
        "HOST=0.0.0.0`nPORT=8000`nDATABASE_URL=sqlite:///./data/reup_automation.db" | Set-Content ".env"
    }
}

# 3. Check Python
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "[!] Không tìm thấy Python trong PATH. Vui lòng cài đặt Python 3.10+." -ForegroundColor Red
    exit 1
}

# 4. Create Virtualenv if not exists
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "[*] Đang khởi tạo môi trường ảo Python (.venv)..." -ForegroundColor Cyan
    python -m venv .venv
}

$VenvPython = ".\.venv\Scripts\python.exe"
$VenvPip = ".\.venv\Scripts\pip.exe"

Write-Host "[*] Đang cài đặt thư viện và FFmpeg tích hợp (imageio-ffmpeg)..." -ForegroundColor Cyan
& $VenvPython -m pip install --upgrade pip
& $VenvPip install -r requirements.txt

# 5. Run Doctor Diagnostic
Write-Host "[*] Đang chạy kiểm tra hệ thống (doctor.py)..." -ForegroundColor Cyan
& $VenvPython doctor.py

if ($LASTEXITCODE -ne 0) {
    Write-Host "[!] Kiểm tra hệ thống báo lỗi, vui lòng xem chi tiết bên trên." -ForegroundColor Red
    exit 1
}

Write-Host "================================================================" -ForegroundColor Green
Write-Host "✅ CÀI ĐẶT HOÀN TẤT 100%!" -ForegroundColor Green
Write-Host "👉 Để chạy server ngay, gõ: .\.venv\Scripts\python.exe run.py (hoặc mở start.bat)" -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Green
