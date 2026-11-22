import os
import sys
import time
import json
import sqlite3
import secrets
from pathlib import Path
from typing import Optional, Dict, Any

from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "portal.db"


def _load_dotenv_file(env_path: Path) -> None:
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


_load_dotenv_file(BASE_DIR / ".env")
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import payment_gateway  # noqa: E402

TASTE_DIR = BASE_DIR / "taste" if (BASE_DIR / "taste").exists() else (REPO_ROOT / "app" / "static" / "taste")
STATIC_DIR = BASE_DIR / "static"
DEMOS_DIR = BASE_DIR / "demos" if (BASE_DIR / "demos").exists() else (REPO_ROOT / "outputs" / "voice_samples_rv_phim")
DIST_ZIP = REPO_ROOT / "dist" / "ReupAutomationStudio_Windows.zip"

ADMIN_SECRET = os.getenv("PORTAL_ADMIN_SECRET") or os.getenv("ADMIN_KEY") or "reup-admin-2026"
DOWNLOAD_REDIRECT_URL = os.getenv("DOWNLOAD_REDIRECT_URL", "").strip()


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
                transfer_content TEXT DEFAULT '',
                provider TEXT DEFAULT 'sepay',
                email TEXT NOT NULL,
                name TEXT DEFAULT '',
                zalo_phone TEXT DEFAULT '',
                tier TEXT NOT NULL,
                amount_vnd INTEGER NOT NULL,
                status TEXT DEFAULT 'PENDING',
                fulfilled_key TEXT DEFAULT '',
                payment_ref TEXT DEFAULT '',
                paid_at TEXT DEFAULT '',
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
        # Ensure new columns exist if upgrading an older portal.db
        existing_cols = {r["name"] for r in conn.execute("PRAGMA table_info(orders)").fetchall()}
        for col_name, col_def in [
            ("transfer_content", "TEXT DEFAULT ''"),
            ("provider", "TEXT DEFAULT 'sepay'"),
            ("fulfilled_key", "TEXT DEFAULT ''"),
            ("payment_ref", "TEXT DEFAULT ''"),
            ("paid_at", "TEXT DEFAULT ''"),
        ]:
            if col_name not in existing_cols:
                conn.execute(f"ALTER TABLE orders ADD COLUMN {col_name} {col_def}")


init_db()

app = FastAPI(title="Reup Studio Portal & VietQR License Server", version="2.1.0")

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


def _generate_numeric_order_code() -> str:
    """12-digit random numeric code (compatible with both SePay regex \\d{6,18} and payOS int)."""
    first = secrets.choice("123456789")
    rest = "".join(secrets.choice("0123456789") for _ in range(11))
    return first + rest


def _activate_paid_order(conn: sqlite3.Connection, order_code: str, reference: str = "") -> Optional[Dict[str, Any]]:
    """Idempotently mark order PAID, mint PRO key or Meet VIP ticket, and upgrade bound HWIDs."""
    row = conn.execute("SELECT * FROM orders WHERE order_code = ?", (str(order_code),)).fetchone()
    if not row:
        return None
    if row["status"] == "PAID" and row["fulfilled_key"]:
        return dict(row)

    tier = row["tier"]
    fulfilled_key = row["fulfilled_key"] or (_mint_key("PRO") if tier == "PRO_MONTHLY" else _mint_key("MEET50K"))
    now = _now_iso()

    conn.execute(
        """
        UPDATE orders
        SET status = 'PAID', fulfilled_key = ?, payment_ref = COALESCE(NULLIF(?, ''), payment_ref), paid_at = ?
        WHERE order_code = ?
        """,
        (fulfilled_key, reference, now, str(order_code)),
    )

    if tier == "PRO_MONTHLY" and row["email"]:
        conn.execute(
            "UPDATE registered_devices SET plan = 'PRO', license_key = ?, is_blocked = 0 WHERE email = ?",
            (fulfilled_key, row["email"].lower()),
        )

    updated = conn.execute("SELECT * FROM orders WHERE order_code = ?", (str(order_code),)).fetchone()
    return dict(updated) if updated else None


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
        "payment": payment_gateway.gateway_status(),
    }


