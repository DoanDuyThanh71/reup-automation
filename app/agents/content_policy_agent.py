import os
from typing import Dict, Any, Optional
from ..services.ai_client import AIClient
from ..services.shopee_client import ShopeeAffiliateClient

class ContentPolicyAgent:
    """
    Agent 3: Handles AI Subtitle Translation, SEO Generation (Title/Caption/Hashtags),
    Shopee Affiliate Search, and Policy Sanitization.
    """
    def __init__(self):
        self.ai = AIClient()
        self.shopee = ShopeeAffiliateClient()

    def run(self, raw_srt_path: str, output_translated_srt_path: str, product_hint: Optional[str] = None) -> Dict[str, Any]:
        with open(raw_srt_path, "r", encoding="utf-8") as f:
            raw_srt = f.read()

        # Step 1: Translate SRT to Vietnamese
        translated_srt = self.ai.translate_srt(raw_srt)

        os.makedirs(os.path.dirname(output_translated_srt_path), exist_ok=True)
        with open(output_translated_srt_path, "w", encoding="utf-8") as f:
            f.write(translated_srt)

        # Step 2: Generate SEO Viral Metadata
        seo = self.ai.generate_seo_metadata(translated_srt, product_hint or "")
        product_keyword = seo.get("product_name_vn") or product_hint or "đồ gia dụng thông minh"

        # Step 3: Search Shopee Product & Convert to Affiliate Link
        product_url = self.shopee.search_product(product_keyword)
        affiliate_link = self.shopee.convert_to_affiliate_link(product_url)

        return {
            "success": True,
            "translated_srt_path": output_translated_srt_path,
            "translated_srt": translated_srt,
            "title": seo.get("title"),
            "caption": seo.get("caption"),
            "hashtags": seo.get("hashtags"),
            "product_keyword": product_keyword,
            "affiliate_link": affiliate_link,
            "summary": seo.get("summary")
        }
