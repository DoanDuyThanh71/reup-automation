import os
import shutil
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from .database import SessionLocal, Base, engine
from .models import ConfigModel

def get_ffmpeg_exe() -> str:
    """
    Returns the system ffmpeg executable path if available,
    or falls back to the pre-compiled binary bundled in imageio-ffmpeg.
    Guarantees ffmpeg works on Windows, Linux, and macOS without root/apt.
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

DEFAULT_VBEE_APP_ID = "63a47dd0-f273-4b4a-a9bf-ae354f38b554"
DEFAULT_VBEE_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpYXQiOjE3Nzg3NDA4MDN9.vSKa74Mutjtk6lGpEg2iuCItXZUrn9W9EBymYflEuXo"

DEFAULT_CONFIGS = [
    # AI Content & Translation
    {"key": "AI_BASE_URL", "value": "https://9router.n8n71.com/v1", "category": "ai", "is_secret": False, "description": "Endpoint API AI (9Router, ShopAIKey, OpenAI, Groq, DeepSeek...)"},
    {"key": "AI_API_KEY", "value": "", "category": "ai", "is_secret": True, "description": "API Key của mô hình AI"},
    {"key": "AI_MODEL", "value": "AiFF", "category": "ai", "is_secret": False, "description": "Model Name (AiFF, gpt-4o-mini, gemini-1.5-flash...)"},

    # Audio ASR (Speech-to-Text)
    {"key": "ASR_PROVIDER", "value": "shopaikey", "category": "asr", "is_secret": False, "description": "Nhà cung cấp ASR: shopaikey, openai, groq, local"},
    {"key": "ASR_API_KEY", "value": "", "category": "asr", "is_secret": True, "description": "API Key cho dịch vụ Speech-to-Text"},
    {"key": "ASR_BASE_URL", "value": "https://api.shopaikey.com/v1", "category": "asr", "is_secret": False, "description": "Base URL của ASR Service"},
    {"key": "ASR_MODEL", "value": "whisper-1", "category": "asr", "is_secret": False, "description": "Model Whisper"},

    # Voice Dubbing (TTS) - Vbee Default
    {"key": "TTS_PROVIDER", "value": "vbee", "category": "tts", "is_secret": False, "description": "Dịch vụ đọc lồng tiếng: vbee (mặc định) hoặc edge-tts"},
    {"key": "VBEE_APP_ID", "value": DEFAULT_VBEE_APP_ID, "category": "tts", "is_secret": False, "description": "Vbee App ID (Mặc định: 63a47dd0-f273-4b4a-a9bf-ae354f38b554)"},
    {"key": "VBEE_ACCESS_TOKEN", "value": DEFAULT_VBEE_TOKEN, "category": "tts", "is_secret": True, "description": "Vbee Bearer Access Token (API v1/tts)"},
    {"key": "VBEE_REFRESH_TOKEN_COOKIE", "value": "", "category": "tts", "is_secret": True, "description": "Cookie chuỗi refresh_token từ studio.vbee.vn (tùy chọn)"},
    {"key": "VBEE_VOICE_CODE", "value": "hn_female_ngochuyen_full_48k-fhg", "category": "tts", "is_secret": False, "description": "Mã giọng đọc Vbee (hn_female_ngochuyen_full_48k-fhg, hn_male_manhdung_news_48k-fhg...)"},
    {"key": "EDGE_TTS_VOICE", "value": "vi-VN-HoaiMyNeural", "category": "tts", "is_secret": False, "description": "Giọng đọc Edge-TTS dự phòng (vi-VN-HoaiMyNeural, vi-VN-NamMinhNeural)"},

    # E-Commerce & Scraping
    {"key": "DOUYIN_COOKIE", "value": "", "category": "ecommerce", "is_secret": True, "description": "Cookie Douyin (tùy chọn)"},
    {"key": "SHOPEE_APP_ID", "value": "", "category": "ecommerce", "is_secret": False, "description": "Shopee Affiliate Open API App ID (SHA256 Credential)"},
    {"key": "SHOPEE_APP_SECRET", "value": "", "category": "ecommerce", "is_secret": True, "description": "Shopee Affiliate Open API Secret Key"},
    {"key": "SHOPEE_COOKIE", "value": "", "category": "ecommerce", "is_secret": True, "description": "Cookie Shopee Affiliate Portal (affiliate.shopee.vn)"},
    {"key": "SHOPEE_SUB_ID", "value": "16550927460", "category": "ecommerce", "is_secret": False, "description": "Sub ID / Affiliate ID Shopee của bạn"},

    # Social Auto-Publishing - Facebook
    {"key": "FACEBOOK_AUTO_PUBLISH", "value": "false", "category": "social", "is_secret": False, "description": "Tự động đăng lên Facebook sau khi render xong (true/false)"},
    {"key": "FACEBOOK_PAGE_ID", "value": "", "category": "social", "is_secret": False, "description": "Facebook Page ID đích"},
    {"key": "FACEBOOK_PAGE_ACCESS_TOKEN", "value": "", "category": "social", "is_secret": True, "description": "Facebook Page Access Token (vĩnh viễn hoặc dài hạn)"},
    {"key": "FACEBOOK_PUBLISH_MODE", "value": "reel", "category": "social", "is_secret": False, "description": "Chế độ đăng Facebook: 'reel' (Facebook Reels) hoặc 'video' (bài đăng video thường)"},

    # Social Auto-Publishing - TikTok
    {"key": "TIKTOK_AUTO_PUBLISH", "value": "false", "category": "social", "is_secret": False, "description": "Tự động gửi/đăng lên TikTok (true/false)"},
    {"key": "TIKTOK_SESSION_ID", "value": "", "category": "social", "is_secret": True, "description": "Session ID Cookie TikTok của tài khoản đăng bài"},
    {"key": "TIKTOK_WEBHOOK_URL", "value": "", "category": "social", "is_secret": False, "description": "Webhook URL (n8n/Make/Server riêng) nhận video và đăng TikTok"},
]

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
                    config_entry = ConfigModel(
                        key=item["key"],
                        value=env_val,
                        category=item["category"],
                        is_secret=item["is_secret"],
                        description=item["description"]
                    )
                    db.add(config_entry)
                elif item["key"] in ("VBEE_APP_ID", "VBEE_ACCESS_TOKEN") and not (existing.value or "").strip():
                    existing.value = item["value"]
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
                return item.value
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
            if item:
                item.value = value
            else:
                item = ConfigModel(key=key, value=value, category="general")
                db.add(item)
            db.commit()
        finally:
            db.close()

    def set_many(self, config_dict: Dict[str, str]):
        db: Session = SessionLocal()
        try:
            for k, v in config_dict.items():
                item = db.query(ConfigModel).filter(ConfigModel.key == k).first()
                if item:
                    item.value = v
                else:
                    item = ConfigModel(key=k, value=v, category="general")
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
                val = item.value or ""
                if mask_secrets and item.is_secret and val:
                    if len(val) > 8:
                        masked = val[:4] + "*" * (len(val) - 8) + val[-4:]
                    else:
                        masked = "********"
                    result[item.key] = {
                        "value": masked,
                        "raw_length": len(val),
                        "category": item.category,
                        "is_secret": True,
                        "description": item.description
                    }
                else:
                    result[item.key] = {
                        "value": val,
                        "category": item.category,
                        "is_secret": item.is_secret,
                        "description": item.description
                    }
            return result
        finally:
            db.close()

config = ConfigManager()
