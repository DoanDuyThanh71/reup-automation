from typing import Dict, Any, Optional
from ..config import config
from ..services.facebook_client import FacebookPublisher
from ..services.tiktok_client import TikTokClient


class PublisherAgent:
    """
    Agent 6: Handles multi-channel publishing to Facebook Pages/Reels (with auto Affiliate comment)
    and TikTok Studio (via Cookie + Browser Fingerprint or Webhook).
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

        desc_parts = [caption.strip()] if caption else []
        if hashtags and hashtags.strip():
            desc_parts.append(hashtags.strip())
        if affiliate_link and affiliate_link.strip():
            desc_parts.append(f"👉 Mua ngay tại Shopee chính hãng: {affiliate_link.strip()}")

        full_description = "\n\n".join(desc_parts)
        aff_comment = (
            f"🔥 Link sản phẩm chính hãng ưu đãi tại đây nhé cả nhà:\n{affiliate_link.strip()}"
            if (affiliate_link and affiliate_link.strip())
            else None
        )

        if publish_mode == "reel":
            return self.fb.publish_reel(
                video_path,
                description=full_description,
                page_id=p_id,
                token=p_token,
                affiliate_comment=aff_comment,
            )
        return self.fb.publish_video(
            video_path,
            title=title,
            description=full_description,
            page_id=p_id,
            token=p_token,
            affiliate_comment=aff_comment,
        )

    def publish_to_tiktok(
        self,
        video_path: str,
        title: str,
        caption: str,
        hashtags: str = ""
    ) -> Dict[str, Any]:
        tt = TikTokClient()
        return tt.publish_video(video_path=video_path, title=title, caption=caption, hashtags=hashtags)
