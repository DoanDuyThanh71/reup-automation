import os
import sys
import time
import uuid
import json
import sqlite3
import secrets
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, Header, Form
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "portal.db"

# Resolve taste-skill assets (works both inside monorepo locally and standalone in Docker/VPS)
TASTE_DIR = BASE_DIR / "taste" if (BASE_DIR / "taste").exists() else (REPO_ROOT / "app" / "static" / "taste")
STATIC_DIR = BASE_DIR / "static"
DEMOS_DIR = BASE_DIR / "demos" if (BASE_DIR / "demos").exists() else (REPO_ROOT / "outputs" / "voice_samples_rv_phim")
DIST_ZIP = REPO_ROOT / "dist" / "ReupAutomationStudio_Windows.zip"

ADMIN_SECRET = os.getenv("PORTAL_ADMIN_SECRET", "reup-admin-2026")
DOWNLOAD_REDIRECT_URL = os.getenv("DOWNLOAD_REDIRECT_URL", "").strip()
BANK_ID = os.getenv("VIETQR_BANK_ID", "MB")
BANK_ACCOUNT_NO = os.getenv("VIETQR_ACCOUNT_NO", "0000123456789")
BANK_ACCOUNT_NAME = os.getenv("VIETQR_ACCOUNT_NAME", "REUP STUDIO")


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    return conn


def init_db() -> None:
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS trial_leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                name TEXT DEFAULT '',
                hardware_note TEXT DEFAULT '',
                license_key TEXT NOT NULL,
                ip_address TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_trial_email ON trial_leads(email);

            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_code TEXT UNIQUE NOT NULL,
                email TEXT NOT NULL,
                name TEXT DEFAULT '',
                zalo_phone TEXT DEFAULT '',
                tier TEXT NOT NULL,
                amount_vnd INTEGER NOT NULL,
                status TEXT DEFAULT 'PENDING',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS registered_devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hwid TEXT UNIQUE NOT NULL,
                email TEXT NOT NULL,
                display_name TEXT DEFAULT '',
                license_key TEXT DEFAULT '',
                plan TEXT DEFAULT 'FREE_TRIAL',
                is_blocked INTEGER DEFAULT 0,
                os TEXT DEFAULT '',
                gpu_name TEXT DEFAULT '',
                vram_gb REAL DEFAULT 0,
                ram_gb REAL DEFAULT 0,
                cpu_threads INTEGER DEFAULT 0,
                app_version TEXT DEFAULT '',
                registered_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_dev_email ON registered_devices(email);
            """
        )


init_db()

app = FastAPI(title="Reup Studio Portal & License Server", version="2.0.0")

if TASTE_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(TASTE_DIR)), name="assets")
if DEMOS_DIR.exists():
    app.mount("/demos", StaticFiles(directory=str(DEMOS_DIR)), name="demos")
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _mint_key(prefix: str = "TRIAL") -> str:
    tok = secrets.token_hex(4).upper()
    return f"{prefix}-{tok[:4]}-{tok[4:]}"


class DeviceRegisterPayload(BaseModel):
    email: str
    display_name: Optional[str] = ""
    hwid: str
    license_key: Optional[str] = ""
    os: Optional[str] = ""
    gpu_name: Optional[str] = ""
    vram_gb: Optional[float] = 0
    ram_gb: Optional[float] = 0
    cpu_threads: Optional[int] = 0
    app_version: Optional[str] = "2.0.0-exe"
    registered_at: Optional[str] = ""


class AdminDevicePatch(BaseModel):
    hwid: str
    plan: Optional[str] = None
    is_blocked: Optional[bool] = None


class AdminOrderPatch(BaseModel):
    order_code: str
    status: str


@app.get("/", response_class=HTMLResponse)
async def home():
    html_path = STATIC_DIR / "index.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.get("/admin", response_class=HTMLResponse)
async def admin_page():
    html_path = STATIC_DIR / "admin.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.get("/api/v1/health")
async def health():
    zip_exists = DIST_ZIP.exists()
    zip_mb = round(DIST_ZIP.stat().st_size / (1024 * 1024), 2) if zip_exists else 201.76
    return {
        "ok": True,
        "service": "reup-studio-portal",
        "installer_ready": zip_exists or bool(DOWNLOAD_REDIRECT_URL),
        "installer_size_mb": zip_mb,
    }


@app.post("/api/v1/trial-request")
async def request_trial(request: Request):
    """Handles both FormData (from taste-skill form.form) and JSON."""
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        data = await request.json()
    else:
        form = await request.form()
        data = dict(form)

    email = str(data.get("email", "")).strip().lower()
    name = str(data.get("name", "")).strip()
    hardware_note = str(data.get("hardware_note", "")).strip()

    if not email or "@" not in email or "." not in email.split("@")[-1]:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "Vui lòng nhập địa chỉ Gmail hợp lệ."},
        )

    now = _now_iso()
    ip_addr = request.client.host if request.client else ""

    with get_db() as conn:
        existing = conn.execute(
            "SELECT license_key FROM trial_leads WHERE email = ? ORDER BY id DESC LIMIT 1",
            (email,),
        ).fetchone()
        license_key = existing["license_key"] if existing else _mint_key("TRIAL")
        if not existing:
            conn.execute(
                """
                INSERT INTO trial_leads (email, name, hardware_note, license_key, ip_address, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (email, name, hardware_note, license_key, ip_addr, now),
            )

    return {
        "ok": True,
        "email": email,
        "license_key": license_key,
        "download_url": "/download/windows",
        "message": f"Đã cấp mã kích hoạt {license_key} cho {email}.",
    }


