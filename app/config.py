import os
import shutil
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from .database import SessionLocal, Base, engine
from .models import ConfigModel
from .services.security_fingerprint import SecurityFingerprintManager


def get_ffmpeg_exe() -> str:
    """
    Returns the system ffmpeg executable path if available,
    or falls back to the pre-compiled binary bundled in imageio-ffmpeg.
    """
    custom_bin = os.getenv("FFMPEG_BINARY")
    if custom_bin and os.path.exists(custom_bin):
        return custom_bin

    sys_ffmpeg = shutil.which("ffmpeg")
    if sys_ffmpeg:
        return sys_ffmpeg

    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


import sys

IS_COMMERCIAL_EXE = bool(getattr(sys, "frozen", False) or os.getenv("REUP_COMMERCIAL_EXE") == "1")

DEFAULT_VBEE_APP_ID = "" if IS_COMMERCIAL_EXE else "63a47dd0-f273-4b4a-a9bf-ae354f38b554"
DEFAULT_VBEE_TOKEN = "" if IS_COMMERCIAL_EXE else "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpYXQiOjE3Nzg3NDA4MDN9.vSKa74Mutjtk6lGpEg2iuCItXZUrn9W9EBymYflEuXo"
DEFAULT_TTS_PROVIDER = "edge-tts" if IS_COMMERCIAL_EXE else "vbee"
DEFAULT_AFF_ID = "" if IS_COMMERCIAL_EXE else "17374600599"
DEFAULT_SUB_ID = "reup_video" if IS_COMMERCIAL_EXE else "kenh71"
DEFAULT_FB_PAGE = "" if IS_COMMERCIAL_EXE else "1058364167367881"
DEFAULT_AUTO_PUB = "false" if IS_COMMERCIAL_EXE else "true"

