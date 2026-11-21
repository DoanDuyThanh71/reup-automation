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
from .dubbing_agent import DubbingAgent
from .render_agent import RenderAgent
from .publisher_agent import PublisherAgent

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
TEMP_DIR = os.path.join(BASE_DIR, "temp")

class WorkflowOrchestrator:
    """
    Master Multi-Agent Orchestrator. Coordinates the 6 specialized AI agents.
    """
    def __init__(self):
        self.ingestion_agent = IngestionAgent()
        self.transcribe_agent = TranscribeAgent()
        self.content_agent = ContentPolicyAgent()
        self.dubbing_agent = DubbingAgent()
        self.render_agent = RenderAgent()
        self.publisher_agent = PublisherAgent()
        self.log_listeners = []

    def register_log_listener(self, callback):
        """Registers a callback(dict) to receive real-time log events."""
        self.log_listeners.append(callback)

    def log(self, db: Session, job_id: str, stage: str, message: str, level: str = "INFO"):
        print(f"[{job_id[:8]}] [{stage}] {message}")
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

    def execute_pipeline(self, job_id: str, custom_product_hint: Optional[str] = None, voice_code: Optional[str] = None, auto_post_fb: bool = False, auto_post_tt: bool = False):
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
            # Stage 2: Transcribe Agent
            # -----------------------------------------------------------------
            job.status = "TRANSCRIBING"
            job.current_stage = "2. Trích xuất âm thanh & Nhận diện phụ đề"
            job.progress = 35
            db.commit()
            self.log(db, job_id, "Bóc tách giọng nói", "Đang trích xuất audio và chuyển đổi giọng nói thành SRT...")

            audio_path = os.path.join(job_dir, "extracted_audio.mp3")
            raw_srt_path = os.path.join(job_dir, "raw_transcript.srt")
            trans_res = self.transcribe_agent.run(job.source_video_path, audio_path, raw_srt_path)
            job.audio_path = trans_res["audio_path"]
            job.srt_raw_path = trans_res["srt_path"]
            db.commit()
            self.log(db, job_id, "Bóc tách giọng nói", "Đã tạo xong phụ đề SRT gốc")

            # -----------------------------------------------------------------
            # Stage 3: Content & Policy Agent
            # -----------------------------------------------------------------
            job.status = "TRANSLATING"
            job.current_stage = "3. AI Dịch tiếng Việt & Tạo tiêu đề/caption/affiliate"
            job.progress = 55
            db.commit()
            self.log(db, job_id, "AI Biên dịch & SEO", "AI đang dịch phụ đề sang tiếng Việt chuẩn và sinh tiêu đề viral...")

            translated_srt_path = os.path.join(job_dir, "vietnamese_sub.srt")
            content_res = self.content_agent.run(raw_srt_path, translated_srt_path, product_hint=custom_product_hint)

            job.srt_translated_path = content_res["translated_srt_path"]
            job.title = content_res["title"]
            job.caption = content_res["caption"]
            job.hashtags = content_res["hashtags"]
            job.product_keyword = content_res["product_keyword"]
            job.affiliate_link = content_res["affiliate_link"]
            job.transcript_summary = content_res["summary"]
            db.commit()
            self.log(db, job_id, "AI Biên dịch & SEO", f"Tiêu đề: {job.title}")

            # -----------------------------------------------------------------
            # Stage 4: Dubbing Agent
            # -----------------------------------------------------------------
            job.status = "DUBBING"
            job.current_stage = "4. Lồng tiếng AI (Vbee / Edge-TTS)"
            job.progress = 75
            db.commit()
            self.log(db, job_id, "Lồng tiếng AI", "Đang tạo giọng đọc lồng tiếng tiếng Việt...")

            dubbed_audio_path = os.path.join(job_dir, "dubbed_audio.mp3")
            dub_res = self.dubbing_agent.run(translated_srt_path, dubbed_audio_path, voice_code=voice_code)
            job.dubbed_audio_path = dub_res["audio_path"]
            db.commit()
            self.log(db, job_id, "Lồng tiếng AI", f"Lồng tiếng hoàn tất ({dub_res['provider']} - giọng {dub_res['voice']})")

            # -----------------------------------------------------------------
            # Stage 5: Render Agent
            # -----------------------------------------------------------------
            job.status = "RENDERING"
            job.current_stage = "5. Ghép video & Burn phụ đề nghệ thuật"
            job.progress = 90
            db.commit()
            self.log(db, job_id, "Render video", "Đang dùng FFmpeg ghép âm thanh và burn sub vàng viền đen...")

            output_video_path = os.path.join(job_dir, f"final_{job_id}.mp4")
            render_res = self.render_agent.run(job.source_video_path, dubbed_audio_path, translated_srt_path, output_video_path)
            job.output_video_path = render_res["output_video_path"]
            db.commit()
            self.log(db, job_id, "Render video", f"Render video thành công ({render_res['file_size'] / (1024*1024):.2f} MB)")

            # -----------------------------------------------------------------
            # Stage 6: Publisher Agent (Optional Auto-Publish)
            # -----------------------------------------------------------------
            should_post_fb = auto_post_fb or config.get_bool("FACEBOOK_AUTO_PUBLISH", False)
            should_post_tt = auto_post_tt or config.get_bool("TIKTOK_AUTO_PUBLISH", False)

            if should_post_fb or should_post_tt:
                job.status = "PUBLISHING"
                job.current_stage = "6. Tự động xuất bản lên mạng xã hội"
                db.commit()

            # Facebook
            if should_post_fb:
                self.log(db, job_id, "Đăng Facebook", "Đang tải video lên Facebook Page...")
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
                    self.log(db, job_id, "Đăng Facebook", f"Thành công! Post ID: {job.facebook_post_id}")
                else:
                    job.facebook_error = fb_res.get("error", "Lỗi không xác định")
                    self.log(db, job_id, "Đăng Facebook", f"Thất bại: {job.facebook_error}", level="ERROR")
                db.commit()

            # TikTok
            if should_post_tt:
                self.log(db, job_id, "Đăng TikTok", "Đang gửi nội dung sang TikTok...")
                tt_res = self.publisher_agent.publish_to_tiktok(
                    video_path=job.output_video_path,
                    title=job.title or "",
                    caption=job.caption or "",
                    hashtags=job.hashtags or ""
                )
                if tt_res.get("success"):
                    job.published_tiktok = True
                    self.log(db, job_id, "Đăng TikTok", "Gửi TikTok thành công!")
                else:
                    job.tiktok_error = tt_res.get("error", "Lỗi TikTok")
                    self.log(db, job_id, "Đăng TikTok", f"Thất bại: {job.tiktok_error}", level="ERROR")
                db.commit()

            # Pipeline Complete
            job.status = "COMPLETED"
            job.current_stage = "Hoàn tất xuất sắc"
            job.progress = 100
            db.commit()
            self.log(db, job_id, "Hoàn tất", "Quy trình xử lý video đã hoàn thành 100%!")

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