@app.post("/api/v1/order")
async def create_order(request: Request):
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        data = await request.json()
    else:
        form = await request.form()
        data = dict(form)

    email = str(data.get("email", "")).strip().lower()
    name = str(data.get("name", "")).strip()
    zalo_phone = str(data.get("zalo_phone", "")).strip()
    tier = str(data.get("tier", "MEET_50K")).strip().upper()

    if not email or "@" not in email:
        return JSONResponse(status_code=400, content={"ok": False, "error": "Vui lòng nhập Gmail nhận vé / mã kích hoạt."})

    amount_map = {
        "MEET_50K": 50000,
        "PRO_MONTHLY": 149000,
    }
    amount = amount_map.get(tier, 50000)
    prefix = "RS50K" if tier == "MEET_50K" else "RSPRO"
    order_code = f"{prefix}{secrets.token_hex(2).upper()}"
    now = _now_iso()

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO orders (order_code, email, name, zalo_phone, tier, amount_vnd, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?)
            """,
            (order_code, email, name, zalo_phone, tier, amount, now),
        )

    qr_url = (
        f"https://img.vietqr.io/image/{BANK_ID}-{BANK_ACCOUNT_NO}-compact2.png"
        f"?amount={amount}&addInfo={order_code}&accountName={BANK_ACCOUNT_NAME.replace(' ', '%20')}"
    )
    return {
        "ok": True,
        "order_code": order_code,
        "tier": tier,
        "amount_vnd": amount,
        "bank_id": BANK_ID,
        "account_no": BANK_ACCOUNT_NO,
        "account_name": BANK_ACCOUNT_NAME,
        "qr_url": qr_url,
    }


@app.post("/api/v1/register-device")
async def register_device(payload: DeviceRegisterPayload):
    """
    Central HWID endpoint called automatically on first launch by ReupAutomationStudio.exe
    (`LICENSE_SERVER_URL=https://yourdomain.com/api/v1/register-device`).
    """
    clean_email = payload.email.strip().lower()
    clean_hwid = payload.hwid.strip().upper()
    clean_key = (payload.license_key or "").strip().upper()
    now = _now_iso()

    if not clean_email or not clean_hwid:
        raise HTTPException(status_code=400, detail="Thiếu email hoặc HWID thiết bị.")

    inferred_plan = "PRO" if clean_key.startswith("PRO-") else "FREE_TRIAL"

    with get_db() as conn:
        row = conn.execute(
            "SELECT plan, is_blocked FROM registered_devices WHERE hwid = ?",
            (clean_hwid,),
        ).fetchone()

        if row:
            if row["is_blocked"]:
                return JSONResponse(
                    status_code=403,
                    content={
                        "is_blocked": True,
                        "error": "Thiết bị này đã hết hạn dùng thử hoặc đang tạm khóa. Vui lòng nâng cấp khóa Pro trên trang chủ.",
                    },
                )
            plan = "PRO" if (row["plan"] == "PRO" or inferred_plan == "PRO") else row["plan"]
            conn.execute(
                """
                UPDATE registered_devices
                SET email = ?, display_name = ?, license_key = COALESCE(NULLIF(?, ''), license_key),
                    plan = ?, gpu_name = ?, vram_gb = ?, ram_gb = ?, cpu_threads = ?,
                    app_version = ?, last_seen_at = ?
                WHERE hwid = ?
                """,
                (
                    clean_email,
                    payload.display_name or "",
                    clean_key,
                    plan,
                    payload.gpu_name or "",
                    payload.vram_gb or 0,
                    payload.ram_gb or 0,
                    payload.cpu_threads or 0,
                    payload.app_version or "2.0.0-exe",
                    now,
                    clean_hwid,
                ),
            )
        else:
            plan = inferred_plan
            conn.execute(
                """
                INSERT INTO registered_devices (
                    hwid, email, display_name, license_key, plan, is_blocked,
                    os, gpu_name, vram_gb, ram_gb, cpu_threads, app_version,
                    registered_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    clean_hwid,
                    clean_email,
                    payload.display_name or "",
                    clean_key or f"FREE-{clean_hwid[-9:]}",
                    plan,
                    payload.os or "",
                    payload.gpu_name or "",
                    payload.vram_gb or 0,
                    payload.ram_gb or 0,
                    payload.cpu_threads or 0,
                    payload.app_version or "2.0.0-exe",
                    payload.registered_at or now,
                    now,
                ),
            )

    return {
        "ok": True,
        "hwid": clean_hwid,
        "email": clean_email,
        "plan": plan,
        "is_blocked": False,
    }