DEFAULT_CONFIGS = [
    # AI & 2-Stage Gemini Video View + Context-Locked Subtitle Translation
    {"key": "SUBTITLE_MODE", "value": "gemini_video", "category": "ai", "is_secret": False, "description": "Chế độ tách & dịch Sub: gemini_video (2 bước: Xem Video lập bảng nhân vật -> Dịch Sub chuẩn xưng hô) hoặc whisper_asr"},
    {"key": "VIDEO_VIEW_MODEL", "value": "gemini-3.1-flash-lite", "category": "ai", "is_secret": False, "description": "Model Bước 1: Chuyên xem hình ảnh video 5p+, lập bảng quan hệ nhân vật & bóc sub gốc"},
    {"key": "SUB_TRANSLATE_MODEL", "value": "gemini-3.5-flash-lite", "category": "ai", "is_secret": False, "description": "Model Bước 2: Chuyên dịch phụ đề tiếng Việt chuẩn xưng hô theo bối cảnh"},
    {"key": "TRANSLATE_STYLE_PRESET", "value": "review_tom_tat", "category": "ai", "is_secret": False, "description": "Preset bối cảnh dịch: review_tom_tat, tong_tai_hien_dai, co_trang_tien_hiep, hoc_duong_thanh_xuan, gia_dinh_drama"},
    {"key": "CUSTOM_TRANSLATE_PROMPT", "value": "", "category": "ai", "is_secret": False, "description": "Custom Prompt bối cảnh & quy tắc xưng hô riêng khi dịch phụ đề"},
    {"key": "GEMINI_VIDEO_MODEL", "value": "gemini-3.6-flash", "category": "ai", "is_secret": False, "description": "Model dự phòng xem video"},
    {"key": "GEMINI_API_KEYS", "value": "", "category": "ai", "is_secret": True, "description": "Danh sách Google AI Studio Gemini Keys miễn phí (AIza..., mỗi dòng 1 key để xoay vòng)"},
    {"key": "AI_KEY_POOL", "value": "", "category": "ai", "is_secret": True, "description": "Pool nhiều API Key dự phòng (AIza..., gsk_..., sk-or-..., hoặc endpoint|key|model)"},
    {"key": "QUOTA_LOGIN_GATEWAY_URL", "value": "", "category": "ai", "is_secret": False, "description": "URL cổng Quota Login OAuth (VD: http://127.0.0.1:20128/v1 cho 9Router Antigravity/Gemini/Copilot)"},
    {"key": "QUOTA_LOGIN_API_KEY", "value": "9router-local", "category": "ai", "is_secret": True, "description": "Key kết nối cổng Quota Login cục bộ (nếu có)"},
    {"key": "AI_BASE_URL", "value": "https://api.shopaikey.com/v1", "category": "ai", "is_secret": False, "description": "Endpoint API AI chính (ShopAIKey, 9Router, OpenAI, Groq...)"},
    {"key": "AI_API_KEY", "value": "", "category": "ai", "is_secret": True, "description": "API Key của mô hình AI chính"},
    {"key": "AI_MODEL", "value": "gemini-2.5-flash-lite", "category": "ai", "is_secret": False, "description": "Model AI dịch văn bản & SEO"},

    # Audio ASR (Fallback Speech-to-Text)
    {"key": "ASR_PROVIDER", "value": "shopaikey", "category": "asr", "is_secret": False, "description": "Nhà cung cấp ASR dự phòng: shopaikey, openai, groq, local"},
    {"key": "ASR_API_KEY", "value": "", "category": "asr", "is_secret": True, "description": "API Key cho dịch vụ Speech-to-Text"},
    {"key": "ASR_BASE_URL", "value": "https://api.shopaikey.com/v1", "category": "asr", "is_secret": False, "description": "Base URL của ASR Service"},
    {"key": "ASR_MODEL", "value": "whisper-1", "category": "asr", "is_secret": False, "description": "Model Whisper"},

    # Voice Dubbing (TTS) - Vbee / Local On-Device / Edge-TTS
    {"key": "TTS_PROVIDER", "value": DEFAULT_TTS_PROVIDER, "category": "tts", "is_secret": False, "description": "Dịch vụ đọc lồng tiếng: local (chạy trên máy 0đ), vbee, hoặc edge-tts"},
    {"key": "LOCAL_TTS_ENGINE", "value": "sherpa_onnx", "category": "tts", "is_secret": False, "description": "Engine giọng Local: sherpa_onnx (64MB Offline), vieneu (48kHz Clone), hoặc custom_api"},
    {"key": "LOCAL_TTS_THREADS", "value": "4", "category": "tts", "is_secret": False, "description": "Số luồng CPU cho Voice Local"},
    {"key": "LOCAL_TTS_URL", "value": "", "category": "tts", "is_secret": False, "description": "URL máy chủ TTS cục bộ tùy chỉnh (VD: http://127.0.0.1:8001/v1/audio/speech)"},
    {"key": "LOCAL_VOICE_REF_WAV", "value": "", "category": "tts", "is_secret": False, "description": "Đường dẫn file WAV mẫu 3-5s để Clone giọng với VieNeu-TTS"},
    {"key": "VBEE_APP_ID", "value": DEFAULT_VBEE_APP_ID, "category": "tts", "is_secret": False, "description": "Vbee App ID"},
    {"key": "VBEE_ACCESS_TOKEN", "value": DEFAULT_VBEE_TOKEN, "category": "tts", "is_secret": True, "description": "Vbee Bearer Access Token (API v1/tts)"},
    {"key": "VBEE_REFRESH_TOKEN_COOKIE", "value": "", "category": "tts", "is_secret": True, "description": "Cookie refresh_token từ studio.vbee.vn (tùy chọn)"},
    {"key": "VBEE_VOICE_CODE", "value": "hn_female_ngochuyen_full_48k-fhg", "category": "tts", "is_secret": False, "description": "Mã giọng đọc Vbee"},
    {"key": "EDGE_TTS_VOICE", "value": "vi-VN-HoaiMyNeural", "category": "tts", "is_secret": False, "description": "Giọng đọc Edge-TTS dự phòng"},

    # E-Commerce & Scraping
    {"key": "DOUYIN_COOKIE", "value": "", "category": "ecommerce", "is_secret": True, "description": "Cookie Douyin (tùy chọn)"},
    {"key": "SHOPEE_APP_ID", "value": "", "category": "ecommerce", "is_secret": False, "description": "Shopee Affiliate Open API App ID"},
    {"key": "SHOPEE_APP_SECRET", "value": "", "category": "ecommerce", "is_secret": True, "description": "Shopee Affiliate Open API Secret Key"},
    {"key": "SHOPEE_COOKIE", "value": "", "category": "ecommerce", "is_secret": True, "description": "Cookie Shopee Affiliate (JSON Cookie-Editor hoặc key=value)"},
    {"key": "SHOPEE_AFFILIATE_ID", "value": DEFAULT_AFF_ID, "category": "ecommerce", "is_secret": False, "description": "Mã Affiliate ID nhận hoa hồng"},
    {"key": "SHOPEE_SUB_ID", "value": DEFAULT_SUB_ID, "category": "ecommerce", "is_secret": False, "description": "Sub ID theo dõi chiến dịch"},

    # Social Auto-Publishing - Facebook
    {"key": "FACEBOOK_AUTO_PUBLISH", "value": DEFAULT_AUTO_PUB, "category": "social", "is_secret": False, "description": "Tự động đăng lên Facebook sau khi render xong (true/false)"},
    {"key": "FACEBOOK_PAGE_ID", "value": DEFAULT_FB_PAGE, "category": "social", "is_secret": False, "description": "Facebook Page ID đích"},
    {"key": "FACEBOOK_PAGE_ACCESS_TOKEN", "value": "", "category": "social", "is_secret": True, "description": "Facebook Page Access Token"},
    {"key": "FACEBOOK_PUBLISH_MODE", "value": "reel", "category": "social", "is_secret": False, "description": "Chế độ đăng Facebook: 'reel' hoặc 'video'"},

    # Social Auto-Publishing - TikTok
    {"key": "TIKTOK_AUTO_PUBLISH", "value": DEFAULT_AUTO_PUB, "category": "social", "is_secret": False, "description": "Tự động đăng lên TikTok sau khi render xong (true/false)"},
    {"key": "TIKTOK_COOKIES", "value": "", "category": "social", "is_secret": True, "description": "Bộ Cookie TikTok (JSON Cookie-Editor hoặc sessionid=...)"},
    {"key": "TIKTOK_SESSION_ID", "value": "", "category": "social", "is_secret": True, "description": "Session ID Cookie TikTok"},
    {"key": "TIKTOK_WEBHOOK_URL", "value": "", "category": "social", "is_secret": False, "description": "Webhook URL nhận video đăng TikTok (nếu dùng n8n/Make)"},

    # Security, License & Video Anti-Duplicate Fingerprint
    {"key": "VIDEO_FINGERPRINT_PROTECTION", "value": "true", "category": "system", "is_secret": False, "description": "Tự động đổi vân tay MD5/khung hình/metadata video chống quét trùng lặp"},
    {"key": "LICENSE_SERVER_URL", "value": "", "category": "system", "is_secret": False, "description": "Endpoint Server / Supabase / Webhook nhận đăng ký tài khoản & HWID khách hàng"},
    {"key": "LICENSE_SUPABASE_KEY", "value": "", "category": "system", "is_secret": True, "description": "Supabase Anon Key (nếu dùng Supabase lưu HWID)"},
    {"key": "CLIENT_ACCOUNT_EMAIL", "value": "", "category": "system", "is_secret": False, "description": "Email người dùng đã kích hoạt trên máy này"},
    {"key": "CLIENT_ACCOUNT_NAME", "value": "", "category": "system", "is_secret": False, "description": "Tên người dùng trên máy này"},
    {"key": "CLIENT_BOUND_HWID", "value": "", "category": "system", "is_secret": False, "description": "Mã vân tay phần cứng máy đã khóa"},
]

