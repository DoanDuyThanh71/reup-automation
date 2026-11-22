import os
import re
import hmac
import json
import uuid
import base64
import hashlib
import platform
from typing import Dict, Any, Optional, Tuple


ENC_PREFIX = "ENC:v1:"


class SecurityFingerprintManager:
    """
    Provides 3 layers of security & anti-detection fingerprinting:
    1. Secret Vault Encryption (Fernet/XOR-HMAC-SHA256 bound to machine + SECRET_KEY)
       and SHA-256 Secret Fingerprinting (`fp:sha256:xxxxxxxxxxxx`) so raw cookies/tokens
       never leak into logs, UI badges, or AI context windows.
    2. Deterministic Account-Bound Browser Fingerprint Profile (`User-Agent`, `Sec-CH-UA`,
       `Viewport`, `Locale`, `Timezone`, `WebGL` consistency) so Shopee/TikTok/Facebook
       sessions always present the exact same browser identity across runs.
    3. Video Anti-Duplicate Fingerprint Parameters (deterministic or per-job micro-contrast,
       saturation, crop, and clean container UUID) for FFmpeg rendering.
    """

    CHROME_PROFILES = [
        {
            "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "sec_ch_ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            "viewport": {"width": 1366, "height": 768},
            "webgl_vendor": "Google Inc. (Intel)",
            "webgl_renderer": "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)",
            "hardware_concurrency": 8,
            "device_memory": 8,
        },
        {
            "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "sec_ch_ua": '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
            "viewport": {"width": 1440, "height": 900},
            "webgl_vendor": "Google Inc. (NVIDIA)",
            "webgl_renderer": "ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 SUPER Direct3D11 vs_5_0 ps_5_0, D3D11)",
            "hardware_concurrency": 12,
            "device_memory": 16,
        },
        {
            "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
            "sec_ch_ua": '"Microsoft Edge";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            "viewport": {"width": 1536, "height": 864},
            "webgl_vendor": "Google Inc. (AMD)",
            "webgl_renderer": "ANGLE (AMD, AMD Radeon(TM) Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)",
            "hardware_concurrency": 8,
            "device_memory": 16,
        },
    ]

    @staticmethod
    def _derive_vault_key() -> bytes:
        secret_seed = os.getenv("SECRET_KEY", "reup-automation-local-vault")
        machine_seed = f"{platform.node()}|{platform.machine()}|{secret_seed}"
        return hashlib.pbkdf2_hmac("sha256", machine_seed.encode("utf-8"), b"reup_fp_vault_salt_v1", 60000, dklen=32)

    @classmethod
    def encrypt_secret(cls, plaintext: str) -> str:
        """Encrypts a secret string at rest with authenticated HMAC-SHA256 stream cipher."""
        if not plaintext or plaintext.startswith(ENC_PREFIX):
            return plaintext or ""
        key = cls._derive_vault_key()
        nonce = os.urandom(16)
        raw = plaintext.encode("utf-8")
        # Counter-mode keystream from HMAC-SHA256(key, nonce || counter)
        cipher_bytes = bytearray(len(raw))
        for blk_idx in range((len(raw) + 31) // 32):
            ks = hmac.new(key, nonce + blk_idx.to_bytes(4, "big"), hashlib.sha256).digest()
            start = blk_idx * 32
            end = min(start + 32, len(raw))
            for i in range(start, end):
                cipher_bytes[i] = raw[i] ^ ks[i - start]
        mac = hmac.new(key, nonce + bytes(cipher_bytes), hashlib.sha256).digest()[:16]
        token = base64.urlsafe_b64encode(nonce + mac + bytes(cipher_bytes)).decode("ascii")
        return f"{ENC_PREFIX}{token}"

    @classmethod
    def decrypt_secret(cls, value: str) -> str:
        """Decrypts an `ENC:v1:...` secret string; passes through plaintext for backward compatibility."""
        if not value or not value.startswith(ENC_PREFIX):
            return value or ""
        try:
            blob = base64.urlsafe_b64decode(value[len(ENC_PREFIX):].encode("ascii"))
            if len(blob) < 32:
                return ""
            nonce, mac, cipher_bytes = blob[:16], blob[16:32], blob[32:]
            key = cls._derive_vault_key()
            expected_mac = hmac.new(key, nonce + cipher_bytes, hashlib.sha256).digest()[:16]
            if not hmac.compare_digest(mac, expected_mac):
                return ""
            plain = bytearray(len(cipher_bytes))
            for blk_idx in range((len(cipher_bytes) + 31) // 32):
                ks = hmac.new(key, nonce + blk_idx.to_bytes(4, "big"), hashlib.sha256).digest()
                start = blk_idx * 32
                end = min(start + 32, len(cipher_bytes))
                for i in range(start, end):
                    plain[i] = cipher_bytes[i] ^ ks[i - start]
            return plain.decode("utf-8")
        except Exception:
            return ""

    @staticmethod
    def secret_fingerprint(secret: str) -> str:
        """Returns a safe, irreversible 12-hex-char SHA-256 fingerprint for UI/logs."""
        if not secret or not secret.strip():
            return "chưa-cài-đặt"
        digest = hashlib.sha256(secret.strip().encode("utf-8")).hexdigest()[:12]
        return f"fp:{digest}"

    @classmethod
    def get_browser_fingerprint(cls, account_seed: str = "default") -> Dict[str, Any]:
        """
        Generates a deterministic browser identity bound to `account_seed`
        so cookies never trigger device-change security flags.
        """
        seed_hash = hashlib.sha256((account_seed or "default").encode("utf-8")).hexdigest()
        idx = int(seed_hash[:8], 16) % len(cls.CHROME_PROFILES)
        prof = dict(cls.CHROME_PROFILES[idx])
        prof["fingerprint_id"] = f"bfp-{seed_hash[:10]}"
        prof["locale"] = "vi-VN"
        prof["timezone_id"] = "Asia/Ho_Chi_Minh"
        prof["accept_language"] = "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7"
        prof["headers"] = {
            "User-Agent": prof["ua"],
            "Accept-Language": prof["accept_language"],
            "Sec-CH-UA": prof["sec_ch_ua"],
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": '"Windows"',
        }
        prof["init_script"] = (
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});\n"
            f"Object.defineProperty(navigator, 'hardwareConcurrency', {{get: () => {prof['hardware_concurrency']}}});\n"
            f"Object.defineProperty(navigator, 'deviceMemory', {{get: () => {prof['device_memory']}}});\n"
            "Object.defineProperty(navigator, 'languages', {get: () => ['vi-VN', 'vi', 'en-US', 'en']});\n"
        )
        return prof

    @staticmethod
    def get_video_anti_detect_params(job_id: str = "") -> Dict[str, Any]:
        """
        Computes subtle, imperceptible per-video anti-duplicate fingerprint parameters
        so each rendered video has a fresh MD5/SHA256 & perceptual frame signature.
        """
        seed = job_id or str(uuid.uuid4())
        h = int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8], 16)
        contrast = round(1.010 + (h % 12) * 0.001, 4)       # 1.010 .. 1.021
        saturation = round(1.012 + ((h >> 4) % 15) * 0.001, 4)  # 1.012 .. 1.026
        brightness = round(0.003 + ((h >> 8) % 6) * 0.001, 4)   # 0.003 .. 0.008
        zoom = round(1.010 + ((h >> 12) % 10) * 0.001, 4)       # 1.010 .. 1.019
        media_uuid = str(uuid.uuid5(uuid.NAMESPACE_OID, f"reup-fp-{seed}-{h}"))
        return {
            "contrast": contrast,
            "saturation": saturation,
            "brightness": brightness,
            "zoom": zoom,
            "media_uuid": media_uuid,
            "vf_snippet": (
                f"scale=trunc(iw*{zoom}/2)*2:trunc(ih*{zoom}/2)*2,"
                f"crop=trunc(iw/{zoom}/2)*2:trunc(ih/{zoom}/2)*2,"
                f"eq=contrast={contrast}:saturation={saturation}:brightness={brightness}"
            ),
        }
