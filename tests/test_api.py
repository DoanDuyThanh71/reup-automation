import os
import pytest
from unittest.mock import patch
from app.models import JobModel

def test_serve_dashboard_ui(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "Reup Automation" in res.text
    assert "FACEBOOK_PAGE_ACCESS_TOKEN" in res.text
    assert "ASR_PROVIDER" in res.text

def test_health_endpoint_and_doctor(client, db_session):
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["database"] is True
    assert data["ffmpeg_binary"]

    from doctor import run_doctor
    assert run_doctor() == 0

def test_configs_endpoints_and_masking(client):
    # Save new configs via API
    payload = {
        "configs": {
            "FACEBOOK_PAGE_ID": "987654321",
            "FACEBOOK_PAGE_ACCESS_TOKEN": "EAAB_SUPER_SECRET_TOKEN_9999",
            "AI_MODEL": "gpt-4o-mini"
        }
    }
    res = client.post("/api/configs", json=payload)
    assert res.status_code == 200
    assert res.json()["success"] is True

    # Masked GET
    masked = client.get("/api/configs").json()
    assert masked["FACEBOOK_PAGE_ID"]["value"] == "987654321"
    assert "SUPER_SECRET" not in masked["FACEBOOK_PAGE_ACCESS_TOKEN"]["value"]

    # Raw GET for internal settings form hydration
    raw = client.get("/api/configs/raw").json()
    assert raw["FACEBOOK_PAGE_ACCESS_TOKEN"]["value"] == "EAAB_SUPER_SECRET_TOKEN_9999"

def test_create_list_and_delete_job_api(client):
    with patch("app.main.orchestrator.execute_pipeline"):
        res = client.post("/api/jobs", json={
            "source_url": "https://v.douyin.com/iY8Test/",
            "custom_product_hint": "bàn chải điện",
            "auto_post_facebook": True
        })
        assert res.status_code == 200
        job_data = res.json()
        job_id = job_data["id"]
        assert job_data["status"] == "PENDING"

        # List jobs
        jobs = client.get("/api/jobs").json()
        assert any(j["id"] == job_id for j in jobs)

        # Stats
        stats = client.get("/api/stats").json()
        assert stats["total_jobs"] >= 1

        # Delete job
        del_res = client.delete(f"/api/jobs/{job_id}")
        assert del_res.status_code == 200

def test_test_connection_endpoints(client):
    # Edge-TTS connection test
    res_tts = client.post("/api/test-connection", json={"target": "edge-tts"})
    assert res_tts.status_code == 200
    assert res_tts.json()["success"] is True

    # ASR connection test
    res_asr = client.post("/api/test-connection", json={
        "target": "asr",
        "custom_params": {"provider": "shopaikey", "api_key": "sk-asr-123", "model": "whisper-1"}
    })
    assert res_asr.status_code == 200
    assert res_asr.json()["success"] is True

def test_manual_publish_facebook_endpoint(client, db_session, tmp_path):
    vid = tmp_path / "ready.mp4"
    vid.write_bytes(b"MP4_DATA")

    job = JobModel(
        id="pubjob01",
        source_url="https://v.douyin.com/pub/",
        status="COMPLETED",
        output_video_path=str(vid),
        title="TIÊU ĐỀ ĐĂNG FB",
        caption="Caption đăng FB",
        hashtags="#fb #reels"
    )
    db_session.add(job)
    db_session.commit()

    with patch("app.main.orchestrator.publisher_agent.publish_to_facebook", return_value={"success": True, "post_id": "fb_post_555"}):
        res = client.post("/api/jobs/pubjob01/publish", json={
            "job_id": "pubjob01",
            "platform": "facebook",
            "publish_mode": "reel"
        })
        assert res.status_code == 200
        assert res.json()["post_id"] == "fb_post_555"
