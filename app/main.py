import os
import uuid
import asyncio
import requests
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .database import get_db, Base, engine
from .models import JobModel, LogModel, JobCreate, JobResponse, ConfigUpdate, TestConnectionRequest, ManualPublishRequest
from .config import config
from .agents.orchestrator import orchestrator
from .services.facebook_client import FacebookPublisher
from .services.ai_client import AIClient
from .services.vbee_client import VbeeClient
from .services.edge_tts_client import EdgeTTSClient
from .services.shopee_client import ShopeeAffiliateClient

# Initialize SQLite tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Reup Automation API",
    description="Hệ thống tự động hóa làm video Douyin/TikTok sang tiếng Việt, lồng tiếng, burn sub và auto đăng Facebook & TikTok",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Active WebSocket connections for live logs
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)

manager = ConnectionManager()

def _on_orchestrator_log(payload: dict):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(manager.broadcast(payload))
    except Exception:
        pass

orchestrator.register_log_listener(_on_orchestrator_log)

# ==========================================
# REST API: Jobs
# ==========================================

@app.post("/api/jobs", response_model=JobResponse)
def create_job(payload: JobCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    if not payload.source_url or not payload.source_url.strip():
        raise HTTPException(status_code=400, detail="source_url không được để trống")

    job_id = str(uuid.uuid4())[:12]
    new_job = JobModel(
        id=job_id,
        source_url=payload.source_url.strip(),
        status="PENDING",
        current_stage="Đang chờ xử lý trong hàng đợi",
        progress=0
    )
    db.add(new_job)
    db.commit()
    db.refresh(new_job)

    # Launch pipeline in background task
    background_tasks.add_task(
        orchestrator.execute_pipeline,
        job_id=job_id,
        custom_product_hint=payload.custom_product_hint,
        voice_code=payload.voice_code,
        auto_post_fb=payload.auto_post_facebook or False,
        auto_post_tt=payload.auto_post_tiktok or False
    )

    return new_job.to_dict()

@app.get("/api/jobs")
def list_jobs(status: Optional[str] = None, limit: int = 50, db: Session = Depends(get_db)):
    query = db.query(JobModel).order_by(JobModel.created_at.desc())
    if status and status.upper() != "ALL":
        query = query.filter(JobModel.status == status.upper())
    jobs = query.limit(limit).all()
    return [j.to_dict() for j in jobs]

@app.get("/api/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(JobModel).filter(JobModel.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy Job")
    return job.to_dict()

@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(JobModel).filter(JobModel.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy Job")
    db.delete(job)
    db.commit()
    return {"success": True, "message": f"Đã xóa Job {job_id}"}

@app.get("/api/logs")
def get_recent_logs(limit: int = 100, db: Session = Depends(get_db)):
    logs = db.query(LogModel).order_by(LogModel.created_at.desc()).limit(limit).all()
    return [
        {
            "id": l.id,
            "job_id": l.job_id,
            "stage": l.stage,
            "message": l.message,
            "level": l.level,
            "created_at": l.created_at.isoformat() if l.created_at else None
        }
        for l in reversed(logs)
    ]

@app.get("/api/jobs/{job_id}/logs")
def get_job_logs(job_id: str, db: Session = Depends(get_db)):
    logs = db.query(LogModel).filter(LogModel.job_id == job_id).order_by(LogModel.created_at.asc()).all()
    return [
        {
            "id": l.id,
            "job_id": l.job_id,
            "stage": l.stage,
            "message": l.message,
            "level": l.level,
            "created_at": l.created_at.isoformat() if l.created_at else None
        }
        for l in logs
    ]

@app.get("/api/jobs/{job_id}/video")
def get_job_video(job_id: str, db: Session = Depends(get_db)):
    job = db.query(JobModel).filter(JobModel.id == job_id).first()
    if not job or not job.output_video_path or not os.path.exists(job.output_video_path):
        raise HTTPException(status_code=404, detail="Video chưa được render hoặc không tồn tại")
    return FileResponse(job.output_video_path, media_type="video/mp4", filename=f"video_{job_id}.mp4")

@app.get("/api/jobs/{job_id}/srt")
def get_job_srt(job_id: str, db: Session = Depends(get_db)):
    job = db.query(JobModel).filter(JobModel.id == job_id).first()
    if not job or not job.srt_translated_path or not os.path.exists(job.srt_translated_path):
        raise HTTPException(status_code=404, detail="File phụ đề chưa sẵn sàng")
    return FileResponse(job.srt_translated_path, media_type="text/plain", filename=f"sub_{job_id}.srt")

@app.post("/api/jobs/{job_id}/publish")
def manual_publish(job_id: str, payload: ManualPublishRequest, db: Session = Depends(get_db)):
    job = db.query(JobModel).filter(JobModel.id == job_id).first()
    if not job or not job.output_video_path or not os.path.exists(job.output_video_path):
        raise HTTPException(status_code=400, detail="Video chưa được tạo hoàn chỉnh để đăng bài")

    platform = payload.platform.lower()
    title = payload.title or job.title or "Video Review"
    caption = payload.caption or job.caption or ""
    hashtags = payload.hashtags or job.hashtags or ""

    if platform == "facebook":
        publisher = orchestrator.publisher_agent
        res = publisher.publish_to_facebook(
            video_path=job.output_video_path,
            title=title,
            caption=caption,
            hashtags=hashtags,
            affiliate_link=job.affiliate_link or "",
            page_id=payload.page_id,
            page_token=payload.page_token,
            mode=payload.publish_mode or "reel"
        )
        if res.get("success"):
            job.published_facebook = True
            job.facebook_post_id = str(res.get("post_id", ""))
            job.facebook_error = None
            db.commit()
            return {"success": True, "message": "Đã xuất bản lên Facebook thành công!", "post_id": job.facebook_post_id}
        else:
            job.facebook_error = res.get("error", "Lỗi đăng bài")
            db.commit()
            raise HTTPException(status_code=400, detail=job.facebook_error)

    elif platform == "tiktok":
        publisher = orchestrator.publisher_agent
        res = publisher.publish_to_tiktok(
            video_path=job.output_video_path,
            title=title,
            caption=caption,
            hashtags=hashtags
        )
        if res.get("success"):
            job.published_tiktok = True
            job.tiktok_error = None
            db.commit()
            return {"success": True, "message": "Đã gửi lên TikTok thành công!"}
        else:
            job.tiktok_error = res.get("error")
            db.commit()
            raise HTTPException(status_code=400, detail=job.tiktok_error)

    raise HTTPException(status_code=400, detail=f"Nền tảng {platform} không được hỗ trợ")

# ==========================================
# REST API: Configs & Credentials
# ==========================================

@app.get("/api/configs")
def get_configs():
    return config.get_all(mask_secrets=True)

@app.get("/api/configs/raw")
def get_raw_configs():
    return config.get_all(mask_secrets=False)

@app.post("/api/configs")
def update_configs(payload: ConfigUpdate):
    config.set_many(payload.configs)
    return {"success": True, "message": "Đã lưu cài đặt cấu hình thành công!"}

@app.post("/api/test-connection")
def test_connection(payload: TestConnectionRequest):
    target = payload.target.lower()
    params = payload.custom_params or {}

    if target == "facebook":
        p_id = params.get("page_id") or config.get("FACEBOOK_PAGE_ID")
        token = params.get("page_token") or config.get("FACEBOOK_PAGE_ACCESS_TOKEN")
        fb = FacebookPublisher()
        return fb.test_connection(page_id=p_id, token=token)

    elif target == "ai":
        base_url = params.get("base_url") or config.get("AI_BASE_URL")
        api_key = params.get("api_key") or config.get("AI_API_KEY")
        model = params.get("model") or config.get("AI_MODEL")
        ai = AIClient(base_url=base_url, api_key=api_key, model=model)
        return ai.test_connection()

    elif target == "asr":
        provider = params.get("provider") or config.get("ASR_PROVIDER", "shopaikey")
        base_url = (params.get("base_url") or config.get("ASR_BASE_URL", "https://api.shopaikey.com/v1")).rstrip("/")
        api_key = params.get("api_key") or config.get("ASR_API_KEY", "")
        model = params.get("model") or config.get("ASR_MODEL", "whisper-1")
        if provider == "local":
            return {"success": True, "message": f"ASR Local ({model}) sẵn sàng sử dụng"}
        if not api_key:
            return {"success": False, "error": "Chưa nhập ASR_API_KEY để xác thực dịch vụ Speech-to-Text"}
        return {
            "success": True,
            "message": f"Đã cấu hình ASR ({provider}) tại {base_url} với model {model}"
        }

    elif target == "vbee":
        vbee = VbeeClient(refresh_token_cookie=params.get("cookie"))
        return vbee.test_connection()

    elif target == "edge-tts":
        tts = EdgeTTSClient()
        return tts.test_connection()

    elif target == "shopee":
        shopee = ShopeeAffiliateClient(cookie=params.get("cookie"), sub_id=params.get("sub_id"))
        return shopee.test_connection()

    raise HTTPException(status_code=400, detail=f"Mục tiêu kiểm tra '{target}' không hợp lệ")

# ==========================================
# REST API: Stats
# ==========================================

@app.get("/api/stats")
def get_stats(db: Session = Depends(get_db)):
    total = db.query(JobModel).count()
    completed = db.query(JobModel).filter(JobModel.status == "COMPLETED").count()
    failed = db.query(JobModel).filter(JobModel.status == "FAILED").count()
    processing = db.query(JobModel).filter(JobModel.status.in_(["PENDING", "INGESTING", "TRANSCRIBING", "TRANSLATING", "DUBBING", "RENDERING", "PUBLISHING"])).count()
    fb_published = db.query(JobModel).filter(JobModel.published_facebook == True).count()
    tt_published = db.query(JobModel).filter(JobModel.published_tiktok == True).count()

    return {
        "total_jobs": total,
        "completed_jobs": completed,
        "failed_jobs": failed,
        "processing_jobs": processing,
        "facebook_published": fb_published,
        "tiktok_published": tt_published
    }

# ==========================================
# WebSocket: Live Logs
# ==========================================

@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# ==========================================
# Static Files & Dashboard UI
# ==========================================

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    def serve_dashboard():
        index_file = os.path.join(STATIC_DIR, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
        return {"message": "Reup Automation API is running. UI not found."}
