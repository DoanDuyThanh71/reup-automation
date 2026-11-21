import os
import re
import sys
import asyncio
import requests
import subprocess
import concurrent.futures
from typing import Dict, Any, Optional

class DouyinScraper:
    """
    Handles downloading videos from Douyin, TikTok, YouTube Shorts, or direct MP4 URLs without watermarks.
    - Extracts clean URLs from raw mobile share text.
    - Normalizes Douyin modal_id / video IDs.
    - Uses Playwright headless browser (with anti-webdriver stealth) to intercept Douyin's
      /aweme/v1/web/aweme/detail/ JSON (progressive MP4) or DASH video + audio streams.
    - Falls back to Python yt_dlp library and direct HTTP streaming.
    """
    URL_REGEX = re.compile(r'https?://[^\s<>"\'，。！？；：（）【】]+')
    DOUYIN_ID_REGEX = re.compile(r'(?:modal_id=|/video/|/note/)(\d{15,22})')

    def __init__(self, cookie_string: Optional[str] = None):
        from ..config import config
        self.cookie_string = cookie_string or config.get("DOUYIN_COOKIE", "")
        self.user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )
        self.headers = {
            "User-Agent": self.user_agent,
            "Referer": "https://www.douyin.com/"
        }
        if self.cookie_string:
            self.headers["Cookie"] = self.cookie_string

    @classmethod
    def extract_url(cls, raw_input: str) -> str:
        """Extracts clean HTTP/HTTPS URL from raw mobile share text (e.g. Douyin share copy)."""
        if not raw_input or not raw_input.strip():
            raise ValueError("URL đầu vào trống")
        match = cls.URL_REGEX.search(raw_input.strip())
        if match:
            url = match.group(0)
            return url.rstrip("/.,;!)") if not url.endswith("/") else url
        return raw_input.strip()

    @classmethod
    def extract_douyin_id(cls, url: str) -> Optional[str]:
        """Extracts 19-digit Douyin video ID from modal_id=..., /video/..., or /note/..."""
        m = cls.DOUYIN_ID_REGEX.search(url)
        return m.group(1) if m else None

    def resolve_douyin_short_url(self, short_url: str) -> str:
        """Follows redirect to obtain full Douyin desktop video URL."""
        clean_url = self.extract_url(short_url)
        try:
            res = requests.get(clean_url, headers=self.headers, allow_redirects=True, timeout=10)
            return res.url
        except Exception as e:
            print(f"[DouyinScraper] Failed to resolve short URL: {e}")
            return clean_url

    def _stream_download(self, url: str, dest_path: str, headers: Dict[str, str], timeout: int = 180) -> int:
        """Streams a file from url to dest_path in chunks and returns total bytes written."""
        total = 0
        with requests.get(url, headers=headers, stream=True, timeout=timeout) as r:
            r.raise_for_status()
            with open(dest_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=131072):
                    if chunk:
                        f.write(chunk)
                        total += len(chunk)
        return total

    async def _download_douyin_via_playwright_async(self, douyin_url: str, output_path: str) -> Optional[str]:
        """
        Uses Playwright headless Chromium with navigator.webdriver removed to open
        https://www.douyin.com/jingxuan?modal_id=<id>, capture exact progressive MP4 from detail JSON
        or DASH video + audio streams, download them, and mux into output_path using FFmpeg.
        """
        from playwright.async_api import async_playwright
        from ..config import get_ffmpeg_exe

        vid = self.extract_douyin_id(douyin_url)
        target_url = f"https://www.douyin.com/jingxuan?modal_id={vid}" if vid else douyin_url

        video_urls = []
        audio_urls = []
        prog_urls = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"]
            )
            ctx = await browser.new_context(user_agent=self.user_agent)
            await ctx.add_init_script("delete Object.getPrototypeOf(navigator).webdriver;")
            page = await ctx.new_page()

            async def on_response(r):
                u = r.url
                if "/aweme/v1/web/aweme/detail/" in u and r.status == 200:
                    try:
                        data = await r.json()
                        detail = data.get("aweme_detail") or {}
                        play_urls = detail.get("video", {}).get("play_addr", {}).get("url_list", [])
                        for pu in play_urls:
                            if pu and "uuu_265.mp4" not in pu:
                                prog_urls.insert(0, pu)
                    except Exception:
                        pass
                elif "douyinvod.com" in u and "uuu_265.mp4" not in u:
                    if "media-audio" in u:
                        audio_urls.append(u)
                    elif "media-video" in u:
                        video_urls.append(u)
                    else:
                        prog_urls.append(u)

            page.on("response", on_response)
            try:
                await page.goto(target_url, wait_until="commit", timeout=15000)
            except Exception as e:
                print(f"[DouyinScraper] Playwright goto note: {e}")

            for _ in range(40):
                if prog_urls or (video_urls and audio_urls):
                    break
                await page.wait_for_timeout(500)

            await browser.close()

        dl_headers = {
            "User-Agent": self.user_agent,
            "Referer": "https://www.douyin.com/"
        }

        # Case 1: Progressive single MP4 stream (fastest, already muxed)
        if prog_urls:
            try:
                written = self._stream_download(prog_urls[0], output_path, dl_headers)
                if written > 10000:
                    return output_path
            except Exception as e:
                print(f"[DouyinScraper] Progressive stream download failed ({e}), trying DASH streams...")

        # Case 2: DASH separate video + audio streams -> download & mux via FFmpeg
        if video_urls:
            temp_v = output_path + ".video.tmp.mp4"
            temp_a = output_path + ".audio.tmp.m4a"
            try:
                v_written = self._stream_download(video_urls[-1], temp_v, dl_headers)
                if v_written < 10000:
                    return None

                if not audio_urls:
                    if os.path.exists(output_path):
                        os.remove(output_path)
                    os.rename(temp_v, output_path)
                    return output_path

                self._stream_download(audio_urls[-1], temp_a, dl_headers)

                ffmpeg_bin = get_ffmpeg_exe()
                mux_cmd = [
                    ffmpeg_bin, "-y",
                    "-i", temp_v,
                    "-i", temp_a,
                    "-c:v", "copy",
                    "-c:a", "aac",
                    "-shortest",
                    output_path
                ]
                subprocess.run(mux_cmd, check=True, capture_output=True)
            finally:
                for tf in (temp_v, temp_a):
                    if os.path.exists(tf):
                        try:
                            os.remove(tf)
                        except Exception:
                            pass

            if os.path.exists(output_path) and os.path.getsize(output_path) > 10000:
                return output_path

        return None

    def _download_douyin_via_playwright(self, douyin_url: str, output_path: str) -> Optional[str]:
        """Synchronous wrapper for Playwright Douyin downloader."""
        def _runner():
            if sys.platform == "win32":
                loop = asyncio.ProactorEventLoop()
                asyncio.set_event_loop(loop)
                try:
                    return loop.run_until_complete(self._download_douyin_via_playwright_async(douyin_url, output_path))
                finally:
                    loop.close()
            else:
                return asyncio.run(self._download_douyin_via_playwright_async(douyin_url, output_path))

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                res = pool.submit(_runner).result(timeout=300)
                if res and os.path.exists(res) and os.path.getsize(res) > 10000:
                    return res
        except Exception as e:
            print(f"[DouyinScraper] Playwright extraction warning: {type(e).__name__}: {e}")

        if os.path.exists(output_path) and os.path.getsize(output_path) > 10000:
            return output_path
        return None

    def download_video(self, url: str, output_path: str) -> str:
        """
        Downloads video to output_path. Supports Douyin (modal_id, /video/, v.douyin.com),
        TikTok, YouTube Shorts, or direct MP4 links.
        """
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        # Reuse existing downloaded file if already present (> 10KB)
        if os.path.exists(output_path) and os.path.getsize(output_path) > 10000:
            return output_path

        clean_url = self.extract_url(url)

        # 1. Direct MP4 file link
        if any(clean_url.lower().split("?")[0].endswith(ext) for ext in (".mp4", ".mov", ".m4v")):
            self._stream_download(clean_url, output_path, self.headers)
            return output_path

        resolved_url = clean_url
        if "v.douyin.com" in clean_url or "vt.tiktok.com" in clean_url or "vm.tiktok.com" in clean_url:
            resolved_url = self.resolve_douyin_short_url(clean_url)

        # 2. If Douyin URL, try Playwright DASH/Detail stream capture first
        if "douyin.com" in resolved_url:
            pw_saved = self._download_douyin_via_playwright(resolved_url, output_path)
            if pw_saved and os.path.exists(pw_saved) and os.path.getsize(pw_saved) > 10000:
                return pw_saved

            vid = self.extract_douyin_id(resolved_url)
            if vid:
                resolved_url = f"https://www.douyin.com/video/{vid}"

        # 3. Attempt download via yt-dlp CLI or Python module
        cmd = [
            "yt-dlp",
            "--no-check-certificates",
            "-o", output_path,
            "--force-overwrites",
            resolved_url
        ]
        if self.cookie_string and "douyin.com" in resolved_url:
            cmd.extend(["--add-header", f"Cookie:{self.cookie_string}"])

        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                return output_path
        except Exception as yt_err:
            print(f"[DouyinScraper] yt-dlp CLI error: {yt_err}. Trying Python yt_dlp library...")
            try:
                import yt_dlp
                ydl_opts = {
                    "outtmpl": output_path,
                    "overwrites": True,
                    "nocheckcertificate": True,
                    "quiet": True,
                    "http_headers": dict(self.headers)
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([resolved_url])
                if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                    return output_path
            except Exception as py_yt_err:
                print(f"[DouyinScraper] Python yt_dlp error: {py_yt_err}")

        # 4. Check if file was created with extra extension
        for ext in [".mp4", ".mkv", ".webm"]:
            alt_path = output_path + ext
            if os.path.exists(alt_path):
                if os.path.exists(output_path):
                    os.remove(output_path)
                os.rename(alt_path, output_path)
                return output_path

        raise RuntimeError(f"Không thể tải video từ URL: {url}")
