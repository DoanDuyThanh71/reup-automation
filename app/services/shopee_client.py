import os
import urllib.parse
import requests
from typing import Dict, Any, Optional

class ShopeeAffiliateClient:
    """
    Client for searching products on Shopee and creating Shopee Affiliate links with custom Sub-ID.
    """
    def __init__(self, cookie: Optional[str] = None, sub_id: Optional[str] = None):
        from ..config import config
        self.cookie = cookie or config.get("SHOPEE_COOKIE", "")
        self.sub_id = sub_id or config.get("SHOPEE_SUB_ID", "16550927460")

    def test_connection(self) -> Dict[str, Any]:
        if not self.cookie:
            return {"success": True, "message": "Shopee Cookie chưa được cài đặt (chế độ tạo link cơ bản)", "has_cookie": False}
        return {"success": True, "message": "Shopee Cookie đã được cấu hình", "has_cookie": True, "sub_id": self.sub_id}

    def search_product(self, keyword: str) -> Optional[str]:
        """Searches Shopee for the best-selling product matching keyword and returns its URL."""
        if not keyword:
            return None

        encoded_kw = urllib.parse.quote(keyword)
        search_url = f"https://shopee.vn/api/v4/search/search_items?by=relevancy&keyword={encoded_kw}&limit=1&newest=0&order=desc&page_type=search&scenario=PAGE_GLOBAL_SEARCH&version=2"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": f"https://shopee.vn/search?keyword={encoded_kw}"
        }
        if self.cookie:
            headers["Cookie"] = self.cookie

        try:
            res = requests.get(search_url, headers=headers, timeout=10)
            if res.status_code == 200:
                data = res.json()
                items = data.get("items", [])
                if items:
                    item_info = items[0].get("item_basic", {})
                    itemid = item_info.get("itemid")
                    shopid = item_info.get("shopid")
                    name = item_info.get("name", "san-pham")
                    clean_name = urllib.parse.quote(name.replace(" ", "-")[:40])
                    if itemid and shopid:
                        return f"https://shopee.vn/{clean_name}-i.{shopid}.{itemid}"
        except Exception as e:
            print(f"[ShopeeAffiliateClient] Search error: {e}")

        # Fallback to search query link
        return f"https://shopee.vn/search?keyword={encoded_kw}"

    def convert_to_affiliate_link(self, product_url: str) -> str:
        """Appends affiliate tracking sub_id to product URL."""
        if not product_url:
            return ""
        separator = "&" if "?" in product_url else "?"
        return f"{product_url}{separator}sub_id={self.sub_id}"
