from typing import Dict, Any, Optional
from ..services.shopee_client import ShopeeAffiliateClient

class AffiliateAgent:
    """
    Agent 7 (Affiliate & E-Commerce Verification Agent):
    Dedicated agent responsible for:
    1. Searching Shopee products from video context / product keyword hints.
    2. Generating attributed Shopee Affiliate links via Open API GraphQL (`generateShortLink`),
       Portal Cookie GraphQL, or Attributed Deep-Link (`sub_id` + `utm_source=an_{sub_id}`).
    3. Auditing & repairing any un-attributed link so every video job is guaranteed
       to have a valid, testable Shopee Affiliate link.
    """
    def __init__(self):
        self.client = ShopeeAffiliateClient()

    def refresh_client(self):
        self.client = ShopeeAffiliateClient()

    def run(self, product_keyword: str, existing_link: Optional[str] = None, job_id: str = "reup") -> Dict[str, Any]:
        self.refresh_client()
        kw = (product_keyword or "đồ gia dụng thông minh").strip()
        campaign_tag = f"job_{job_id[:8]}"

        # Step 1: Resolve product URL if not provided
        if existing_link and existing_link.strip():
            candidate_url = existing_link.strip()
        else:
            candidate_url = self.client.search_product(kw) or f"https://shopee.vn/search?keyword={kw}"

        # Step 2: Convert to Affiliate Link
        affiliate_link = self.client.convert_to_affiliate_link(candidate_url, campaign_tag=campaign_tag)

        # Step 3: Verify & auto-heal if needed
        verification = self.client.verify_affiliate_link(affiliate_link, product_keyword=kw)
        if not verification.get("valid"):
            repaired_origin = self.client.search_product(kw)
            affiliate_link = self.client.convert_to_affiliate_link(repaired_origin, campaign_tag=campaign_tag)
            verification = self.client.verify_affiliate_link(affiliate_link, product_keyword=kw)

        return {
            "success": verification.get("valid", False),
            "product_keyword": kw,
            "origin_url": candidate_url,
            "affiliate_link": affiliate_link,
            "universal_redirect_link": verification.get("universal_redirect_link", affiliate_link),
            "method": verification.get("method", "attributed_deeplink"),
            "sub_id": verification.get("sub_id", self.client.sub_id),
            "is_short_link": verification.get("is_short_link", False),
            "verification": verification
        }