@app.get("/api/payment/status")
@app.get("/api/v1/payment/status")
async def payment_status():
    return payment_gateway.gateway_status()


@app.post("/api/v1/trial-request")
async def request_trial(request: Request):
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
        return JSONResponse(status_code=400, content={"ok": False, "error": "Vui lòng nhập địa chỉ Gmail hợp lệ."})

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
    label_map = {
        "MEET_50K": "Ve Buoi Meet Reup Studio",
        "PRO_MONTHLY": "Khoa Pro Reup Studio",
    }
    amount = amount_map.get(tier, 50000)
    order_code = _generate_numeric_order_code()
    now = _now_iso()

    active_provider = payment_gateway.get_active_provider()
    if active_provider:
        try:
            link = payment_gateway.create_payment(
                order_code=order_code,
                amount_vnd=amount,
                description=label_map.get(tier, "Reup Studio"),
                contact=email,
            )
            memo = link.transfer_content
            provider = link.provider
            qr_url = link.qr_image_url
            bank_code = link.bank_code
            acc_no = link.account_number
            acc_name = link.account_name
            checkout_url = link.checkout_url
        except payment_gateway.PaymentGatewayError as exc:
            return JSONResponse(status_code=503, content={"ok": False, "error": f"Lỗi cổng thanh toán: {exc}"})
    else:
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "error": "Cổng VietQR (SePay/payOS) chưa được cấu hình biến môi trường SEPAY_BANK_CODE / SEPAY_ACCOUNT_NO.",
            },
        )

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO orders (
                order_code, transfer_content, provider, email, name, zalo_phone,
                tier, amount_vnd, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)
            """,
            (order_code, memo, provider, email, name, zalo_phone, tier, amount, now),
        )

    return {
        "ok": True,
        "provider": provider,
        "order_code": order_code,
        "transfer_content": memo,
        "tier": tier,
        "amount_vnd": amount,
        "bank_id": bank_code,
        "account_no": acc_no,
        "account_name": acc_name,
        "qr_url": qr_url,
        "checkout_url": checkout_url,
        "status": "PENDING",
    }


@app.get("/api/v1/orders/{order_code}")
async def check_order_status(order_code: str):
    """
    Polled every 4s by the VietQR modal (matching co-tuong):
    - If already PAID in DB, returns immediately.
    - If PENDING and SePay API Token is set, polls SePay `/userapi/transactions/list` directly!
    - If PENDING and provider == 'payos', polls payOS payment status!
    """
    clean_code = str(order_code).strip()
    with get_db() as conn:
        row = conn.execute("SELECT * FROM orders WHERE order_code = ?", (clean_code,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Không tìm thấy đơn hàng.")
        order = dict(row)

    if order["status"] != "PAID":
        if order.get("provider") == "sepay" and payment_gateway.SePayGateway.has_api_token():
            try:
                ev = payment_gateway.SePayGateway.poll_order(clean_code, int(order["amount_vnd"]))
                if ev and ev.is_paid:
                    with get_db() as conn:
                        activated = _activate_paid_order(conn, clean_code, reference=ev.reference)
                        if activated:
                            order = activated
            except payment_gateway.PaymentGatewayError:
                pass
        elif order.get("provider") == "payos" and payment_gateway.PayOSGateway.is_configured():
            try:
                p_data = payment_gateway.PayOSGateway.get_payment(clean_code)
                if str(p_data.get("status", "")).upper() == "PAID":
                    with get_db() as conn:
                        activated = _activate_paid_order(conn, clean_code, reference=str(p_data.get("id", "")))
                        if activated:
                            order = activated
            except payment_gateway.PaymentGatewayError:
                pass

    return {
        "ok": True,
        "order_code": order["order_code"],
        "transfer_content": order["transfer_content"],
        "tier": order["tier"],
        "amount_vnd": order["amount_vnd"],
        "status": order["status"],
        "fulfilled_key": order["fulfilled_key"] if order["status"] == "PAID" else "",
        "paid_at": order["paid_at"],
    }


@app.post("/api/payment/sepay-webhook")
async def sepay_webhook(request: Request):
    """Official SePay incoming transfer webhook (`Authorization: Apikey <SEPAY_WEBHOOK_API_KEY>`)."""
    if not payment_gateway.SePayGateway.is_configured():
        return JSONResponse(status_code=503, content={"ok": False, "error": "SePay chưa được cấu hình."})

    try:
        payload = await request.json()
    except Exception:
        payload = {}

    ev = payment_gateway.SePayGateway.verify_webhook(request.headers, payload)
    if not ev.valid_auth:
        return JSONResponse(status_code=401, content={"ok": False, "error": "Sai khóa xác thực SePay Webhook."})

    if not ev.is_paid or not ev.order_code:
        return {"ok": True, "activated": False}

    with get_db() as conn:
        row = conn.execute("SELECT * FROM orders WHERE order_code = ?", (ev.order_code,)).fetchone()
        if not row or ev.amount_vnd < int(row["amount_vnd"]):
            return {"ok": True, "activated": False}
        activated = _activate_paid_order(conn, ev.order_code, reference=ev.reference)

    return {"ok": True, "activated": bool(activated), "order_code": ev.order_code}


@app.post("/api/payos/webhook")
async def payos_webhook(request: Request):
    """Official payOS HMAC-SHA256 webhook."""
    if not payment_gateway.PayOSGateway.is_configured():
        return JSONResponse(status_code=503, content={"ok": False, "error": "payOS chưa được cấu hình."})

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"ok": False})

    data = body.get("data") if isinstance(body, dict) else None
    sig = body.get("signature") if isinstance(body, dict) else None
    if not isinstance(data, dict) or not payment_gateway.PayOSGateway.verify_signature(data, sig):
        return JSONResponse(status_code=401, content={"ok": False, "error": "Chữ ký payOS không hợp lệ."})

    order_code = str(data.get("orderCode") or "").strip()
    amount_vnd = int(data.get("amount") or 0)
    code_ok = str(body.get("code")) == "00" and str(data.get("code", "00")) == "00"
    if not code_ok or not order_code:
        return {"ok": True, "activated": False}

    with get_db() as conn:
        row = conn.execute("SELECT * FROM orders WHERE order_code = ?", (order_code,)).fetchone()
        if not row or amount_vnd < int(row["amount_vnd"]):
            return {"ok": True, "activated": False}
        activated = _activate_paid_order(conn, order_code, reference=str(data.get("reference") or ""))

    return {"ok": True, "activated": bool(activated), "order_code": order_code}


@app.post("/api/v1/register-device")
async def register_device(payload: DeviceRegisterPayload):
    clean_email = payload.email.strip().lower()
    clean_hwid = payload.hwid.strip().upper()
    clean_key = (payload.license_key or "").strip().upper()
    now = _now_iso()

    if not clean_email or not clean_hwid:
        raise HTTPException(status_code=400, detail="Thiếu email hoặc HWID thiết bị.")

    with get_db() as conn:
        # Check if user already bought a PAID PRO order with this email or key
        paid_pro = conn.execute(
            """
            SELECT fulfilled_key FROM orders
            WHERE status = 'PAID' AND tier = 'PRO_MONTHLY' AND (email = ? OR fulfilled_key = ?)
            LIMIT 1
            """,
            (clean_email, clean_key),
        ).fetchone()
        inferred_plan = "PRO" if (paid_pro or clean_key.startswith("PRO-")) else "FREE_TRIAL"

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
        "payment": payment_gateway.gateway_status(),
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
    with get_db() as conn:
        if patch.status == "PAID":
            activated = _activate_paid_order(conn, patch.order_code, reference="manual_admin")
            return {"ok": True, "order_code": patch.order_code, "status": "PAID", "minted_pro_key": activated["fulfilled_key"] if activated else ""}
        conn.execute("UPDATE orders SET status = ? WHERE order_code = ?", (patch.status, patch.order_code))
    return {"ok": True, "order_code": patch.order_code, "status": patch.status}


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORTAL_PORT", "8088"))
    uvicorn.run(app, host="0.0.0.0", port=port)