SECRET_KEYS_SET = {item["key"] for item in DEFAULT_CONFIGS if item.get("is_secret")}


class ConfigManager:
    def __init__(self):
        Base.metadata.create_all(bind=engine)
        self._init_defaults()

    def _init_defaults(self):
        db: Session = SessionLocal()
        try:
            for item in DEFAULT_CONFIGS:
                existing = db.query(ConfigModel).filter(ConfigModel.key == item["key"]).first()
                if not existing:
                    env_val = os.getenv(item["key"], item["value"])
                    stored_val = (
                        SecurityFingerprintManager.encrypt_secret(env_val)
                        if (item["is_secret"] and env_val)
                        else env_val
                    )
                    config_entry = ConfigModel(
                        key=item["key"],
                        value=stored_val,
                        category=item["category"],
                        is_secret=item["is_secret"],
                        description=item["description"]
                    )
                    db.add(config_entry)
                elif item["key"] in ("VBEE_APP_ID", "VBEE_ACCESS_TOKEN") and not (existing.value or "").strip():
                    existing.value = (
                        SecurityFingerprintManager.encrypt_secret(item["value"])
                        if item["is_secret"]
                        else item["value"]
                    )
            db.commit()
        except Exception as e:
            db.rollback()
            print(f"[ConfigManager] Error initializing default configs: {e}")
        finally:
            db.close()

    def get(self, key: str, default: Optional[str] = None) -> str:
        db: Session = SessionLocal()
        try:
            item = db.query(ConfigModel).filter(ConfigModel.key == key).first()
            if item and item.value is not None and item.value != "":
                plain = SecurityFingerprintManager.decrypt_secret(item.value)
                if plain != "":
                    return plain
            return os.getenv(key, default if default is not None else "")
        finally:
            db.close()

    def get_bool(self, key: str, default: bool = False) -> bool:
        val = self.get(key, str(default)).strip().lower()
        return val in ("true", "1", "yes", "on")

    def set(self, key: str, value: str):
        db: Session = SessionLocal()
        try:
            item = db.query(ConfigModel).filter(ConfigModel.key == key).first()
            is_sec = (item.is_secret if item else (key in SECRET_KEYS_SET))
            stored = SecurityFingerprintManager.encrypt_secret(value) if (is_sec and value) else value
            if item:
                item.value = stored
            else:
                item = ConfigModel(key=key, value=stored, category="general", is_secret=is_sec)
                db.add(item)
            db.commit()
        finally:
            db.close()

    def set_many(self, config_dict: Dict[str, str]):
        db: Session = SessionLocal()
        try:
            for k, v in config_dict.items():
                if v is None:
                    continue
                # Ignore masked placeholder values accidentally re-posted from UI
                if isinstance(v, str) and "****" in v:
                    continue
                item = db.query(ConfigModel).filter(ConfigModel.key == k).first()
                is_sec = (item.is_secret if item else (k in SECRET_KEYS_SET))
                stored = SecurityFingerprintManager.encrypt_secret(v) if (is_sec and v) else v
                if item:
                    item.value = stored
                else:
                    item = ConfigModel(key=k, value=stored, category="general", is_secret=is_sec)
                    db.add(item)
            db.commit()
        finally:
            db.close()

    def get_all(self, mask_secrets: bool = True) -> Dict[str, Any]:
        db: Session = SessionLocal()
        try:
            items = db.query(ConfigModel).all()
            result = {}
            for item in items:
                val = SecurityFingerprintManager.decrypt_secret(item.value or "")
                fp = SecurityFingerprintManager.secret_fingerprint(val) if item.is_secret else None
                if mask_secrets and item.is_secret and val:
                    if len(val) > 8:
                        masked = val[:4] + "********" + val[-4:]
                    else:
                        masked = "********"
                    result[item.key] = {
                        "value": masked,
                        "raw_length": len(val),
                        "fingerprint": fp,
                        "category": item.category,
                        "is_secret": True,
                        "description": item.description
                    }
                else:
                    result[item.key] = {
                        "value": val,
                        "fingerprint": fp,
                        "category": item.category,
                        "is_secret": item.is_secret,
                        "description": item.description
                    }
            return result
        finally:
            db.close()


config = ConfigManager()
