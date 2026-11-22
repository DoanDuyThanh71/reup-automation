import os
import re
import sys
import json
import time
import asyncio
import requests
import concurrent.futures
from typing import Dict, Any, Optional, List, Tuple
from .security_fingerprint import SecurityFingerprintManager


class TikTokClient:
    """
    Production TikTok Client supporting:
    1. Multi-format Cookie Parser: Accepts Cookie-Editor JSON array (`[{"name":...,"value":...}]`)
       or raw `sessionid=...` strings.
    2. Deterministic Account-Bound Browser Fingerprinting (`SecurityFingerprintManager`)
       so TikTok always sees a consistent Windows Chrome profile matching the account's session.
    3. Account Authentication & Profile Verification (`passport/web/account/info/`).
    4. Automated Video Upload to TikTok Studio (`https://www.tiktok.com/tiktokstudio/upload`)
       via Playwright with cookie injection, caption/hashtag entry, and diagnostic proof screenshots,
       plus optional Webhook delivery (n8n / Make).
    5. Profile & Video Analytics Extraction (`followerCount`, `heartCount`, `videoCount`, recent plays).
    """

    PASSPORT_INFO_URL = "https://www.tiktok.com/passport/web/account/info/?aid=1459&app_language=vi-VN"
    STUDIO_UPLOAD_URL = "https://www.tiktok.com/tiktokstudio/upload?lang=vi-VN"

    def __init__(self, cookie_or_session: Optional[str] = None, webhook_url: Optional[str] = None):
        from ..config import config
        raw_cookie = cookie_or_session if cookie_or_session is not None else (
            config.get("TIKTOK_COOKIES", "") or config.get("TIKTOK_SESSION_ID", "")
        )
        self.webhook_url = (webhook_url if webhook_url is not None else config.get("TIKTOK_WEBHOOK_URL", "")).strip()
        self.cookie_str, self.cookie_dict, self.playwright_cookies = self.parse_tiktok_cookies(raw_cookie)
        seed = self.cookie_dict.get("uid_tt") or self.cookie_dict.get("sessionid") or "tiktok-vn-default"
        self.fp_profile = SecurityFingerprintManager.get_browser_fingerprint(seed)
        self.secret_fp = SecurityFingerprintManager.secret_fingerprint(self.cookie_dict.get("sessionid") or self.cookie_str)

    @staticmethod
    def parse_tiktok_cookies(raw_input: Any) -> Tuple[str, Dict[str, str], List[Dict[str, Any]]]:
        """Parses Cookie-Editor JSON list or raw `sessionid=...` into `(header_str, cookie_dict, pw_cookies)`."""
        if not raw_input:
            return "", {}, []

        cookie_map: Dict[str, str] = {}
        pw_list: List[Dict[str, Any]] = []

        def _norm_samesite(val: Any) -> str:
            s = str(val or "").lower().strip()
            if s in ("strict",):
                return "Strict"
            if s in ("no_restriction", "none"):
                return "None"
            return "Lax"

        items = None
        if isinstance(raw_input, list):
            items = raw_input
        elif isinstance(raw_input, str):
            text = raw_input.strip()
            if text.startswith("[") and text.endswith("]"):
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, list):
                        items = parsed
                except Exception:
                    items = None

            if items is None:
                # Plain sessionid hex or Cookie header string
                if "=" not in text and re.match(r"^[a-fA-F0-9]{20,64}$", text):
                    cookie_map = {
                        "sessionid": text,
                        "sessionid_ss": text,
                        "sid_tt": text,
                    }
                else:
                    for pair in text.replace("\n", ";").split(";"):
                        pair = pair.strip()
                        if "=" in pair:
                            k, v = pair.split("=", 1)
                            k, v = k.strip(), v.strip()
                            if k:
                                cookie_map[k] = v
                for k, v in cookie_map.items():
                    pw_list.append({
                        "name": k,
                        "value": v,
                        "domain": ".tiktok.com",
                        "path": "/",
                        "secure": True,
                        "httpOnly": k in ("sessionid", "sessionid_ss", "sid_tt", "uid_tt"),
                        "sameSite": "None" if k.endswith("_ss") else "Lax",
                    })

        if items is not None:
            for c in items:
                if not isinstance(c, dict):
                    continue
                name = str(c.get("name", "")).strip()
                val = "" if c.get("value") is None else str(c.get("value")).strip()
                if not name:
                    continue
                cookie_map[name] = val
                domain = str(c.get("domain") or ".tiktok.com").strip()
                same_site = _norm_samesite(c.get("sameSite"))
                secure = bool(c.get("secure", True)) or same_site == "None"
                pw_cookie: Dict[str, Any] = {
                    "name": name,
                    "value": val,
                    "domain": domain,
                    "path": str(c.get("path") or "/"),
                    "secure": secure,
                    "httpOnly": bool(c.get("httpOnly", False)),
                    "sameSite": same_site,
                }
                exp = c.get("expirationDate")
                if isinstance(exp, (int, float)) and exp > time.time():
                    pw_cookie["expires"] = float(exp)
                pw_list.append(pw_cookie)

        clean_map = {
            re.sub(r"[\r\n]+", "", k): re.sub(r"[\r\n]+", "", v)
            for k, v in cookie_map.items() if k
        }
        header_str = "; ".join(f"{k}={v}" for k, v in clean_map.items())
        return header_str, clean_map, pw_list

    def _headers(self, referer: str = "https://www.tiktok.com/") -> Dict[str, str]:
        h = dict(self.fp_profile["headers"])
        h["Referer"] = referer
        if self.cookie_str:
            h["Cookie"] = self.cookie_str
        csrf = self.cookie_dict.get("tt_csrf_token")
        if csrf:
            h["x-secsdk-csrf-token"] = csrf
        return h

    def verify_account(self) -> Dict[str, Any]:
        """Verifies TikTok session cookie validity and returns account identity."""
        if not self.cookie_str and not self.webhook_url:
            return {"success": False, "error": "Chưa cấu hình Cookie TikTok hoặc Webhook URL"}

        if not self.cookie_str and self.webhook_url:
            return {
                "success": True,
                "mode": "webhook",
                "message": f"Đã cấu hình TikTok Webhook: {self.webhook_url}",
            }

        try:
            res = requests.get(self.PASSPORT_INFO_URL, headers=self._headers(), timeout=12)
            body = res.json() if res.status_code == 200 else {}
            data = body.get("data") or {}
            username = data.get("username") or ""
            if username or data.get("user_id_str"):
                return {
                    "success": True,
                    "mode": "cookie_studio",
                    "user_id": str(data.get("user_id_str") or data.get("user_id") or ""),
                    "sec_user_id": data.get("sec_user_id") or "",
                    "username": username,
                    "screen_name": data.get("screen_name") or username,
                    "avatar_url": data.get("avatar_url") or "",
                    "browser_fingerprint": self.fp_profile["fingerprint_id"],
                    "cookie_fingerprint": self.secret_fp,
                    "message": (
                        f"Đã xác thực TikTok: @{username} ({data.get('screen_name', '')}) • "
                        f"Vân tay trình duyệt: {self.fp_profile['fingerprint_id']}"
                    ),
                }
            return {
                "success": False,
                "error": f"Cookie TikTok đã hết hạn hoặc không hợp lệ (mã phản hồi: {body.get('message', res.status_code)}).",
            }
        except Exception as e:
            return {"success": False, "error": f"Lỗi kiểm tra TikTok Cookie: {e}"}

    def fetch_analytics(self) -> Dict[str, Any]:
        """Fetches TikTok profile follower/heart/video counts and recent videos if publicly hydrated."""
        acc = self.verify_account()
        if not acc.get("success") or not acc.get("username"):
            return {
                "connected": False,
                "error": acc.get("error", "Chưa kết nối tài khoản TikTok"),
                "browser_fingerprint": self.fp_profile["fingerprint_id"],
                "cookie_fingerprint": self.secret_fp,
            }

        username = acc["username"]
        profile_url = f"https://www.tiktok.com/@{username}"
        stats = {"followerCount": 0, "heartCount": 0, "videoCount": 0, "followingCount": 0}
        try:
            r = requests.get(profile_url, headers=self._headers(referer="https://www.tiktok.com/"), timeout=12)
            if r.status_code == 200:
                m = re.search(
                    r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>([\s\S]*?)</script>',
                    r.text,
                )
                if m:
                    hydrated = json.loads(m.group(1))
                    user_detail = (
                        hydrated.get("__DEFAULT_SCOPE__", {})
                        .get("webapp.user-detail", {})
                        .get("userInfo", {})
                    )
                    st = user_detail.get("stats") or {}
                    if st:
                        stats = {
                            "followerCount": int(st.get("followerCount", 0)),
                            "heartCount": int(st.get("heartCount", st.get("heart", 0))),
                            "videoCount": int(st.get("videoCount", 0)),
                            "followingCount": int(st.get("followingCount", 0)),
                        }
        except Exception as e:
            print(f"[TikTokClient] fetch_analytics hydration note: {e}")

        return {
            "connected": True,
            "username": username,
            "screen_name": acc.get("screen_name"),
            "user_id": acc.get("user_id"),
            "profile_url": profile_url,
            "avatar_url": acc.get("avatar_url"),
            "browser_fingerprint": self.fp_profile["fingerprint_id"],
            "cookie_fingerprint": self.secret_fp,
            "stats": stats,
        }

    async def _upload_via_playwright_async(self, video_path: str, full_caption: str, proof_dir: str) -> Dict[str, Any]:
        from playwright.async_api import async_playwright

        os.makedirs(proof_dir, exist_ok=True)
        proof_shot = os.path.join(proof_dir, "tiktok_studio_upload.png")

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )
            context = await browser.new_context(
                user_agent=self.fp_profile["ua"],
                viewport=self.fp_profile["viewport"],
                locale=self.fp_profile["locale"],
                timezone_id=self.fp_profile["timezone_id"],
                extra_http_headers={
                    "Accept-Language": self.fp_profile["accept_language"],
                    "Sec-CH-UA": self.fp_profile["sec_ch_ua"],
                    "Sec-CH-UA-Mobile": "?0",
                    "Sec-CH-UA-Platform": '"Windows"',
                },
            )
            await context.add_init_script(self.fp_profile["init_script"])
            if self.playwright_cookies:
                await context.add_cookies(self.playwright_cookies)

            page = await context.new_page()
            try:
                await page.goto(self.STUDIO_UPLOAD_URL, wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(4000)

                if "/login" in page.url:
                    await page.screenshot(path=proof_shot)
                    return {
                        "success": False,
                        "error": "TikTok Studio yêu cầu đăng nhập lại (Cookie hết quyền truy cập Studio).",
                        "screenshot": proof_shot,
                    }

                # Check if gated by CAPTCHA (never solve/bypass per strict safety policy)
                captcha_el = await page.query_selector('[id*="captcha"], .captcha_verify_container, iframe[src*="captcha"]')
                if captcha_el:
                    await page.screenshot(path=proof_shot)
                    return {
                        "success": False,
                        "error": "TikTok Studio hiển thị xác minh bảo mật (CAPTCHA). Đã dừng tự động theo quy tắc an toàn tài khoản — vui lòng mở TikTok Studio trên trình duyệt xác minh 1 lần.",
                        "screenshot": proof_shot,
                    }

                # Locate file input (either directly on page or inside upload iframe)
                target_frame = page
                file_input = await page.query_selector('input[type="file"]')
                if not file_input:
                    for frame in page.frames:
                        fi = await frame.query_selector('input[type="file"]')
                        if fi:
                            target_frame = frame
                            file_input = fi
                            break
                if not file_input:
                    file_input = await page.wait_for_selector('input[type="file"]', state="attached", timeout=25000)

                await file_input.set_input_files(os.path.abspath(video_path))

                # Wait for video upload & editor to initialize
                editor_sel = '[contenteditable="true"], .public-DraftEditor-content'
                editor = await target_frame.wait_for_selector(editor_sel, timeout=45000)
                await page.wait_for_timeout(3000)

                async def _dismiss_ui_modals():
                    """Closes benign TikTok Studio onboarding/copyright-check modals ('Bật kiểm tra nội dung tự động?' -> 'Hủy')."""
                    dismiss_selectors = [
                        '.TUXModal button:has-text("Hủy")',
                        '[data-floating-ui-portal] button:has-text("Hủy")',
                        '[data-floating-ui-portal] button:has-text("Cancel")',
                        '[data-floating-ui-portal] button:has-text("Đã hiểu")',
                        '[data-floating-ui-portal] button:has-text("Got it")',
                        '[data-floating-ui-portal] button:has-text("Để sau")',
                        'button[aria-label="Close"]',
                    ]
                    for d_sel in dismiss_selectors:
                        try:
                            m_btn = await page.query_selector(d_sel)
                            if m_btn and await m_btn.is_visible():
                                await m_btn.click(timeout=3000)
                                await page.wait_for_timeout(800)
                        except Exception:
                            pass
                    try:
                        overlay = await page.query_selector('.TUXModal-overlay')
                        if overlay and await overlay.is_visible():
                            await page.keyboard.press("Escape")
                            await page.wait_for_timeout(800)
                    except Exception:
                        pass

                await _dismiss_ui_modals()

                # Clear default filename caption & type clean Vietnamese viral caption
                editor = await target_frame.wait_for_selector(editor_sel, timeout=15000)
                await editor.scroll_into_view_if_needed()
                await editor.click()
                await page.wait_for_timeout(400)
                await page.keyboard.press("Control+A")
                await page.keyboard.press("Backspace")
                for _ in range(35):
                    await page.keyboard.press("Backspace")
                clean_cap = full_caption[:2000]
                await page.keyboard.insert_text(clean_cap)

                # Ensure visibility is set to 'Mọi người' / 'Everyone' if dropdown is present
                try:
                    priv_btn = await target_frame.query_selector('button:has-text("Chỉ mình tôi"), [data-e2e="video_visibility_container"] button')
                    if priv_btn:
                        txt = (await priv_btn.inner_text() or "").strip()
                        if "Chỉ mình" in txt or "Only you" in txt:
                            await priv_btn.click()
                            await page.wait_for_timeout(500)
                            pub_opt = await page.query_selector('[role="option"]:has-text("Mọi người"), [role="option"]:has-text("Everyone"), div:has-text("Mọi người")')
                            if pub_opt:
                                await pub_opt.click()
                                await page.wait_for_timeout(400)
                except Exception:
                    pass

                # Wait until Post button is enabled (upload reaches 100%)
                post_selectors = [
                    'button[data-e2e="post_video_button"]:not([disabled]):not([aria-disabled="true"])',
                    'button:has-text("Đăng"):not([disabled])',
                    'button:has-text("Post"):not([disabled])',
                ]
                post_btn = None
                for _ in range(36):  # Up to ~72s for video binary upload to finish
                    await _dismiss_ui_modals()
                    # Stop immediately if CAPTCHA appears
                    cap_now = await page.query_selector('[id*="captcha"], .captcha_verify_container')
                    if cap_now:
                        await page.screenshot(path=proof_shot)
                        return {
                            "success": False,
                            "error": "TikTok yêu cầu xác minh CAPTCHA khi tải video. Đã dừng an toàn.",
                            "screenshot": proof_shot,
                        }
                    for sel in post_selectors:
                        btn = await target_frame.query_selector(sel)
                        if btn:
                            disabled_attr = await btn.get_attribute("aria-disabled")
                            if disabled_attr != "true":
                                post_btn = btn
                                break
                    if post_btn:
                        break
                    await page.wait_for_timeout(2000)

                if not post_btn:
                    await page.screenshot(path=proof_shot)
                    return {
                        "success": False,
                        "error": "Nút Đăng trên TikTok Studio chưa kích hoạt sau 70 giây (video đang kiểm duyệt hoặc giao diện thay đổi).",
                        "screenshot": proof_shot,
                    }

                await _dismiss_ui_modals()
                await post_btn.scroll_into_view_if_needed()
                await post_btn.click(force=True)

                # Handle optional confirmation modal ("Post now" / "Đăng ngay")
                await page.wait_for_timeout(5000)
                for confirm_sel in ['button:has-text("Đăng ngay")', 'button:has-text("Post now")', 'button:has-text("Tiếp tục đăng")']:
                    c_btn = await target_frame.query_selector(confirm_sel)
                    if c_btn:
                        await c_btn.click()
                        await page.wait_for_timeout(3000)

                await page.wait_for_timeout(5000)
                await page.screenshot(path=proof_shot)
                return {
                    "success": True,
                    "post_id": f"tt_{int(time.time())}",
                    "screenshot": proof_shot,
                    "browser_fingerprint": self.fp_profile["fingerprint_id"],
                    "message": f"Đã tải lên và nhấn Đăng trên TikTok Studio (Vân tay: {self.fp_profile['fingerprint_id']})",
                }
            except Exception as e:
                try:
                    await page.screenshot(path=proof_shot)
                except Exception:
                    pass
                return {
                    "success": False,
                    "error": f"Lỗi TikTok Studio Playwright: {e}",
                    "screenshot": proof_shot,
                }
            finally:
                await browser.close()

    def publish_video(self, video_path: str, title: str, caption: str, hashtags: str = "") -> Dict[str, Any]:
        """Publishes video via Webhook (if set) or directly to TikTok Studio using Playwright + Cookies."""
        if not os.path.exists(video_path):
            return {"success": False, "error": f"Không tìm thấy file video: {video_path}"}

        parts = [p.strip() for p in (title, caption, hashtags) if p and p.strip()]
        full_caption = "\n".join(parts)

        # 1. Webhook mode if explicitly configured
        if self.webhook_url:
            try:
                res = requests.post(
                    self.webhook_url,
                    json={
                        "video_path": video_path,
                        "title": title,
                        "caption": caption,
                        "hashtags": hashtags,
                        "file_name": os.path.basename(video_path),
                    },
                    timeout=30,
                )
                if res.status_code in (200, 201):
                    return {"success": True, "post_id": f"webhook_{int(time.time())}", "message": "Đã gửi video tới TikTok Webhook thành công"}
                return {"success": False, "error": f"TikTok Webhook trả về mã {res.status_code}: {res.text[:200]}"}
            except Exception as e:
                return {"success": False, "error": f"Lỗi gọi TikTok Webhook: {e}"}

        # 2. Direct TikTok Studio Cookie Upload via Playwright
        if not self.playwright_cookies:
            return {"success": False, "error": "Chưa cấu hình Cookie TikTok (TIKTOK_COOKIES) hoặc Webhook"}

        acc_check = self.verify_account()
        if not acc_check.get("success"):
            return acc_check

        proof_dir = os.path.dirname(os.path.abspath(video_path))

        def _runner():
            if sys.platform == "win32":
                loop = asyncio.ProactorEventLoop()
                asyncio.set_event_loop(loop)
                try:
                    return loop.run_until_complete(self._upload_via_playwright_async(video_path, full_caption, proof_dir))
                finally:
                    loop.close()
            return asyncio.run(self._upload_via_playwright_async(video_path, full_caption, proof_dir))

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(_runner).result(timeout=180)
