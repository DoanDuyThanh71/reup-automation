import os
import requests
from typing import Dict, Any, Optional
from ..config import config
from ..services.facebook_client import FacebookPublisher

class PublisherAgent:
    """
    Agent 6: Handles multi-channel publishing to Facebook Pages/Reels and TikTok.
    """
    def __init__(self):
        self.fb = FacebookPublisher()

    def publish_to_facebook(
        self,
        video_path: str,
        title: str,
        caption: str,
        hashtags: str = "",
        affiliate_link: str = "",
        page_id: Optional[str] = None,
        page_token: Optional[str] = None,
        mode: Optional[str] = None
    ) -> Dict[str, Any]:
        p_id = page_id or config.get("FACEBOOK_PAGE_ID", "")
        p_token = page_token or config.get("FACEBOOK_PAGE_ACCESS_TOKEN", "")
        publish_mode = (mode or config.get("FACEBOOK_PUBLISH_MODE", "reel")).lower()

        if not p_id or not p_token:
            return {"success": False, "error": "Chưa cấu hình Facebook Page ID hoặc Page Access Token"}

        # Compose full post description
        desc_parts = [caption.strip()] if caption else []
        if hashtags and hashtags.strip():
            desc_parts.append(hashtags.strip())
        if affiliate_link and affiliate_link.strip():
            desc_parts.append(f"👉 Link mua sản phẩm chính hãng: {affiliate_link.strip()}")

        full_description = "\n\n".join(desc_parts)

        if publish_mode == "reel":
            res = self.fb.publish_reel(video_path, description=full_description, page_id=p_id, token=p_token)
        else:
            res = self.fb.publish_video(video_path, title=title, description=full_description, page_id=p_id, token=p_token)

        return res

    def publish_to_tiktok(
        self,
        video_path: str,
        title: str,
        caption: str,
        hashtags: str = ""
    ) -> Dict[str, Any]:
        webhook_url = config.get("TIKTOK_WEBHOOK_URL", "").strip()
        session_id = config.get("TIKTOK_SESSION_ID", "").strip()

        if not webhook_url and not session_id:
            return {"success": False, "error": "Chưa cấu hình TIKTOK_WEBHOOK_URL hoặc TIKTOK_SESSION_ID"}

        if webhook_url:
            # Deliver to automation webhook (n8n, Make, or custom microservice)
            payload = {
                "video_path": video_path,
                "title": title,
                "caption": caption,
                "hashtags": hashtags,
                "file_name": os.path.basename(video_path)
            }
            try:
                res = requests.post(webhook_url, json=payload, timeout=30)
                if res.status_code in (200, 201):
                    return {"success": True, "message": "Đã gửi video và caption tới TikTok Webhook thành công"}
                return {"success": False, "error": f"TikTok Webhook trả về mã {res.status_code}: {res.text}"}
            except Exception as e:
                return {"success": False, "error": f"Lỗi gọi TikTok Webhook: {str(e)}"}

        return {"success": True, "message": "Thông tin đăng TikTok đã sẵn sàng (Session ID)"}
