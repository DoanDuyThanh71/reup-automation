#!/usr/bin/env bash
# Self-heal Windows CRLF line endings if cloned with core.autocrlf=true
if grep -q $'\r' "$0" 2>/dev/null; then
    sed -i 's/\r$//' "$0" 2>/dev/null || tr -d '\r' < "$0" > "$0.tmp" && mv "$0.tmp" "$0"
    exec bash "$0" "$@"
fi

set -e

# ==============================================================================
# REUP AUTOMATION - UNIVERSAL 1-COMMAND INSTALLER (Linux VPS & macOS)
# Supports: Docker Compose | Ubuntu/Debian | CentOS/RHEL/Rocky/Alma | Alpine | macOS
# Handles: Root vs Non-Root (sudo), Port Conflicts, Missing FFmpeg, Systemd/Nohup
# ==============================================================================

GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${CYAN}================================================================${NC}"
echo -e "${CYAN}   🚀 REUP AUTOMATION - UNIVERSAL 1-COMMAND INSTALLER           ${NC}"
echo -e "${CYAN}================================================================${NC}"

# 1. Determine privilege prefix (handles root containers where sudo is not installed)
SUDO=""
if [ "$(id -u)" -ne 0 ]; then
    if command -v sudo >/dev/null 2>&1; then
        SUDO="sudo"
    else
        echo -e "${YELLOW}[!] Chạy với quyền user thường (không có sudo). Sẽ dùng cài đặt user-space.${NC}"
    fi
fi

# 2. Ensure persistent directories exist
mkdir -p data outputs temp

# 3. Provision .env if missing
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

# 4. Detect Port & Auto-resolve Port Conflicts
PORT=$(grep -E '^PORT=' .env | cut -d '=' -f2 | tr -d '[:space:]\r')
PORT=${PORT:-8000}

is_port_busy() {
    local p=$1
    if command -v ss >/dev/null 2>&1; then
        ss -tuln 2>/dev/null | grep -q ":${p} " && return 0 || return 1
    elif command -v lsof >/dev/null 2>&1; then
        lsof -iTCP:"${p}" -sTCP:LISTEN >/dev/null 2>&1 && return 0 || return 1
    elif command -v netstat >/dev/null 2>&1; then
        netstat -tuln 2>/dev/null | grep -q ":${p} " && return 0 || return 1
    fi
    return 1
}

# Stop our own previous process if running so we don't mistake our own port for a conflict
if [ -f data/server.pid ]; then
    OLD_PID=$(cat data/server.pid 2>/dev/null || true)
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        echo -e "${CYAN}[*] Đang dừng tiến trình cũ (PID: ${OLD_PID})...${NC}"
        kill "$OLD_PID" 2>/dev/null || true
        sleep 1
    fi
fi

if is_port_busy "$PORT"; then
    ORIG_PORT=$PORT
    for candidate in $(seq $((PORT + 1)) $((PORT + 25))); do
        if ! is_port_busy "$candidate"; then
            PORT=$candidate
            break
        fi
    done
    echo -e "${YELLOW}[!] Port ${ORIG_PORT} đang được sử dụng bởi ứng dụng khác. Tự động chuyển sang Port ${PORT}.${NC}"
    if grep -q '^PORT=' .env; then
        sed -i.bak "s/^PORT=.*/PORT=${PORT}/" .env && rm -f .env.bak
    else
        echo "PORT=${PORT}" >> .env
    fi
fi

export PORT

