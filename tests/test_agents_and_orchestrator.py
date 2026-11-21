import os
import pytest
from unittest.mock import patch, MagicMock

from app.models import JobModel, LogModel
from app.config import config
from app.agents.dubbing_agent import DubbingAgent
from app.agents.orchestrator import WorkflowOrchestrator

def test_dubbing_agent_fallback_from_vbee_to_edge_tts(db_session, tmp_path):
    config.set("TTS_PROVIDER", "vbee")
    config.set("VBEE_REFRESH_TOKEN_COOKIE", "refresh_token=expired_cookie")

    srt_file = tmp_path / "sub.srt"
    srt_file.write_text("1\n00:00:00,000 --> 00:00:02,000\nXin chào Việt Nam.\n", encoding="utf-8")
    out_audio = tmp_path / "dub.mp3"

    agent = DubbingAgent()

    def fake_edge_speech(srt_path, output_path, voice=None, is_srt=True):
        with open(output_path, "wb") as f:
            f.write(b"FAKE_MP3_AUDIO")
        return output_path

    with patch.object(agent.vbee, "process_full_dubbing", side_effect=RuntimeError("Vbee token expired")), \
         patch.object(agent.edge_tts, "generate_speech", side_effect=fake_edge_speech):
        res = agent.run(str(srt_file), str(out_audio))
        assert res["success"] is True
        assert res["provider"] == "edge-tts"
        assert os.path.exists(out_audio)

def test_orchestrator_end_to_end_pipeline_with_auto_facebook(db_session, tmp_path, monkeypatch):
    import sys
    orch_mod = sys.modules["app.agents.orchestrator"]
    monkeypatch.setattr(orch_mod, "OUTPUT_DIR", str(tmp_path / "outputs"))

    job = JobModel(id="e2ejob01", source_url="https://v.douyin.com/e2etest/", status="PENDING")
    db_session.add(job)
    db_session.commit()

    orch = WorkflowOrchestrator()

    def mock_ingest(url, out_path):
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(b"FAKE_SOURCE_MP4")
        return {"success": True, "video_path": out_path, "file_size": 1024}

    def mock_transcribe(video_path, audio_path, srt_path):
        with open(audio_path, "wb") as f:
            f.write(b"FAKE_EXTRACTED_MP3")
        raw_srt = "1\n00:00:00,000 --> 00:00:03,000\n测试字幕\n"
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(raw_srt)
        return {"success": True, "audio_path": audio_path, "srt_path": srt_path, "raw_srt": raw_srt}

    def mock_content(raw_srt_path, out_srt_path, product_hint=None):
        vn_srt = "1\n00:00:00,000 --> 00:00:03,000\nPhụ đề tiếng Việt chuẩn\n"
        with open(out_srt_path, "w", encoding="utf-8") as f:
            f.write(vn_srt)
        return {
            "success": True,
            "translated_srt_path": out_srt_path,
            "translated_srt": vn_srt,
            "title": "SIÊU PHẨM GIA DỤNG MỚI NHẤT",
            "caption": "Xem ngay kẻo lỡ!",
            "hashtags": "#review #shopee",
            "product_keyword": "máy xay cầm tay",
            "affiliate_link": "https://shopee.vn/may-xay?sub_id=16550927460",
            "summary": "Máy xay tiện lợi"
        }

    def mock_dubbing(srt_path, out_audio_path, voice_code=None):
        with open(out_audio_path, "wb") as f:
            f.write(b"FAKE_DUBBED_MP3")
        return {"success": True, "audio_path": out_audio_path, "provider": "edge-tts", "voice": "vi-VN-HoaiMyNeural"}

    def mock_render(in_vid, dub_aud, srt_p, out_vid):
        with open(out_vid, "wb") as f:
            f.write(b"FAKE_FINAL_RENDERED_MP4")
        return {"success": True, "output_video_path": out_vid, "file_size": 2048}

    def mock_fb_pub(**kwargs):
        return {"success": True, "post_id": "fb_reel_123456"}

    with patch.object(orch.ingestion_agent, "run", side_effect=mock_ingest), \
         patch.object(orch.transcribe_agent, "run", side_effect=mock_transcribe), \
         patch.object(orch.content_agent, "run", side_effect=mock_content), \
         patch.object(orch.dubbing_agent, "run", side_effect=mock_dubbing), \
         patch.object(orch.render_agent, "run", side_effect=mock_render), \
         patch.object(orch.publisher_agent, "publish_to_facebook", side_effect=mock_fb_pub):

        orch.execute_pipeline(job_id="e2ejob01", auto_post_fb=True, auto_post_tt=False)

    updated = db_session.query(JobModel).filter(JobModel.id == "e2ejob01").first()
    assert updated.status == "COMPLETED"
    assert updated.progress == 100
    assert updated.title == "SIÊU PHẨM GIA DỤNG MỚI NHẤT"
    assert updated.published_facebook is True
    assert updated.facebook_post_id == "fb_reel_123456"
    assert os.path.exists(updated.output_video_path)

    logs = db_session.query(LogModel).filter(LogModel.job_id == "e2ejob01").all()
    assert len(logs) >= 6
