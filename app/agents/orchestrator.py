import os
import traceback
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from ..database import SessionLocal
from ..models import JobModel, LogModel
from ..config import config

from .ingestion_agent import IngestionAgent
from .transcribe_agent import TranscribeAgent
from .content_policy_agent import ContentPolicyAgent
from .affiliate_agent import AffiliateAgent
from .dubbing_agent import DubbingAgent
from .render_agent import RenderAgent
from .publisher_agent import PublisherAgent
from ..services.gemini_video_client import GeminiVideoAnalyzer
from ..services.shopee_client import ShopeeAffiliateClient

import sys
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
TEMP_DIR = os.path.join(BASE_DIR, "temp")


class WorkflowOrchestrator:
    """
    Master Multi-Agent Orchestrator. Coordinates the 7 specialized AI agents
    with Gemini Multimodal Direct Video Understanding, Multi-Key Pool Failover,
    Anti-Duplicate Video Fingerprinting, and Auto Facebook + TikTok Publishing.
    """
    def __init__(self):
        self.ingestion_agent = IngestionAgent()
        self.transcribe_agent = TranscribeAgent()
        self.content_agent = ContentPolicyAgent()
        self.affiliate_agent = AffiliateAgent()
        self.dubbing_agent = DubbingAgent()
        self.render_agent = RenderAgent()
        self.publisher_agent = PublisherAgent()
        self.gemini_video = GeminiVideoAnalyzer()
        self.log_listeners = []

    def register_log_listener(self, callback):
        self.log_listeners.append(callback)

    def log(self, db: Session, job_id: str, stage: str, message: str, level: str = "INFO"):
        try:
            print(f"[{job_id[:8]}] [{stage}] {message}")
        except UnicodeEncodeError:
            pass
        log_entry = LogModel(job_id=job_id, stage=stage, message=message, level=level)
        db.add(log_entry)
        db.commit()
        payload = {
            "id": log_entry.id,
            "job_id": job_id,
            "stage": stage,
            "message": message,
            "level": level,
            "created_at": log_entry.created_at.isoformat() if log_entry.created_at else None
        }
        for listener in list(self.log_listeners):
            try:
                listener(payload)
            except Exception:
                pass

    def execute_pipeline(
        self,
        job_id: str,
        custom_product_hint: Optional[str] = None,
        voice_code: Optional[str] = None,
        auto_post_fb: Optional[bool] = None,
        auto_post_tt: Optional[bool] = None,
        custom_translate_prompt: Optional[str] = None,
        translate_style_preset: Optional[str] = None,
    ):
        db: Session = SessionLocal()
        job: Optional[JobModel] = db.query(JobModel).filter(JobModel.id == job_id).first()
        if not job:
            db.close()
            return

        job_dir = os.path.join(OUTPUT_DIR, job_id)
        os.makedirs(job_dir, exist_ok=True)

        try:
            # -----------------------------------------------------------------
            # Stage 1: Ingestion Agent
            # -----------------------------------------------------------------
            job.status = "INGESTING"
            job.current_stage = "1. Tải video gốc"
            job.progress = 15
            db.commit()
            self.log(db, job_id, "Tải video", f"Đang tải video từ URL: {job.source_url}")

            source_video_path = os.path.join(job_dir, "source_video.mp4")
            ingest_res = self.ingestion_agent.run(job.source_url, source_video_path)
            job.source_video_path = ingest_res["video_path"]
            db.commit()
            self.log(db, job_id, "Tải video", f"Tải thành công ({ingest_res['file_size'] / (1024*1024):.2f} MB)")

            # -----------------------------------------------------------------
            # Stage 2 & 3: Gemini Multimodal Direct Video Viewing OR Whisper ASR Fallback
            # -----------------------------------------------------------------
            audio_path = os.path.join(job_dir, "extracted_audio.mp3")
            raw_srt_path = os.path.join(job_dir, "raw_transcript.srt")
            translated_srt_path = os.path.join(job_dir, "vietnamese_sub.srt")

            sub_mode = config.get("SUBTITLE_MODE", "gemini_video").strip().lower()
            gemini_done = False

            if sub_mode == "gemini_video":
                job.status = "TRANSCRIBING"
                job.current_stage = "2. Model Xem Video 5p+ lập bảng nhân vật ➔ Model Dịch Sub chuẩn xưng hô"
                job.progress = 40
                db.commit()
                self.log(db, job_id, "Gemini 2-Stage", "Bước 1: Đang xem toàn bộ video & lập bảng xưng hô nhân vật chống lẫn người...")

                from ..services.gemini_video_client import TRANSLATION_STYLE_PRESETS
                merged_custom_prompt = custom_translate_prompt
                if translate_style_preset and translate_style_preset in TRANSLATION_STYLE_PRESETS:
                    preset_p = TRANSLATION_STYLE_PRESETS[translate_style_preset]
                    merged_custom_prompt = f"{preset_p}\n{custom_translate_prompt or ''}".strip()

                gem_res = self.gemini_video.analyze_and_translate_video(
                    video_path=job.source_video_path,
                    work_dir=job_dir,
                    product_hint=custom_product_hint or "",
                    custom_prompt=merged_custom_prompt,
                )
                if gem_res and gem_res.get("vietnamese_srt"):
                    with open(raw_srt_path, "w", encoding="utf-8") as f:
                        f.write(gem_res["raw_srt"])
                    with open(translated_srt_path, "w", encoding="utf-8") as f:
                        f.write(gem_res["vietnamese_srt"])
                    with open(os.path.join(job_dir, "character_bible.txt"), "w", encoding="utf-8") as f:
                        f.write(f"Bối cảnh: {gem_res.get('genre_context', '')}\n\n{gem_res.get('character_bible', '')}")

                    shopee = ShopeeAffiliateClient()
                    prod_kw = gem_res["product_name_vn"]
                    prod_url = shopee.search_product(prod_kw)
                    aff_link = shopee.convert_to_affiliate_link(prod_url, campaign_tag=f"job_{job_id[:8]}")

                    job.srt_raw_path = raw_srt_path
                    job.srt_translated_path = translated_srt_path
                    job.title = gem_res["title"]
                    job.caption = gem_res["caption"]
                    job.hashtags = gem_res["hashtags"]
                    job.product_keyword = prod_kw
                    job.affiliate_link = aff_link
                    job.transcript_summary = gem_res["summary"]
                    job.progress = 60
                    db.commit()
                    gemini_done = True
                    self.log(
                        db,
                        job_id,
                        "Gemini Vision",
                        f"Gemini đã xem video & dịch xong SRT! ({gem_res.get('provider_used')}) • Sản phẩm phát hiện: {prod_kw}",
                    )
                else:
                    self.log(db, job_id, "Gemini Vision", "Chuyển sang chế độ dự phòng Whisper ASR + LLM 1:1...", level="WARN")

            if not gemini_done:
                job.status = "TRANSCRIBING"
                job.current_stage = "2. Trích xuất âm thanh & Nhận diện phụ đề Whisper"
                job.progress = 35
                db.commit()
                trans_res = self.transcribe_agent.run(job.source_video_path, audio_path, raw_srt_path)
                job.audio_path = trans_res["audio_path"]
                job.srt_raw_path = trans_res["srt_path"]
                db.commit()

                job.status = "TRANSLATING"
                job.current_stage = "3. AI Dịch tiếng Việt 1:1 & Tạo tiêu đề/caption"
                job.progress = 55
                db.commit()
                content_res = self.content_agent.run(raw_srt_path, translated_srt_path, product_hint=custom_product_hint)

                job.srt_translated_path = content_res["translated_srt_path"]
                job.title = content_res["title"]
                job.caption = content_res["caption"]
                job.hashtags = content_res["hashtags"]
                job.product_keyword = content_res["product_keyword"]
                job.affiliate_link = content_res["affiliate_link"]
                job.transcript_summary = content_res["summary"]
                db.commit()

            # -----------------------------------------------------------------
            # Stage 3.5: Affiliate Verification Agent (Agent 7)
            # -----------------------------------------------------------------
            aff_res = self.affiliate_agent.run(
                product_keyword=job.product_keyword or custom_product_hint or "đồ gia dụng thông minh",
                existing_link=job.affiliate_link,
                job_id=job_id
            )
            job.product_keyword = aff_res["product_keyword"]
            job.affiliate_link = aff_res["affiliate_link"]
            db.commit()
            self.log(
                db,
                job_id,
                "Affiliate Agent",
                f"Đã xác thực link Shopee Affiliate ({aff_res['method']} • AffID: {aff_res.get('affiliate_id')}): {job.affiliate_link}"
            )

            # -----------------------------------------------------------------
            # Stage 4: Dubbing Agent
            # -----------------------------------------------------------------
            job.status = "DUBBING"
            job.current_stage = "4. Lồng tiếng AI (Vbee / Edge-TTS)"
            job.progress = 75
            db.commit()
            self.log(db, job_id, "Lồng tiếng AI", "Đang tạo giọng đọc lồng tiếng tiếng Việt đồng bộ mili-giây...")

            dubbed_audio_path = os.path.join(job_dir, "dubbed_audio.mp3")
            dub_res = self.dubbing_agent.run(translated_srt_path, dubbed_audio_path, voice_code=voice_code)
            job.dubbed_audio_path = dub_res["audio_path"]
            db.commit()
            self.log(db, job_id, "Lồng tiếng AI", f"Lồng tiếng hoàn tất ({dub_res['provider']} - giọng {dub_res['voice']})")

            # -----------------------------------------------------------------
            # Stage 5: Render Agent (with Anti-Duplicate Video Fingerprinting)
            # -----------------------------------------------------------------
            job.status = "RENDERING"
            job.current_stage = "5. Ghép video, Burn Sub & Tạo Vân Tay Bảo Mật"
            job.progress = 90
            db.commit()
            self.log(db, job_id, "Render & Vân tay", "Đang dùng FFmpeg ghép giọng, burn sub vàng viền đen và làm mới vân tay video...")

            output_video_path = os.path.join(job_dir, f"final_{job_id}.mp4")
            render_res = self.render_agent.run(job.source_video_path, dubbed_audio_path, translated_srt_path, output_video_path)
            job.output_video_path = render_res["output_video_path"]
            db.commit()
            self.log(
                db,
                job_id,
                "Render & Vân tay",
                f"Render thành công ({render_res['file_size'] / (1024*1024):.2f} MB • Vân tay: {render_res.get('video_fingerprint', 'ok')})"
            )

            # -----------------------------------------------------------------
            # Stage 6: Publisher Agent (Auto-Publish)
            # -----------------------------------------------------------------
            should_post_fb = auto_post_fb if auto_post_fb is not None else config.get_bool("FACEBOOK_AUTO_PUBLISH", False)
            should_post_tt = auto_post_tt if auto_post_tt is not None else config.get_bool("TIKTOK_AUTO_PUBLISH", False)

            if should_post_fb or should_post_tt:
                job.status = "PUBLISHING"
                job.current_stage = "6. Tự động xuất bản lên Facebook & TikTok"
                db.commit()

            if should_post_fb:
                self.log(db, job_id, "Đăng Facebook", "Đang xuất bản lên Fanpage Kênh 71...")
                fb_res = self.publisher_agent.publish_to_facebook(
                    video_path=job.output_video_path,
                    title=job.title or "Video Review",
                    caption=job.caption or "",
                    hashtags=job.hashtags or "",
                    affiliate_link=job.affiliate_link or ""
                )
                if fb_res.get("success"):
                    job.published_facebook = True
                    job.facebook_post_id = str(fb_res.get("post_id", ""))
                    self.log(db, job_id, "Đăng Facebook", f"Thành công! Post ID: {job.facebook_post_id} ({fb_res.get('permalink', '')})")
                else:
                    job.facebook_error = fb_res.get("error", "Lỗi không xác định")
                    self.log(db, job_id, "Đăng Facebook", f"Thất bại: {job.facebook_error}", level="ERROR")
                db.commit()

            if should_post_tt:
                self.log(db, job_id, "Đăng TikTok", "Đang tải video lên TikTok Studio (@tra_sua_nuong_71)...")
                tt_res = self.publisher_agent.publish_to_tiktok(
                    video_path=job.output_video_path,
                    title=job.title or "",
                    caption=job.caption or "",
                    hashtags=job.hashtags or ""
                )
                if tt_res.get("success"):
                    job.published_tiktok = True
                    job.tiktok_post_id = str(tt_res.get("post_id", ""))
                    self.log(db, job_id, "Đăng TikTok", tt_res.get("message", "Gửi TikTok thành công!"))
                else:
                    job.tiktok_error = tt_res.get("error", "Lỗi TikTok")
                    self.log(db, job_id, "Đăng TikTok", f"Lưu ý TikTok: {job.tiktok_error}", level="ERROR")
                db.commit()

            job.status = "COMPLETED"
            job.current_stage = "Hoàn tất xuất sắc"
            job.progress = 100
            db.commit()
            self.log(db, job_id, "Hoàn tất", "Quy trình tự động hóa 1-Click đã hoàn thành 100%!")

        except Exception as e:
            err_trace = traceback.format_exc()
            job.status = "FAILED"
            job.current_stage = "Thất bại"
            job.error_message = f"{str(e)}\n{err_trace}"
            db.commit()
            self.log(db, job_id, "Lỗi hệ thống", f"Lỗi: {str(e)}", level="ERROR")
            print(f"[Orchestrator] Job {job_id} failed: {err_trace}")
        finally:
            db.close()


orchestrator = WorkflowOrchestrator()
