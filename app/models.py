import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, Float
from pydantic import BaseModel, Field
from .database import Base

# ==========================================
# SQLAlchemy Models
# ==========================================

class JobModel(Base):
    __tablename__ = "jobs"

    id = Column(String(64), primary_key=True, index=True)
    source_url = Column(String(1024), nullable=False)
    status = Column(String(32), default="PENDING", index=True) # PENDING, INGESTING, TRANSCRIBING, TRANSLATING, DUBBING, RENDERING, PUBLISHING, COMPLETED, FAILED
    current_stage = Column(String(64), default="Khởi tạo")
    progress = Column(Integer, default=0) # 0 to 100
    error_message = Column(Text, nullable=True)

    # Local file paths
    source_video_path = Column(String(512), nullable=True)
    audio_path = Column(String(512), nullable=True)
    srt_raw_path = Column(String(512), nullable=True)
    srt_translated_path = Column(String(512), nullable=True)
    dubbed_audio_path = Column(String(512), nullable=True)
    output_video_path = Column(String(512), nullable=True)

    # Generated content & metadata
    product_keyword = Column(String(256), nullable=True)
    affiliate_link = Column(String(1024), nullable=True)
    title = Column(String(512), nullable=True)
    caption = Column(Text, nullable=True)
    hashtags = Column(String(512), nullable=True)
    transcript_summary = Column(Text, nullable=True)

    # Social Publishing
    published_facebook = Column(Boolean, default=False)
    facebook_post_id = Column(String(128), nullable=True)
    facebook_error = Column(Text, nullable=True)

    published_tiktok = Column(Boolean, default=False)
    tiktok_post_id = Column(String(128), nullable=True)
    tiktok_error = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source_url": self.source_url,
            "status": self.status,
            "current_stage": self.current_stage,
            "progress": self.progress,
            "error_message": self.error_message,
            "product_keyword": self.product_keyword,
            "affiliate_link": self.affiliate_link,
            "title": self.title,
            "caption": self.caption,
            "hashtags": self.hashtags,
            "transcript_summary": self.transcript_summary,
            "published_facebook": self.published_facebook,
            "facebook_post_id": self.facebook_post_id,
            "facebook_error": self.facebook_error,
            "published_tiktok": self.published_tiktok,
            "tiktok_post_id": self.tiktok_post_id,
            "tiktok_error": self.tiktok_error,
            "has_video": bool(self.output_video_path),
            "video_url": f"/api/jobs/{self.id}/video" if self.output_video_path else None,
            "srt_url": f"/api/jobs/{self.id}/srt" if self.srt_translated_path else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ConfigModel(Base):
    __tablename__ = "configs"

    key = Column(String(128), primary_key=True, index=True)
    value = Column(Text, nullable=True)
    category = Column(String(64), default="general") # ai, asr, tts, social, ecommerce, system
    is_secret = Column(Boolean, default=False)
    description = Column(String(256), nullable=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class LogModel(Base):
    __tablename__ = "logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(64), nullable=True, index=True)
    level = Column(String(16), default="INFO")
    stage = Column(String(64), nullable=True)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


# ==========================================
# Pydantic Schemas
# ==========================================

class JobCreate(BaseModel):
    source_url: str = Field(..., description="URL video Douyin, TikTok hoặc link video MP4 trực tiếp")
    custom_product_hint: Optional[str] = Field(None, description="Tên gợi ý sản phẩm nếu muốn cố định")
    voice_code: Optional[str] = Field(None, description="Mã giọng đọc (Vbee hoặc Edge-TTS)")
    auto_post_facebook: Optional[bool] = Field(False, description="Tự động đăng lên Facebook sau khi hoàn tất")
    auto_post_tiktok: Optional[bool] = Field(False, description="Tự động đăng lên TikTok sau khi hoàn tất")


class JobResponse(BaseModel):
    id: str
    source_url: str
    status: str
    current_stage: str
    progress: int
    error_message: Optional[str] = None
    product_keyword: Optional[str] = None
    affiliate_link: Optional[str] = None
    title: Optional[str] = None
    caption: Optional[str] = None
    hashtags: Optional[str] = None
    published_facebook: bool
    facebook_post_id: Optional[str] = None
    facebook_error: Optional[str] = None
    published_tiktok: bool
    tiktok_post_id: Optional[str] = None
    tiktok_error: Optional[str] = None
    video_url: Optional[str] = None
    srt_url: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ConfigUpdate(BaseModel):
    configs: Dict[str, str] = Field(..., description="Dictionary các cặp key-value cấu hình cần cập nhật")


class TestConnectionRequest(BaseModel):
    target: str = Field(..., description="Mục tiêu kiểm tra: facebook, ai, vbee, asr, shopee")
    custom_params: Optional[Dict[str, str]] = None


class BatchJobCreate(BaseModel):
    urls: List[str] = Field(..., description="Danh sách nhiều URL video để xử lý đồng loạt")
    custom_product_hint: Optional[str] = None
    voice_code: Optional[str] = None
    auto_post_facebook: Optional[bool] = False
    auto_post_tiktok: Optional[bool] = False


class AffiliateVerifyRequest(BaseModel):
    keyword_or_url: str = Field(..., description="Từ khóa sản phẩm hoặc link Shopee gốc cần tạo & kiểm tra link Affiliate")
    sub_id: Optional[str] = None


class ManualPublishRequest(BaseModel):
    job_id: str
    platform: str = Field(..., description="facebook hoặc tiktok")
    title: Optional[str] = None
    caption: Optional[str] = None
    hashtags: Optional[str] = None
    page_id: Optional[str] = None
    page_token: Optional[str] = None
    publish_mode: Optional[str] = Field("reel", description="reel hoặc video cho Facebook")
