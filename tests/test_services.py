import os
import json
import pytest
from unittest.mock import patch, MagicMock

from app.services.facebook_client import FacebookPublisher
from app.services.ai_client import AIClient
from app.services.vbee_client import VbeeClient
from app.services.edge_tts_client import EdgeTTSClient
from app.services.douyin_client import DouyinScraper
from app.services.shopee_client import ShopeeAffiliateClient

# ==========================================
# 1. Facebook Publisher Tests
# ==========================================

def test_facebook_test_connection_success():
    fb = FacebookPublisher(page_id="1001", page_access_token="EAA_TOKEN")
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"id": "1001", "name": "Fanpage Review Phim", "category": "Video Creator"}

    with patch("requests.get", return_value=mock_resp):
        res = fb.test_connection()
        assert res["success"] is True
        assert res["page_name"] == "Fanpage Review Phim"

def test_facebook_publish_reel_3_step_success(tmp_path):
    video_file = tmp_path / "reel.mp4"
    video_file.write_bytes(b"fake_mp4_content_12345")

    fb = FacebookPublisher(page_id="1001", page_access_token="EAA_TOKEN")

    init_resp = MagicMock(status_code=200)
    init_resp.json.return_value = {"video_id": "vid_888", "upload_url": "https://rupload.facebook.com/video-upload/vid_888"}

    upload_resp = MagicMock(status_code=200, text="OK")

    finish_resp = MagicMock(status_code=200)
    finish_resp.json.return_value = {"success": True}

    with patch("requests.post", side_effect=[init_resp, upload_resp, finish_resp]) as mock_post:
        res = fb.publish_reel(str(video_file), description="Review cực cuốn #reels")
        assert res["success"] is True
        assert res["post_id"] == "vid_888"
        assert mock_post.call_count == 3

def test_facebook_publish_reel_fallback_to_video(tmp_path):
    video_file = tmp_path / "video.mp4"
    video_file.write_bytes(b"fake_mp4_content")

    fb = FacebookPublisher(page_id="1001", page_access_token="EAA_TOKEN")

    # Step 1 fails (e.g. page not eligible for reels) -> falls back to publish_video
    init_fail = MagicMock(status_code=400, text="Reels not enabled")
    init_fail.json.return_value = {"error": {"message": "Reels not enabled"}}

    video_ok = MagicMock(status_code=200)
    video_ok.json.return_value = {"id": "post_video_777"}

    with patch("requests.post", side_effect=[init_fail, video_ok]):
        res = fb.publish_reel(str(video_file), description="Video fallback test")
        assert res["success"] is True
        assert res["post_id"] == "post_video_777"

# ==========================================
# 2. AI Client & Policy Filter Tests
# ==========================================

def test_ai_policy_sanitizer(db_session):
    ai = AIClient(base_url="https://9router.n8n71.com/v1", api_key="sk-test", model="AiFF")
    raw = "Hắn định giết và đánh nhau đến chết sau khi lừa đảo và dùng súng đạn."
    clean = ai.sanitize_policy_words(raw)
    assert "chết" not in clean.lower()
    assert "giết" not in clean.lower()
    assert "đăng xuất" in clean.lower()
    assert "tác động vật lý" in clean.lower()
    assert "úp sọt" in clean.lower()
    assert "đồ chơi nguy hiểm" in clean.lower()

def test_ai_translate_srt_and_seo(db_session):
    ai = AIClient(base_url="https://9router.n8n71.com/v1", api_key="sk-test", model="AiFF")

    mock_srt_reply = "```srt\n1\n00:00:00,500 --> 00:00:03,000\nSản phẩm này đánh nhau cực mạnh.\n```"
    mock_seo_reply = json.dumps({
        "title": "PHÁT HIỆN BÍ MẬT KHIẾN KẺ XẤU CHẾT LẶNG",
        "caption": "Màn đánh nhau kịch tính ở cuối video!",
        "hashtags": "#review #douyin",
        "product_name_vn": "quạt tích điện mini",
        "category": "Gia Dụng",
        "summary": "Tóm tắt video"
    })

    with patch.object(ai, "_call_chat", side_effect=[mock_srt_reply, mock_seo_reply]):
        translated = ai.translate_srt("1\n00:00:00,500 --> 00:00:03,000\n这很厉害。")
        assert "00:00:00,500 --> 00:00:03,000" in translated
        assert "tác động vật lý" in translated
        assert "```" not in translated

        seo = ai.generate_seo_metadata(translated)
        assert "đăng xuất" in seo["title"].lower()
        assert "tác động vật lý" in seo["caption"].lower()
        assert seo["product_name_vn"] == "quạt tích điện mini"

# ==========================================
# 3. Douyin Scraper & Shopee Affiliate Tests
# ==========================================

def test_douyin_extract_url_from_share_text(db_session):
    raw_share = "7.41 复制打开抖音，看看【好物分享】https://v.douyin.com/iY8AbCd/ 真的太好用了！"
    extracted = DouyinScraper.extract_url(raw_share)
    assert extracted == "https://v.douyin.com/iY8AbCd/"

def test_shopee_affiliate_search_and_convert(db_session):
    shopee = ShopeeAffiliateClient(cookie="SPC_U=1", sub_id="998877")
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {
        "items": [{"item_basic": {"itemid": 112233, "shopid": 4455, "name": "Quạt mini cầm tay"}}]
    }
    with patch("requests.get", return_value=mock_resp):
        url = shopee.search_product("quạt mini")
        assert "i.4455.112233" in url
        aff_link = shopee.convert_to_affiliate_link(url)
        assert "sub_id=998877" in aff_link

# ==========================================
# 4. Vbee & Edge-TTS Tests
# ==========================================

def test_edge_tts_extract_clean_text_from_srt():
    srt = "1\n00:00:01,000 --> 00:00:03,000\nXin chào các bạn.\n\n2\n00:00:03,500 --> 00:00:05,000\nĐây là sản phẩm mới.\n"
    text = EdgeTTSClient.extract_clean_text_from_srt(srt)
    assert text == "Xin chào các bạn. Đây là sản phẩm mới."
