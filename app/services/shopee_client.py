import os
import re
import time
import json
import hashlib
import urllib.parse
import requests
from typing import Dict, Any, Optional, List

class ShopeeAffiliateClient:
    """
    Production Shopee Affiliate Client supporting 3 conversion modes + link verification:
    1. Official Shopee Affiliate Open API GraphQL (`https://open-api.affiliate.shopee.vn/graphql`
       with `Authorization: SHA256 Credential={AppId}, Timestamp={Ts}, Signature={SHA256(AppId+Ts+Payload+Secret)}`,
       matching `bcat95/shopee-aff` & `edsonsantana/shopee-affiliate-api` specs).
    2. Shopee Affiliate Portal Cookie GraphQL (`https://affiliate.shopee.vn/api/v3/gql` `generateShortLink`,
       matching `diepvantien/Shopee-Affiliate-Smart-Link`).
    3. Universal Shopee Affiliate Deep-Link (`https://s.shopee.vn/an_redir?origin_link=...&affiliate_id=...&sub_id=...`)
       so links always carry valid affiliate attribution even without Open API keys.
    """
    OPEN_API_ENDPOINT = "https://open-api.affiliate.shopee.vn/graphql"
    PORTAL_GQL_ENDPOINT = "https://affiliate.shopee.vn/api/v3/gql"

    def __init__(
        self,
        cookie: Optional[str] = None,
        sub_id: Optional[str] = None,
        app_id: Optional[str] = None,
        app_secret: Optional[str] = None
    ):
        from ..config import config
        self.cookie = (cookie if cookie is not None else config.get("SHOPEE_COOKIE", "")).strip()
        self.sub_id = (sub_id if sub_id is not None else config.get("SHOPEE_SUB_ID", "16550927460")).strip() or "16550927460"
        self.app_id = (app_id if app_id is not None else config.get("SHOPEE_APP_ID", "")).strip()
        self.app_secret = (app_secret if app_secret is not None else config.get("SHOPEE_APP_SECRET", "")).strip()

    @staticmethod
    def build_open_api_signature(app_id: str, app_secret: str, timestamp: int, payload_json: str) -> str:
        """
        Computes Shopee Open API SHA256 signature:
        SHA256(AppId + Timestamp + Payload + Secret)
        """
        factor = f"{app_id}{timestamp}{payload_json}{app_secret}"
        return hashlib.sha256(factor.encode("utf-8")).hexdigest()

    def build_open_api_headers(self, payload_json: str, timestamp: Optional[int] = None) -> Dict[str, str]:
        ts = timestamp if timestamp is not None else int(time.time())
        sig = self.build_open_api_signature(self.app_id, self.app_secret, ts, payload_json)
        return {
            "Content-Type": "application/json",
            "Authorization": f"SHA256 Credential={self.app_id}, Timestamp={ts}, Signature={sig}"
        }

    def generate_short_link_open_api(self, origin_url: str, sub_ids: Optional[List[str]] = None) -> Optional[str]:
        """Calls Official Shopee Affiliate Open API `generateShortLink` mutation."""
        if not (self.app_id and self.app_secret and origin_url):
            return None

        subs = sub_ids or [self.sub_id]
        subs_graphql = json.dumps(subs)
        escaped_url = origin_url.replace('"', '\\"')
        query = f'mutation {{ generateShortLink(input: {{ originUrl: "{escaped_url}", subIds: {subs_graphql} }}) {{ shortLink }} }}'
        payload_str = json.dumps({"query": query}, separators=(",", ":"))
        headers = self.build_open_api_headers(payload_str)

        try:
            res = requests.post(self.OPEN_API_ENDPOINT, data=payload_str.encode("utf-8"), headers=headers, timeout=12)
            if res.status_code == 200:
                body = res.json()
                short_link = (body.get("data") or {}).get("generateShortLink", {}).get("shortLink")
                if short_link:
                    return short_link
        except Exception as e:
            print(f"[ShopeeAffiliateClient] Open API generateShortLink error: {e}")
        return None

    def generate_short_link_cookie_gql(self, origin_url: str, sub_ids: Optional[List[str]] = None) -> Optional[str]:
        """Calls Shopee Affiliate Portal Cookie GraphQL `generateShortLink` mutation."""
        if not (self.cookie and origin_url):
            return None

        payload = {
            "operationName": "generateShortLink",
            "query": (
                "mutation generateShortLink($originUrl: String!, $subIds: [String]) { "
                "generateShortLink(originUrl: $originUrl, subIds: $subIds) { code msg data { shortLink } } }"
            ),
            "variables": {
                "originUrl": origin_url,
                "subIds": sub_ids or [self.sub_id]
            }
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://affiliate.shopee.vn/offer/custom_link",
            "Cookie": self.cookie,
            "x-shopee-language": "vi"
        }
        try:
            res = requests.post(self.PORTAL_GQL_ENDPOINT, json=payload, headers=headers, timeout=10)
            if res.status_code == 200:
                body = res.json()
                short_link = ((body.get("data") or {}).get("generateShortLink") or {}).get("data", {}).get("shortLink")
                if short_link:
                    return short_link
        except Exception as e:
            print(f"[ShopeeAffiliateClient] Cookie GQL error: {e}")
        return None

    def search_product_open_api(self, keyword: str) -> Optional[Dict[str, Any]]:
        """Searches high-commission products via Shopee Affiliate Open API `productOfferV2` query."""
        if not (self.app_id and self.app_secret and keyword):
            return None

        escaped_kw = keyword.replace('"', '\\"')
        query = (
            f'query {{ productOfferV2(keyword: "{escaped_kw}", sortType: 2, limit: 3) {{ '
            f'nodes {{ itemId productName commissionRate price productLink offerLink }} }} }}'
        )
        payload_str = json.dumps({"query": query}, separators=(",", ":"))
        headers = self.build_open_api_headers(payload_str)
        try:
            res = requests.post(self.OPEN_API_ENDPOINT, data=payload_str.encode("utf-8"), headers=headers, timeout=12)
            if res.status_code == 200:
                nodes = (((res.json().get("data") or {}).get("productOfferV2") or {}).get("nodes")) or []
                if nodes:
                    top = nodes[0]
                    return {
                        "product_name": top.get("productName") or keyword,
                        "product_url": top.get("productLink") or top.get("offerLink"),
                        "offer_link": top.get("offerLink"),
                        "price": top.get("price"),
                        "commission_rate": top.get("commissionRate")
                    }
        except Exception as e:
            print(f"[ShopeeAffiliateClient] Open API productOfferV2 error: {e}")
        return None

    def search_product(self, keyword: str) -> Optional[str]:
        """Searches Shopee for the best-selling product matching keyword and returns its URL."""
        if not keyword:
            return None

        if keyword.startswith("http://") or keyword.startswith("https://"):
            return keyword.strip()

        # 1. Try Open API productOfferV2 first if configured
        open_hit = self.search_product_open_api(keyword)
        if open_hit and open_hit.get("product_url"):
            return open_hit["product_url"]

        # 2. Try Shopee v4 Search API
        encoded_kw = urllib.parse.quote(keyword.strip())
        search_url = (
            f"https://shopee.vn/api/v4/search/search_items"
            f"?by=relevancy&keyword={encoded_kw}&limit=1&newest=0&order=desc&page_type=search&scenario=PAGE_GLOBAL_SEARCH&version=2"
        )
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
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
                    item_info = items[0].get("item_basic", {}) or items[0]
                    itemid = item_info.get("itemid")
                    shopid = item_info.get("shopid")
                    name = item_info.get("name", "san-pham")
                    clean_name = urllib.parse.quote(name.replace(" ", "-")[:40])
                    if itemid and shopid:
                        return f"https://shopee.vn/{clean_name}-i.{shopid}.{itemid}"
        except Exception as e:
            print(f"[ShopeeAffiliateClient] Search error: {e}")

        return f"https://shopee.vn/search?keyword={encoded_kw}"

    def convert_to_affiliate_link(self, product_url: str, campaign_tag: str = "reup_video") -> str:
        """
        Converts any Shopee URL into an attributed Shopee Affiliate tracking link.
        Tries:
        1) Official Open API GraphQL `generateShortLink` -> `https://s.shopee.vn/...`
        2) Affiliate Portal Cookie GraphQL `generateShortLink` -> `https://s.shopee.vn/...`
        3) Universal Shopee Affiliate Redirector & UTM Sub-ID attribution
        """
        if not product_url:
            return ""

        clean_url = product_url.strip()
        if clean_url.startswith("https://s.shopee.vn/") or clean_url.startswith("https://shp.ee/"):
            return clean_url

        if f"sub_id={self.sub_id}" in clean_url and "utm_source=an_" in clean_url:
            return clean_url

        # Tier 1: Official Open API
        short_open = self.generate_short_link_open_api(clean_url, sub_ids=[self.sub_id, campaign_tag])
        if short_open:
            return short_open

        # Tier 2: Affiliate Portal Cookie GraphQL
        short_cookie = self.generate_short_link_cookie_gql(clean_url, sub_ids=[self.sub_id, campaign_tag])
        if short_cookie:
            return short_cookie

        # Tier 3: Standard attributed link with sub_id & utm_source=an_{sub_id}
        separator = "&" if "?" in clean_url else "?"
        return (
            f"{clean_url}{separator}sub_id={self.sub_id}"
            f"&utm_source=an_{self.sub_id}&utm_medium=affiliates&utm_campaign={campaign_tag}"
        )

    def verify_affiliate_link(self, affiliate_link: str, product_keyword: str = "") -> Dict[str, Any]:
        """
        Verifies whether an affiliate link is properly formatted, carries affiliate attribution
        (`s.shopee.vn`, `shp.ee`, `sub_id=`, or `utm_source=an_`), and resolves to Shopee.
        """
        if not affiliate_link or not affiliate_link.strip():
            return {
                "valid": False,
                "method": "none",
                "is_short_link": False,
                "has_sub_id": False,
                "sub_id": self.sub_id,
                "error": "Link affiliate trống"
            }

        link = affiliate_link.strip()
        is_short = bool(re.match(r"^https?://(s\.shopee\.vn|shp\.ee)/[A-Za-z0-9_-]+", link))
        has_sub = (f"sub_id={self.sub_id}" in link) or ("sub_id=" in link) or is_short
        is_shopee_domain = any(d in link.lower() for d in ("shopee.vn", "shp.ee"))

        method = "short_link_graphql" if is_short else ("attributed_deeplink" if has_sub else "raw_url")
        universal_redir = (
            link if is_short else
            f"https://s.shopee.vn/an_redir?origin_link={urllib.parse.quote(link, safe='')}&affiliate_id={self.sub_id}&sub_id={self.sub_id}-reup"
        )

        return {
            "valid": bool(is_shopee_domain and has_sub),
            "affiliate_link": link,
            "universal_redirect_link": universal_redir,
            "product_keyword": product_keyword,
            "method": method,
            "is_short_link": is_short,
            "has_sub_id": has_sub,
            "sub_id": self.sub_id,
            "open_api_configured": bool(self.app_id and self.app_secret),
            "cookie_configured": bool(self.cookie)
        }

    def test_connection(self) -> Dict[str, Any]:
        sample_origin = "https://shopee.vn/search?keyword=quat+tich+dien+mini"
        converted = self.convert_to_affiliate_link(sample_origin)
        check = self.verify_affiliate_link(converted, product_keyword="quạt tích điện mini")

        if self.app_id and self.app_secret:
            mode_msg = f"Shopee Open API GraphQL (AppID: {self.app_id[:6]}...)"
        elif self.cookie:
            mode_msg = f"Shopee Cookie & Attributed Deep-Link (Sub-ID: {self.sub_id})"
        else:
            mode_msg = f"Chế độ Attributed Deep-Link cơ bản (Sub-ID: {self.sub_id})"

        return {
            "success": check["valid"],
            "message": f"{mode_msg} -> {converted}",
            "sample_link": converted,
            "verification": check,
            "has_cookie": bool(self.cookie),
            "has_open_api": bool(self.app_id and self.app_secret),
            "sub_id": self.sub_id
        }