@app.api_route("/download/windows", methods=["GET", "HEAD"])
async def download_windows():
    if DOWNLOAD_REDIRECT_URL:
        return RedirectResponse(url=DOWNLOAD_REDIRECT_URL, status_code=302)
    if DIST_ZIP.exists():
        return FileResponse(
            path=str(DIST_ZIP),
            filename="ReupAutomationStudio_Windows.zip",
            media_type="application/zip",
        )
    raise HTTPException(
        status_code=404,
        detail="Chưa tìm thấy file ReupAutomationStudio_Windows.zip hoặc DOWNLOAD_REDIRECT_URL.",
    )


def _verify_admin(x_admin_secret: Optional[str]):
    if not x_admin_secret or x_admin_secret != ADMIN_SECRET:
        raise HTTPException(status_code=401, detail="Sai mã quản trị (ADMIN_SECRET).")


@app.get("/api/v1/admin/overview")
async def admin_overview(x_admin_secret: Optional[str] = Header(default=None)):
    _verify_admin(x_admin_secret)
    with get_db() as conn:
        devices = [dict(r) for r in conn.execute("SELECT * FROM registered_devices ORDER BY last_seen_at DESC LIMIT 200")]
        leads = [dict(r) for r in conn.execute("SELECT * FROM trial_leads ORDER BY id DESC LIMIT 200")]
        orders = [dict(r) for r in conn.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 200")]
    return {
        "ok": True,
        "counts": {
            "devices": len(devices),
            "leads": len(leads),
            "orders": len(orders),
            "pro_devices": sum(1 for d in devices if d["plan"] == "PRO"),
        },
        "devices": devices,
        "leads": leads,
        "orders": orders,
    }


@app.post("/api/v1/admin/device")
async def admin_patch_device(patch: AdminDevicePatch, x_admin_secret: Optional[str] = Header(default=None)):
    _verify_admin(x_admin_secret)
    with get_db() as conn:
        cur = conn.execute("SELECT * FROM registered_devices WHERE hwid = ?", (patch.hwid.upper(),)).fetchone()
        if not cur:
            raise HTTPException(status_code=404, detail="Không tìm thấy mã máy HWID này.")
        new_plan = patch.plan if patch.plan is not None else cur["plan"]
        new_blocked = int(patch.is_blocked) if patch.is_blocked is not None else cur["is_blocked"]
        conn.execute(
            "UPDATE registered_devices SET plan = ?, is_blocked = ? WHERE hwid = ?",
            (new_plan, new_blocked, patch.hwid.upper()),
        )
    return {"ok": True, "hwid": patch.hwid.upper(), "plan": new_plan, "is_blocked": bool(new_blocked)}


@app.post("/api/v1/admin/order")
async def admin_patch_order(patch: AdminOrderPatch, x_admin_secret: Optional[str] = Header(default=None)):
    _verify_admin(x_admin_secret)
    pro_key = _mint_key("PRO") if patch.status == "PAID" else None
    with get_db() as conn:
        conn.execute("UPDATE orders SET status = ? WHERE order_code = ?", (patch.status, patch.order_code))
    return {"ok": True, "order_code": patch.order_code, "status": patch.status, "minted_pro_key": pro_key}


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORTAL_PORT", "8088"))
    uvicorn.run(app, host="0.0.0.0", port=port)
