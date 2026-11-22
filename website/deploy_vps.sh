#!/usr/bin/env bash
set -euo pipefail

# Usage on VPS (Ubuntu/Debian):
#   DOMAIN=tenmiencuaban.com PORTAL_ADMIN_SECRET=MatKhauRieng ./deploy_vps.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d "./taste" ] && [ -d "../app/static/taste" ]; then
  echo "[1/3] Bundling taste-skill design system assets..."
  cp -r ../app/static/taste ./taste
fi

if [ ! -d "./demos" ] && [ -d "../outputs/voice_samples_rv_phim" ]; then
  echo "[2/3] Bundling real Review-Phim voice demo MP3s..."
  mkdir -p ./demos
  cp ../outputs/voice_samples_rv_phim/*.mp3 ./demos/ || true
fi

echo "[3/3] Launching Reup Studio Portal + Automatic HTTPS Caddy..."
docker compose up -d --build
echo "Done! Website & HWID License API live at https://${DOMAIN:-localhost}"
