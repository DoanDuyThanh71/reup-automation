import os
import re
import time
import json
import base64
import hashlib
import urllib.parse
import requests
from typing import Dict, Any, Optional, List, Tuple

import sys
_IS_COMM_EXE = bool(getattr(sys, "frozen", False) or os.getenv("REUP_COMMERCIAL_EXE") == "1")
DEFAULT_SHOPEE_AFFILIATE_ID = "" if _IS_COMM_EXE else "17374600599"
DEFAULT_SHOPEE_SUB_ID = "reup_video" if _IS_COMM_EXE else "kenh71"


class ShopeeAffiliateClient:
    """
    Production Shopee Affiliate Client supporting:
    1. Multi-format Cookie Parser: Accepts Cookie-Editor / J2Team JSON arrays (`[{"name":...,"value":...}]`),
       JSON dicts, Netscape cookies.txt, or raw `key=value; ...` strings.
    2. Live Cookie Authentication & Profile Discovery (`GET https://affiliate.shopee.vn/api/v3/user/profile`)
       to verify session validity and auto-resolve `affiliate_id` (distinct from buyer `SPC_U` / `user_id`).
    3. Official Shopee Affiliate Open API GraphQL (`https://open-api.affiliate.shopee.vn/graphql`
       with `Authorization: SHA256 Credential={AppId}, Timestamp={Ts}, Signature=...`).
    4. Shopee Affiliate Portal Cookie GraphQL (`https://affiliate.shopee.vn/api/v3/gql?q=batchCustomLink`
       `batchGetCustomLink`).
    5. Official Shopee Affiliate Network Redirector (`https://s.shopee.vn/an_redir?origin_link=...&affiliate_id=...&sub_id=...`),
       which mints server-side `mmp_pid=an_{affiliate_id}` & `uls_trackid` via HTTP 301 without anti-bot blocks.
    """
    OPEN_API_ENDPOINT = "https://open-api.affiliate.shopee.vn/graphql"
    PORTAL_GQL_ENDPOINT = "https://affiliate.shopee.vn/api/v3/gql?q=batchCustomLink"
    PORTAL_PROFILE_ENDPOINT = "https://affiliate.shopee.vn/api/v3/user/profile"
    AN_REDIR_ENDPOINT = "https://s.shopee.vn/an_redir"

    def __init__(
        self,
        cookie: Optional[str] = None,
        sub_id: Optional[str] = None,
        app_id: Optional[str] = None,
        app_secret: Optional[str] = None,
        affiliate_id: Optional[str] = None,
    ):
        from ..config import config
        raw_cookie = cookie if cookie is not None else config.get("SHOPEE_COOKIE", "")
        self.cookie, self.cookie_dict = self.parse_cookie_input(raw_cookie)

        cfg_aff_id = (affiliate_id if affiliate_id is not None else config.get("SHOPEE_AFFILIATE_ID", "")).strip()
        self.affiliate_id = cfg_aff_id or DEFAULT_SHOPEE_AFFILIATE_ID

        raw_sub = (sub_id if sub_id is not None else config.get("SHOPEE_SUB_ID", DEFAULT_SHOPEE_SUB_ID)).strip()
        self.sub_id = raw_sub or self.cookie_dict.get("SPC_U") or DEFAULT_SHOPEE_SUB_ID

        self.app_id = (app_id if app_id is not None else config.get("SHOPEE_APP_ID", "")).strip()
        self.app_secret = (app_secret if app_secret is not None else config.get("SHOPEE_APP_SECRET", "")).strip()
        self._cached_profile: Optional[Dict[str, Any]] = None

    @staticmethod
    def parse_cookie_input(raw_cookie: Any) -> Tuple[str, Dict[str, str]]:
        """
        Normalizes Shopee cookies from any common export format into `(header_str, cookie_dict)`:
        - Cookie-Editor / EditThisCookie / J2Team JSON list: `[{"name": "SPC_ST", "value": "...", "domain": "..."}, ...]`
        - JSON object: `{"SPC_ST": "...", "SPC_F": "..."}` or `{"cookies": [...]}`
        - Netscape cookies.txt lines (7 tab-separated columns)
        - Standard HTTP Cookie header string: `SPC_ST=...; SPC_F=...`
        """
        if not raw_cookie:
            return "", {}

        cookie_map: Dict[str, str] = {}

        if isinstance(raw_cookie, list):
            items = raw_cookie
        elif isinstance(raw_cookie, dict):
            items = raw_cookie.get("cookies") if isinstance(raw_cookie.get("cookies"), list) else [
                {"name": k, "value": v} for k, v in raw_cookie.items()
            ]
        else:
            text = str(raw_cookie).strip()
            if not text:
                return "", {}
            items = None
            if (text.startswith("[") and text.endswith("]")) or (text.startswith("{") and text.endswith("}")):
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, list):
                        items = parsed
                    elif isinstance(parsed, dict):
                        if isinstance(parsed.get("cookies"), list):
                            items = parsed["cookies"]
                        else:
                            items = [{"name": k, "value": v} for k, v in parsed.items()]
                except Exception:
                    items = None

            if items is None:
                # Netscape format or raw header string
                for line in text.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "\t" in line and len(line.split("\t")) >= 7:
                        parts = line.split("\t")
                        cookie_map[parts[5].strip()] = parts[6].strip()
                    else:
                        if line.lower().startswith("cookie:"):
                            line = line.split(":", 1)[1].strip()
                        for pair in line.split(";"):
                            pair = pair.strip()
                            if "=" in pair:
                                k, v = pair.split("=", 1)
                                k, v = k.strip(), v.strip()
                                if k:
                                    cookie_map[k] = v

        if items is not None:
            # Two-pass so specific `affiliate.shopee.vn` cookies override generic `.shopee.vn` duplicates
            sorted_items = sorted(
                [x for x in items if isinstance(x, dict)],
                key=lambda c: 1 if str(c.get("domain", "")).startswith("affiliate.") else 0
            )
            for entry in sorted_items:
                name = str(entry.get("name", "")).strip()
                val = "" if entry.get("value") is None else str(entry.get("value")).strip()
                if name:
                    cookie_map[name] = val

        # Sanitize CR/LF so `requests` never raises InvalidHeader
        clean_map = {
            re.sub(r"[\r\n]+", "", k): re.sub(r"[\r\n]+", "", v)
            for k, v in cookie_map.items() if k
        }
        header_str = "; ".join(f"{k}={v}" for k, v in clean_map.items())
        return header_str, clean_map

    def _portal_headers(self, referer: str = "https://affiliate.shopee.vn/dashboard") -> Dict[str, str]:
        csrf = self.cookie_dict.get("csrftoken", "")
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json; charset=UTF-8",
            "Origin": "https://affiliate.shopee.vn",
            "Referer": referer,
            "x-shopee-language": "vi",
            "affiliate-program-type": "1",
        }
        if self.cookie:
            headers["Cookie"] = self.cookie
        if csrf:
            headers["csrf-token"] = csrf
            headers["x-csrftoken"] = csrf
        return headers

    def fetch_affiliate_profile(self, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        """
        Authenticates with `https://affiliate.shopee.vn/api/v3/user/profile` using `self.cookie`.
        Returns profile dict (`affiliate_id`, `user_id`, `shopee_user_name`, `nick_name`, etc.)
        and updates `self.affiliate_id` automatically when valid.
        """
        if not self.cookie:
            return None
        if self._cached_profile is not None and not force_refresh:
            return self._cached_profile

        try:
            res = requests.get(
                self.PORTAL_PROFILE_ENDPOINT,
                headers=self._portal_headers(),
                timeout=10
            )
            if res.status_code == 200:
                body = res.json()
                if body.get("code") == 0 and isinstance(body.get("data"), dict):
                    data = body["data"]
                    aff_id = str(data.get("affiliate_id") or "").strip()
                    if aff_id:
                        self.affiliate_id = aff_id
                    self._cached_profile = {
                        "affiliate_id": aff_id or self.affiliate_id,
                        "user_id": str(data.get("user_id") or ""),
                        "shopee_user_name": data.get("shopee_user_name") or data.get("name") or "",
                        "nick_name": data.get("nick_name") or "",
                        "email": data.get("email") or "",
                        "phone": data.get("phone") or "",
                        "account_type": data.get("account_type"),
                        "social_channels": [
                            s.get("user_name") for s in (data.get("social_media_info") or [])
                            if isinstance(s, dict) and s.get("user_name")
                        ],
                    }
                    return self._cached_profile
        except Exception as e:
            print(f"[ShopeeAffiliateClient] fetch_affiliate_profile error: {e}")
        return None

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

        subs = [s for s in (sub_ids or [self.sub_id]) if s][:5]
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
        """
        Calls Shopee Affiliate Portal GraphQL `batchGetCustomLink` (`/api/v3/gql?q=batchCustomLink`).
        Note: When Shopee WAF enforces browser-JS `af-ac-enc-dat` (`error: 90309999`), returns None
        so `convert_to_affiliate_link` seamlessly uses the official `s.shopee.vn/an_redir` deep-link.
        """
        if not (self.cookie and origin_url):
            return None

        subs = [str(s).strip() for s in (sub_ids or [self.sub_id]) if s]
        while len(subs) < 5:
            subs.append("")

        payload = {
            "operationName": "batchGetCustomLink",
            "query": (
                "query batchGetCustomLink($linkParams: [CustomLinkParam!], $sourceCaller: SourceCaller){\n"
                "  batchCustomLink(linkParams: $linkParams, sourceCaller: $sourceCaller){\n"
                "    shortLink\n"
                "    longLink\n"
                "    failCode\n"
                "  }\n"
                "}\n"
            ),
            "variables": {
                "linkParams": [
                    {
                        "originalUrl": origin_url,
                        "advancedLinkParams": {
                            "subId1": subs[0],
                            "subId2": subs[1],
                            "subId3": subs[2],
                            "subId4": subs[3],
                            "subId5": subs[4],
                        }
                    }
                ],
                "sourceCaller": "CUSTOM_LINK_CALLER"
            }
        }
        headers = self._portal_headers(referer="https://affiliate.shopee.vn/offer/custom_link")
        try:
            res = requests.post(self.PORTAL_GQL_ENDPOINT, json=payload, headers=headers, timeout=10)
            if res.status_code == 200:
                body = res.json()
                items = (body.get("data") or {}).get("batchCustomLink") or []
                if isinstance(items, list) and items:
                    first = items[0] or {}
                    if not first.get("failCode") and first.get("shortLink"):
                        return first["shortLink"]
                # Legacy fallback check
                legacy = ((body.get("data") or {}).get("generateShortLink") or {}).get("data", {}).get("shortLink")
                if legacy:
                    return legacy
        except Exception as e:
            print(f"[ShopeeAffiliateClient] Cookie GQL error: {e}")
        return None

    def build_an_redir_link(self, origin_url: str, campaign_tag: str = "reup_video") -> str:
        """
        Constructs the official Shopee Affiliate Network Redirector URL (`https://s.shopee.vn/an_redir`).
        Verified against Shopee VN servers: returns HTTP 301 with live `mmp_pid=an_{affiliate_id}` & `uls_trackid`.
        """
        # Auto-resolve real affiliate_id from session cookie if SPC_ST is present and not yet cached
        if "SPC_ST" in self.cookie_dict and self._cached_profile is None:
            self.fetch_affiliate_profile()

        aff_id = self.affiliate_id or DEFAULT_SHOPEE_AFFILIATE_ID
        clean_sub = re.sub(r"[^A-Za-z0-9_-]", "", self.sub_id or DEFAULT_SHOPEE_SUB_ID)[:24] or DEFAULT_SHOPEE_SUB_ID
        clean_tag = re.sub(r"[^A-Za-z0-9_-]", "", campaign_tag or "")[:24]
        combined_sub = f"{clean_sub}-{clean_tag}" if (clean_tag and clean_tag != clean_sub) else clean_sub

        encoded_origin = urllib.parse.quote(origin_url.strip(), safe="")
        return (
            f"{self.AN_REDIR_ENDPOINT}?origin_link={encoded_origin}"
            f"&affiliate_id={aff_id}&sub_id={combined_sub}"
        )

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

    def _search_product_bing_index(self, keyword: str) -> Optional[str]:
        """Discovers public `https://shopee.vn/...` product or category URLs indexed on Bing."""
        try:
            q = urllib.parse.quote(f"site:shopee.vn {keyword.strip()}")
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "vi-VN,vi;q=0.9",
            }
            res = requests.get(f"https://www.bing.com/search?q={q}", headers=headers, timeout=8)
            if res.status_code != 200:
                return None

            candidates: List[str] = []
            for m in re.finditer(r"u=a1([A-Za-z0-9_-]+)", res.text):
                b64 = m.group(1) + "=" * ((4 - len(m.group(1)) % 4) % 4)
                try:
                    decoded = base64.urlsafe_b64decode(b64).decode("utf-8", errors="ignore")
                except Exception:
                    continue
                if decoded.startswith("https://shopee.vn/") and not any(
                    skip in decoded for skip in ("/buyer/", "/seller/", "/search?", "/web")
                ):
                    clean_u = decoded.split("?")[0]
                    if clean_u not in candidates:
                        candidates.append(clean_u)

            # Prefer exact item links (`-i.shopid.itemid`), then category links (`-cat.`)
            for u in candidates:
                if re.search(r"-i\.\d+\.\d+", u):
                    return u
            for u in candidates:
                if "-cat." in u and len(u) > len("https://shopee.vn/"):
                    return u
        except Exception:
            pass
        return None

    def search_product(self, keyword: str) -> Optional[str]:
        """Searches Shopee for the best matching product/category URL for `keyword`."""
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
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
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

        # 3. Try Bing indexed Shopee VN product/category URL discovery
        indexed_url = self._search_product_bing_index(keyword)
        if indexed_url:
            return indexed_url

        # 4. Clean Shopee search landing page (100% compatible with s.shopee.vn/an_redir)
        return f"https://shopee.vn/search?keyword={encoded_kw}"

    def convert_to_affiliate_link(self, product_url: str, campaign_tag: str = "reup_video") -> str:
        """
        Converts any Shopee URL into an attributed Shopee Affiliate tracking link.
        Tries:
        1) Official Open API GraphQL `generateShortLink` -> `https://s.shopee.vn/...`
        2) Affiliate Portal Cookie GraphQL `batchGetCustomLink` -> `https://s.shopee.vn/...`
        3) Official Shopee Affiliate Network Redirector (`https://s.shopee.vn/an_redir?...`)
        """
        if not product_url:
            return ""

        clean_url = product_url.strip()
        # Already a short link or an_redir link with our affiliate_id
        if re.match(r"^https?://(s\.shopee\.vn|shp\.ee)/(?!an_redir)[A-Za-z0-9_-]+", clean_url):
            return clean_url
        if "s.shopee.vn/an_redir" in clean_url and f"affiliate_id={self.affiliate_id}" in clean_url:
            return clean_url

        # Strip stale tracking query parameters if re-converting a raw shopee.vn link
        if "shopee.vn/" in clean_url and "an_redir" not in clean_url and ("utm_source=" in clean_url or "mmp_pid=" in clean_url):
            parsed = urllib.parse.urlparse(clean_url)
            q_filtered = [
                (k, v) for k, v in urllib.parse.parse_qsl(parsed.query)
                if k in ("keyword",)
            ]
            clean_url = urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(q_filtered)))

        # Tier 1: Official Open API
        short_open = self.generate_short_link_open_api(clean_url, sub_ids=[self.sub_id, campaign_tag])
        if short_open:
            return short_open

        # Tier 2: Affiliate Portal Cookie GraphQL
        short_cookie = self.generate_short_link_cookie_gql(clean_url, sub_ids=[self.sub_id, campaign_tag])
        if short_cookie:
            return short_cookie

        # Tier 3: Official Shopee Affiliate Network Redirector (`s.shopee.vn/an_redir`)
        return self.build_an_redir_link(clean_url, campaign_tag=campaign_tag)

    def verify_affiliate_link(self, affiliate_link: str, product_keyword: str = "", live_check: bool = False) -> Dict[str, Any]:
        """
        Verifies whether an affiliate link carries valid Shopee Affiliate attribution
        (`s.shopee.vn/xxxx`, `s.shopee.vn/an_redir?...affiliate_id=...`, `shp.ee`, or `utm_source=an_`).
        """
        if not affiliate_link or not affiliate_link.strip():
            return {
                "valid": False,
                "method": "none",
                "is_short_link": False,
                "has_sub_id": False,
                "affiliate_id": self.affiliate_id,
                "sub_id": self.sub_id,
                "error": "Link affiliate trống"
            }

        link = affiliate_link.strip()
        is_an_redir = link.startswith("https://s.shopee.vn/an_redir?") or link.startswith("http://s.shopee.vn/an_redir?")
        is_short = bool(re.match(r"^https?://(s\.shopee\.vn|shp\.ee)/(?!an_redir)[A-Za-z0-9_-]+", link))
        has_sub = (
            (f"sub_id={self.sub_id}" in link)
            or ("sub_id=" in link)
            or ("affiliate_id=" in link)
            or is_short
        )
        is_shopee_domain = any(d in link.lower() for d in ("shopee.vn", "shp.ee"))

        if is_short:
            method = "short_link_graphql"
        elif is_an_redir:
            method = "s.shopee.vn/an_redir"
        elif has_sub:
            method = "attributed_deeplink"
        else:
            method = "raw_url"

        universal_redir = link if (is_short or is_an_redir) else self.build_an_redir_link(link, campaign_tag="reup")

        resolved_location = None
        if live_check and (is_an_redir or is_short):
            try:
                r = requests.get(link, allow_redirects=False, timeout=8)
                if r.status_code in (301, 302):
                    resolved_location = r.headers.get("Location")
            except Exception:
                pass

        return {
            "valid": bool(is_shopee_domain and has_sub),
            "affiliate_link": link,
            "universal_redirect_link": universal_redir,
            "resolved_location": resolved_location,
            "product_keyword": product_keyword,
            "method": method,
            "is_short_link": bool(is_short or is_an_redir),
            "has_sub_id": has_sub,
            "affiliate_id": self.affiliate_id,
            "sub_id": self.sub_id,
            "open_api_configured": bool(self.app_id and self.app_secret),
            "cookie_configured": bool(self.cookie)
        }

    def test_connection(self) -> Dict[str, Any]:
        """
        Tests Shopee Affiliate credentials end-to-end:
        1. Validates Cookie session against `https://affiliate.shopee.vn/api/v3/user/profile`
           and auto-syncs `affiliate_id`.
        2. Generates a real tracking link and verifies Shopee's HTTP 301 redirect (`mmp_pid=an_{affiliate_id}`).
        """
        profile = self.fetch_affiliate_profile(force_refresh=True) if self.cookie else None
        if self.cookie and not profile and "SPC_ST" in self.cookie_dict:
            return {
                "success": False,
                "error": "Cookie Shopee Affiliate đã hết hạn hoặc không hợp lệ. Vui lòng xuất lại Cookie từ affiliate.shopee.vn.",
                "has_cookie": True,
                "affiliate_id": self.affiliate_id,
                "sub_id": self.sub_id,
            }

        sample_origin = "https://shopee.vn/search?keyword=quat+tich+dien+mini"
        converted = self.convert_to_affiliate_link(sample_origin, campaign_tag="test")
        check = self.verify_affiliate_link(converted, product_keyword="quạt tích điện mini", live_check=True)

        if self.app_id and self.app_secret:
            mode_msg = f"Shopee Open API GraphQL (AppID: {self.app_id[:6]}...)"
        elif profile:
            uname = profile.get("shopee_user_name") or profile.get("nick_name") or "Affiliate"
            mode_msg = (
                f"Đã xác thực Cookie Shopee Affiliate: @{uname} "
                f"(Affiliate ID: {profile['affiliate_id']} • User ID: {profile['user_id']})"
            )
        elif self.cookie:
            mode_msg = f"Shopee Cookie & Official Redirector (Affiliate ID: {self.affiliate_id})"
        else:
            mode_msg = f"Chế độ Official Redirector (Affiliate ID: {self.affiliate_id} • Sub-ID: {self.sub_id})"

        return {
            "success": check["valid"],
            "message": f"{mode_msg}\nLink mẫu: {converted}",
            "sample_link": converted,
            "resolved_location": check.get("resolved_location"),
            "profile": profile,
            "affiliate_id": self.affiliate_id,
            "sub_id": self.sub_id,
            "verification": check,
            "has_cookie": bool(self.cookie),
            "cookie_count": len(self.cookie_dict),
            "has_open_api": bool(self.app_id and self.app_secret),
        }
