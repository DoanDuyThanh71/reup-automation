import pytest
from app.models import JobModel, ConfigModel, LogModel
from app.config import config

def test_job_model_creation_and_to_dict(db_session):
    job = JobModel(
        id="job123",
        source_url="https://v.douyin.com/test123/",
        status="COMPLETED",
        current_stage="Hoàn tất",
        progress=100,
        output_video_path="/tmp/final.mp4",
        srt_translated_path="/tmp/sub.srt",
        title="TIÊU ĐỀ TEST",
        published_facebook=True,
        facebook_post_id="fb_999"
    )
    db_session.add(job)
    db_session.commit()

    d = job.to_dict()
    assert d["id"] == "job123"
    assert d["status"] == "COMPLETED"
    assert d["has_video"] is True
    assert d["video_url"] == "/api/jobs/job123/video"
    assert d["srt_url"] == "/api/jobs/job123/srt"
    assert d["published_facebook"] is True
    assert d["facebook_post_id"] == "fb_999"

def test_config_manager_defaults_and_persistence(db_session):
    assert config.get("AI_MODEL") == "AiFF"
    assert config.get("FACEBOOK_PUBLISH_MODE") == "reel"
    assert config.get_bool("FACEBOOK_AUTO_PUBLISH") is False

    config.set("FACEBOOK_AUTO_PUBLISH", "true")
    assert config.get_bool("FACEBOOK_AUTO_PUBLISH") is True

    config.set_many({
        "FACEBOOK_PAGE_ID": "123456789",
        "FACEBOOK_PAGE_ACCESS_TOKEN": "EAABsbCS1iHgBO1234567890SECRET"
    })
    assert config.get("FACEBOOK_PAGE_ID") == "123456789"
    assert config.get("FACEBOOK_PAGE_ACCESS_TOKEN") == "EAABsbCS1iHgBO1234567890SECRET"

def test_config_secret_masking(db_session):
    config.set("FACEBOOK_PAGE_ACCESS_TOKEN", "EAABsbCS1iHgBO1234567890SECRET")
    masked_all = config.get_all(mask_secrets=True)
    raw_all = config.get_all(mask_secrets=False)

    masked_val = masked_all["FACEBOOK_PAGE_ACCESS_TOKEN"]["value"]
    assert "SECRET" not in masked_val or "*" in masked_val
    assert masked_val.startswith("EAAB")
    assert raw_all["FACEBOOK_PAGE_ACCESS_TOKEN"]["value"] == "EAABsbCS1iHgBO1234567890SECRET"
