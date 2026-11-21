#!/usr/bin/env bash
set -e

# ==============================================================================
# REUP AUTOMATION - 1-COMMAND VPS INSTALLER (Ubuntu / Debian / CentOS)
# ==============================================================================

GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${CYAN}================================================================${NC}"
echo -e "${CYAN}   🚀 REUP AUTOMATION - 1-COMMAND VPS DEPLOYMENT INSTALLER      ${NC}"
echo -e "${CYAN}================================================================${NC}"

# Ensure directories exist
mkdir -p data outputs temp

# Provision .env if missing
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        echo -e "${GREEN}[+] Đã tạo file cấu hình .env từ .env.example${NC}"
    else
        cat <<EOF > .env
HOST=0.0.0.0
PORT=8000
DATABASE_URL=sqlite:///./data/reup_automation.db
EOF
        echo -e "${GREEN}[+] Đã khởi tạo file .env mặc định${NC}"
    fi
fi

PORT=$(grep -E '^PORT=' .env | cut -d '=' -f2 | tr -d '[:space:]')
PORT=${PORT:-8000}

# Prefer Docker Compose if available or install Docker if running as root on Linux
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    echo -e "${CYAN}[*] Phát hiện Docker Compose. Đang build và khởi chạy container...${NC}"
    docker compose up -d --build
    DEPLOY_MODE="Docker Compose"
elif command -v docker-compose >/dev/null 2>&1; then
    echo -e "${CYAN}[*] Phát hiện docker-compose. Đang build và khởi chạy container...${NC}"
    docker-compose up -d --build
    DEPLOY_MODE="docker-compose"
else
    echo -e "${YELLOW}[!] Không tìm thấy Docker. Chuyển sang cài đặt trực tiếp (Native Python + FFmpeg)...${NC}"
    if command -v apt-get >/dev/null 2>&1; then
        sudo apt-get update -y
        sudo apt-get install -y python3 python3-venv python3-pip ffmpeg fonts-liberation fonts-dejavu-core curl
    fi

    if [ ! -d ".venv" ]; then
        python3 -m venv .venv
    fi
    source .venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt

    # Start in background with nohup
    nohup .venv/bin/python run.py > data/server.log 2>&1 &
    DEPLOY_MODE="Native Python (nohup)"
fi

# Wait for health check
echo -e "${CYAN}[*] Đang kiểm tra trạng thái hoạt động của máy chủ (Port ${PORT})...${NC}"
for i in {1..15}; do
    if curl -s -f "http://localhost:${PORT}/api/stats" >/dev/null 2>&1; then
        break
    fi
    sleep 2
done

PUBLIC_IP=$(curl -s --max-time 4 https://ifconfig.me || hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")

echo -e "${GREEN}================================================================${NC}"
echo -e "${GREEN}✅ CÀI ĐẶT & KHỞI CHẠY THÀNH CÔNG! (${DEPLOY_MODE})${NC}"
echo -e "${GREEN}🌐 Giao diện Web Dashboard: http://${PUBLIC_IP}:${PORT}${NC}"
echo -e "${GREEN}🔑 Vào mục 'Cấu hình Token & API' trên Web để dán Token Facebook, AI, Vbee, Shopee.${NC}"
echo -e "${GREEN}================================================================${NC}"
