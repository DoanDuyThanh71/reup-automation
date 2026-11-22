import os
import sys
import uuid
import json
import time
import hashlib
import platform
import subprocess
import requests
from typing import Dict, Any, Optional


class MachineLicenseClient:
    """
    Handles:
    1. Deterministic Hardware Machine Fingerprint (`HWID-XXXX-XXXX-XXXX`) using
       Motherboard UUID + Processor ID + Volume Serial + Hostname.
    2. First-Launch Account & HWID Cloud Registration: sends `(email, name, hwid, hardware_specs)`
       to the owner's Central Server / Supabase / Webhook (`LICENSE_SERVER_URL`), while keeping all
       video rendering jobs, MP4 files, and cookies 100% local on the user's PC.
    """

    @staticmethod
    def get_machine_hwid() -> str:
        parts = [platform.node(), platform.machine(), platform.processor()]
        if os.name == "nt":
            for ps_cmd in [
                "(Get-CimInstance Win32_ComputerSystemProduct).UUID",
                "(Get-CimInstance Win32_BIOS).SerialNumber",
            ]:
                try:
                    r = subprocess.run(
                        ["powershell", "-NoProfile", "-Command", ps_cmd],
                        capture_output=True,
                        text=True,
                        timeout=4,
                    )
                    val = (r.stdout or "").strip()
                    if val and "FFFF" not in val:
                        parts.append(val)
                except Exception:
                    pass
        else:
            parts.append(str(uuid.getnode()))

        raw_seed = "|".join(parts)
        digest = hashlib.sha256(raw_seed.encode("utf-8")).hexdigest().upper()
        return f"HWID-{digest[:4]}-{digest[4:8]}-{digest[8:12]}"

    @classmethod
    def get_registration_status(cls) -> Dict[str, Any]:
        from ..config import config

        hwid = cls.get_machine_hwid()
        saved_email = config.get("CLIENT_ACCOUNT_EMAIL", "").strip()
        saved_name = config.get("CLIENT_ACCOUNT_NAME", "").strip()
        saved_hwid = config.get("CLIENT_BOUND_HWID", "").strip()
        registered_at = config.get("CLIENT_REGISTERED_AT", "").strip()
        plan = config.get("CLIENT_LICENSE_PLAN", "TRIAL").strip() or "TRIAL"

        is_registered = bool(saved_email and (not saved_hwid or saved_hwid == hwid))
        hwid_mismatch = bool(saved_hwid and saved_hwid != hwid)

        return {
            "registered": is_registered,
            "hwid_mismatch": hwid_mismatch,
            "current_hwid": hwid,
            "bound_hwid": saved_hwid or None,
            "email": saved_email,
            "name": saved_name,
            "plan": plan,
            "registered_at": registered_at,
            "local_storage_mode": "100% Local SQLite & Local MP4 (Tiến trình tự lưu trên máy người dùng)",
        }

    @classmethod
    def register_first_launch(
        cls,
        email: str,
        name: str = "",
        license_key: str = "",
    ) -> Dict[str, Any]:
        from ..config import config
        from .hardware_advisor import HardwareAdvisor

        clean_email = (email or "").strip().lower()
        if not clean_email or "@" not in clean_email:
            return {"success": False, "error": "Vui lòng nhập địa chỉ Gmail hợp lệ để kích hoạt máy."}

        clean_name = (name or clean_email.split("@")[0]).strip()
        hwid = cls.get_machine_hwid()
        hw_info = HardwareAdvisor.inspect_and_recommend().get("hardware", {})
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        payload = {
            "email": clean_email,
            "display_name": clean_name,
            "hwid": hwid,
            "license_key": (license_key or "").strip() or f"FREE-{hwid[-9:]}",
            "os": f"{platform.system()} {platform.release()}",
            "gpu_name": hw_info.get("gpu_name", ""),
            "vram_gb": hw_info.get("vram_gb", 0),
            "ram_gb": hw_info.get("ram_gb", 0),
            "cpu_threads": hw_info.get("cpu_threads", 0),
            "app_version": "2.0.0-exe",
            "registered_at": now_iso,
        }

        # Sync to owner's Central Server / Supabase / n8n Webhook if configured
        server_url = config.get("LICENSE_SERVER_URL", "").strip() or os.getenv("LICENSE_SERVER_URL", "").strip()
        supabase_anon_key = config.get("LICENSE_SUPABASE_KEY", "").strip() or os.getenv("LICENSE_SUPABASE_KEY", "").strip()
        remote_synced = False
        plan = "PRO" if (license_key and license_key.strip().upper().startswith("PRO-")) else "FREE_TRIAL"

        if server_url:
            headers = {"Content-Type": "application/json"}
            if supabase_anon_key:
                headers["apikey"] = supabase_anon_key
                headers["Authorization"] = f"Bearer {supabase_anon_key}"
                headers["Prefer"] = "resolution=merge-duplicates,return=representation"
            try:
                res = requests.post(server_url, json=payload, headers=headers, timeout=10)
                if res.status_code == 403:
                    err_msg = "Tài khoản hoặc mã máy này đã hết hạn dùng thử / bị khóa."
                    try:
                        err_msg = res.json().get("error") or err_msg
                    except Exception:
                        pass
                    return {"success": False, "error": err_msg}
                if res.status_code in (200, 201, 204):
                    remote_synced = True
                    try:
                        r_json = res.json()
                        row = r_json[0] if (isinstance(r_json, list) and r_json) else r_json
                        if isinstance(row, dict):
                            if row.get("is_blocked"):
                                return {"success": False, "error": "Thiết bị này đã bị tạm khóa bởi Quản trị viên."}
                            if row.get("plan"):
                                plan = row["plan"]
                    except Exception:
                        pass
            except Exception as e:
                print(f"[MachineLicenseClient] Remote sync note: {e}")

        # Persist bound account + HWID locally on user's PC
        config.set_many({
            "CLIENT_ACCOUNT_EMAIL": clean_email,
            "CLIENT_ACCOUNT_NAME": clean_name,
            "CLIENT_BOUND_HWID": hwid,
            "CLIENT_LICENSE_KEY": payload["license_key"],
            "CLIENT_LICENSE_PLAN": plan,
            "CLIENT_REGISTERED_AT": now_iso,
        })

        return {
            "success": True,
            "email": clean_email,
            "name": clean_name,
            "hwid": hwid,
            "plan": plan,
            "remote_synced": remote_synced,
            "message": f"Đã kích hoạt thành công tài khoản {clean_email} gắn với mã máy {hwid}!",
        }
