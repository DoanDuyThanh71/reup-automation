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
    shopee = ShopeeAffiliateClient(
        cookie="SPC_U=1",
        sub_id="998877",
        affiliate_id="17374600599",
        app_id="",
        app_secret="",
    )
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {
        "items": [{"item_basic": {"itemid": 112233, "shopid": 4455, "name": "Quạt mini cầm tay"}}]
    }
    with patch("requests.get", return_value=mock_resp), \
         patch.object(shopee, "generate_short_link_cookie_gql", return_value=None):
        url = shopee.search_product("quạt mini")
        assert "i.4455.112233" in url
        aff_link = shopee.convert_to_affiliate_link(url)
        assert "s.shopee.vn/an_redir" in aff_link
        assert "affiliate_id=17374600599" in aff_link
        assert "sub_id=998877" in aff_link
        check = shopee.verify_affiliate_link(aff_link, product_keyword="quạt mini")
        assert check["valid"] is True


def test_shopee_cookie_json_array_parser_and_profile(db_session):
    json_cookies = json.dumps([
        {"domain": ".shopee.vn", "name": "SPC_U", "value": "16550927460"},
        {"domain": ".shopee.vn", "name": "SPC_ST", "value": "token_abc"},
        {"domain": ".shopee.vn", "name": "csrftoken", "value": "csrf_123"},
        {"domain": "affiliate.shopee.vn", "name": "_sapid", "value": "sap_456"},
    ])
    shopee = ShopeeAffiliateClient(cookie=json_cookies, sub_id="kenh71")
    assert "SPC_ST=token_abc" in shopee.cookie
    assert shopee.cookie_dict["csrftoken"] == "csrf_123"
    assert "\n" not in shopee.cookie

    mock_prof = MagicMock(status_code=200)
    mock_prof.json.return_value = {
        "code": 0,
        "msg": "success",
        "data": {
            "affiliate_id": "17374600599",
            "user_id": "16550927460",
            "shopee_user_name": "doanduythanh71",
            "nick_name": "Thành",
            "social_media_info": [{"user_name": "Kênh 71"}],
        },
    }
    with patch("requests.get", return_value=mock_prof):
        prof = shopee.fetch_affiliate_profile(force_refresh=True)
        assert prof is not None
        assert prof["affiliate_id"] == "17374600599"
        assert prof["shopee_user_name"] == "doanduythanh71"
        assert shopee.affiliate_id == "17374600599"

def test_shopee_open_api_signature_and_affiliate_agent(db_session):
    from app.agents.affiliate_agent import AffiliateAgent
    sig = ShopeeAffiliateClient.build_open_api_signature("12345", "secret99", 1700000000, '{"query":"test"}')
    assert len(sig) == 64

    agent = AffiliateAgent()
    with patch.object(agent.client, "search_product", return_value="https://shopee.vn/quat-mini-i.11.22"):
        res = agent.run(product_keyword="quạt tích điện mini", job_id="jobtest")
        assert res["success"] is True
        assert "sub_id=" in res["affiliate_link"] or "s.shopee.vn" in res["affiliate_link"]

# ==========================================
# 4. Vbee & Edge-TTS Tests
# ==========================================

def test_edge_tts_extract_clean_text_from_srt():
    srt = "1\n00:00:01,000 --> 00:00:03,000\nXin chào các bạn.\n\n2\n00:00:03,500 --> 00:00:05,000\nĐây là sản phẩm mới.\n"
    text = EdgeTTSClient.extract_clean_text_from_srt(srt)
    assert text == "Xin chào các bạn. Đây là sản phẩm mới."


# ==========================================
# 5. Security Fingerprint, TikTok & Quota Pool Tests
# ==========================================

def test_security_vault_encryption_and_fingerprints():
    from app.services.security_fingerprint import SecurityFingerprintManager

    raw_secret = "EAA_SUPER_SECRET_TOKEN_123456"
    enc = SecurityFingerprintManager.encrypt_secret(raw_secret)
    assert enc.startswith("ENC:v1:")
    assert raw_secret not in enc
    dec = SecurityFingerprintManager.decrypt_secret(enc)
    assert dec == raw_secret

    fp1 = SecurityFingerprintManager.secret_fingerprint(raw_secret)
    fp2 = SecurityFingerprintManager.secret_fingerprint(raw_secret)
    assert fp1 == fp2 and fp1.startswith("fp:")

    bfp = SecurityFingerprintManager.get_browser_fingerprint("uid_tt_test")
    assert bfp["fingerprint_id"].startswith("bfp-")
    assert "Chrome/" in bfp["ua"]

    vfp = SecurityFingerprintManager.get_video_anti_detect_params("job_abc")
    assert "eq=contrast=" in vfp["vf_snippet"]


def test_tiktok_cookie_json_parser_and_verify(db_session):
    from app.services.tiktok_client import TikTokClient

    raw_tt = json.dumps([
        {"domain": ".tiktok.com", "name": "sessionid", "value": "956b1c7c69619d11", "sameSite": None, "secure": True},
        {"domain": ".tiktok.com", "name": "uid_tt", "value": "uid_999", "sameSite": "no_restriction", "secure": True},
    ])
    tt = TikTokClient(cookie_or_session=raw_tt)
    assert "sessionid=956b1c7c69619d11" in tt.cookie_str
    assert len(tt.playwright_cookies) == 2
    assert tt.playwright_cookies[1]["sameSite"] == "None"

    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {
        "data": {"username": "tra_sua_nuong_71", "screen_name": "N1 Đoàn Duy Thành", "user_id_str": "73029"}
    }
    with patch("requests.get", return_value=mock_resp):
        acc = tt.verify_account()
        assert acc["success"] is True
        assert acc["username"] == "tra_sua_nuong_71"


def test_facebook_page_id_markdown_sanitizer():
    clean = FacebookPublisher.sanitize_page_id("[1058364167367881](https://developers.facebook.com/tools/explorer/)")
    assert clean == "1058364167367881"


def test_hardware_tts_advisor_tiers():
    from app.services.hardware_advisor import HardwareAdvisor

    res = HardwareAdvisor.inspect_and_recommend()
    assert "hardware" in res and "recommendation" in res
    assert res["recommendation"]["tier"] in ("ULTRA_GPU", "MID_GPU", "CPU_GOOD", "LOW_SPEC")
    assert res["recommendation"]["recommended_tts_provider"] in ("local", "edge-tts", "vbee")
