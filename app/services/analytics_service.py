from typing import Dict, Any, List
from sqlalchemy.orm import Session
from ..models import JobModel
from ..config import config
from .facebook_client import FacebookPublisher
from .tiktok_client import TikTokClient
from .shopee_client import ShopeeAffiliateClient
from .quota_pool import QuotaPoolManager
from .security_fingerprint import SecurityFingerprintManager


class AnalyticsService:
    """
    Unified Analytics & Tracking Service across:
    - Facebook Fanpage & Reels (`Kênh 71`)
    - TikTok Creator Profile (`@tra_sua_nuong_71`)
    - Shopee Affiliate Attribution (`@doanduythanh71` • `17374600599`)
    - AI/Gemini Multi-Key Quota Pool & Security Fingerprints
    """

    def collect_dashboard_analytics(self, db: Session) -> Dict[str, Any]:
        # 1. Local Job Pipeline Summary
        jobs: List[JobModel] = db.query(JobModel).order_by(JobModel.created_at.desc()).limit(50).all()
        total_jobs = db.query(JobModel).count()
        completed_jobs = db.query(JobModel).filter(JobModel.status == "COMPLETED").count()
        fb_jobs = db.query(JobModel).filter(JobModel.published_facebook == True).count()
        tt_jobs = db.query(JobModel).filter(JobModel.published_tiktok == True).count()
        aff_jobs = db.query(JobModel).filter(JobModel.affiliate_link.isnot(None), JobModel.affiliate_link != "").count()

        # 2. Facebook Page Live Metrics & Video Views
        fb_client = FacebookPublisher(
            page_id=config.get("FACEBOOK_PAGE_ID"),
            page_access_token=config.get("FACEBOOK_PAGE_ACCESS_TOKEN"),
        )
        fb_analytics = fb_client.fetch_page_analytics(limit=10)

        # 3. TikTok Profile Live Metrics
        tt_client = TikTokClient()
        tt_analytics = tt_client.fetch_analytics()

        # 4. Shopee Affiliate Status
        shopee_client = ShopeeAffiliateClient()
        shopee_prof = shopee_client.fetch_affiliate_profile() if shopee_client.cookie else None
        shopee_summary = {
            "connected": bool(shopee_prof or shopee_client.affiliate_id),
            "affiliate_id": shopee_client.affiliate_id,
            "sub_id": shopee_client.sub_id,
            "username": (shopee_prof or {}).get("shopee_user_name") or "doanduythanh71",
            "cookie_fingerprint": SecurityFingerprintManager.secret_fingerprint(shopee_client.cookie),
            "attributed_videos_count": aff_jobs,
        }

        # 5. Quota & Security Fingerprint Summary
        quota_summary = QuotaPoolManager.detect_local_quota_gateways()

        recent_published = [
            {
                "job_id": j.id,
                "title": j.title or j.source_url,
                "status": j.status,
                "product_keyword": j.product_keyword,
                "affiliate_link": j.affiliate_link,
                "published_facebook": j.published_facebook,
                "facebook_post_id": j.facebook_post_id,
                "facebook_url": f"https://www.facebook.com/{j.facebook_post_id}" if j.facebook_post_id else None,
                "published_tiktok": j.published_tiktok,
                "tiktok_post_id": j.tiktok_post_id,
                "created_at": j.created_at.isoformat() if j.created_at else None,
            }
            for j in jobs[:15]
        ]

        return {
            "overview": {
                "total_jobs": total_jobs,
                "completed_jobs": completed_jobs,
                "facebook_published_jobs": fb_jobs,
                "tiktok_published_jobs": tt_jobs,
                "affiliate_attributed_jobs": aff_jobs,
                "total_fb_views": fb_analytics.get("total_views", 0),
                "total_fb_likes": fb_analytics.get("total_likes", 0),
                "total_tt_followers": (tt_analytics.get("stats") or {}).get("followerCount", 0),
                "total_tt_hearts": (tt_analytics.get("stats") or {}).get("heartCount", 0),
            },
            "facebook": fb_analytics,
            "tiktok": tt_analytics,
            "shopee": shopee_summary,
            "quota_pool": quota_summary,
            "recent_jobs": recent_published,
        }