# 5. Deployment Functions
deploy_native() {
    echo -e "${CYAN}[*] Đang cấu hình môi trường Native Python + FFmpeg...${NC}"

    # Install system packages if missing
    if ! command -v python3 >/dev/null 2>&1 || ! command -v ffmpeg >/dev/null 2>&1; then
        if command -v apt-get >/dev/null 2>&1; then
            $SUDO apt-get update -y || true
            $SUDO apt-get install -y python3 python3-venv python3-pip ffmpeg fonts-liberation fonts-dejavu-core curl ca-certificates || true
        elif command -v dnf >/dev/null 2>&1; then
            $SUDO dnf install -y python3 python3-pip curl ca-certificates || true
            $SUDO dnf install -y ffmpeg || true
        elif command -v yum >/dev/null 2>&1; then
            $SUDO yum install -y python3 python3-pip curl ca-certificates || true
            $SUDO yum install -y ffmpeg || true
        elif command -v apk >/dev/null 2>&1; then
            $SUDO apk add --no-cache python3 py3-pip ffmpeg ttf-dejavu curl ca-certificates || true
        elif command -v brew >/dev/null 2>&1; then
            brew install python ffmpeg || true
        fi
    fi

    # Create virtualenv (with fallback if python3-venv package is broken)
    if [ ! -d ".venv" ]; then
        python3 -m venv .venv || python3 -m virtualenv .venv
    fi

    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install -r requirements.txt

    # Run doctor verification
    .venv/bin/python doctor.py

    # Start background service
    nohup .venv/bin/python run.py > data/server.log 2>&1 &
    echo $! > data/server.pid
    DEPLOY_MODE="Native Python (PID: $(cat data/server.pid))"
}

DEPLOY_MODE=""
FORCE_NATIVE=${FORCE_NATIVE:-0}

if [ "$FORCE_NATIVE" != "1" ] && command -v docker >/dev/null 2>&1; then
    # Ensure docker daemon is running
    if ! docker info >/dev/null 2>&1; then
        if command -v systemctl >/dev/null 2>&1; then
            $SUDO systemctl start docker 2>/dev/null || true
        elif command -v service >/dev/null 2>&1; then
            $SUDO service docker start 2>/dev/null || true
        fi
    fi

    if docker info >/dev/null 2>&1; then
        if docker compose version >/dev/null 2>&1; then
            echo -e "${CYAN}[*] Phát hiện Docker Compose V2. Đang build và khởi chạy container...${NC}"
            if docker compose up -d --build; then
                DEPLOY_MODE="Docker Compose V2"
            fi
        elif command -v docker-compose >/dev/null 2>&1; then
            echo -e "${CYAN}[*] Phát hiện docker-compose V1. Đang build và khởi chạy container...${NC}"
            if docker-compose up -d --build; then
                DEPLOY_MODE="docker-compose V1"
            fi
        fi
    fi
fi

# Fallback to native if Docker wasn't used or failed (e.g. LXC / unprivileged container)
if [ -z "$DEPLOY_MODE" ]; then
    deploy_native
fi

# 6. Wait for health check
echo -e "${CYAN}[*] Đang kiểm tra trạng thái hoạt động của máy chủ (Port ${PORT})...${NC}"
HEALTH_OK=0
for i in {1..20}; do
    if curl -s -f "http://127.0.0.1:${PORT}/api/health" >/dev/null 2>&1 || curl -s -f "http://127.0.0.1:${PORT}/api/stats" >/dev/null 2>&1; then
        HEALTH_OK=1
        break
    fi
    sleep 1
done

PUBLIC_IP=$(curl -s --max-time 3 https://ifconfig.me 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")
PUBLIC_IP=${PUBLIC_IP:-localhost}

echo -e "${GREEN}================================================================${NC}"
if [ "$HEALTH_OK" -eq 1 ]; then
    echo -e "${GREEN}✅ CÀI ĐẶT & KHỞI CHẠY THÀNH CÔNG 100%! (${DEPLOY_MODE})${NC}"
else
    echo -e "${YELLOW}⚠️ Tiến trình đã khởi chạy (${DEPLOY_MODE}), vui lòng kiểm tra log tại data/server.log nếu cần.${NC}"
fi
echo -e "${GREEN}🌐 Giao diện Web Dashboard : http://${PUBLIC_IP}:${PORT}${NC}"
echo -e "${GREEN}🩺 Endpoint Healthcheck    : http://${PUBLIC_IP}:${PORT}/api/health${NC}"
echo -e "${GREEN}🔑 Vào mục 'Cấu hình Token & API' trên Web để dán Token Facebook, AI, Vbee, Shopee.${NC}"
echo -e "${GREEN}================================================================${NC}"
