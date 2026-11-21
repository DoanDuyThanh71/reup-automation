import os
import re
import requests
import subprocess
from typing import Dict, Any, Optional

class DouyinScraper:
    """
    Handles downloading videos from Douyin and TikTok without watermarks.
    Combines custom HTTP un-shorteners, URL extraction from raw share text, and yt-dlp.
    """
    URL_REGEX = re.compile(r'https?://[^\s<>"\'，。！？；：（）【】]+')

    def __init__(self, cookie_string: Optional[str] = None):
        from ..config import config
        self.cookie_string = cookie_string or config.get("DOUYIN_COOKIE", "")
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.douyin.com/"
        }
        if self.cookie_string:
            self.headers["Cookie"] = self.cookie_string

    @classmethod
    def extract_url(cls, raw_input: str) -> str:
        """Extracts clean HTTP/HTTPS URL from raw mobile share text (e.g. Douyin share copy)."""
        if not raw_input:
            raise ValueError("URL đầu vào trống")
        match = cls.URL_REGEX.search(raw_input.strip())
        if match:
            return match.group(0).rstrip("/.,;!)") if not match.group(0).endswith("/") else match.group(0)
        return raw_input.strip()

    def resolve_douyin_short_url(self, short_url: str) -> str:
        """Follows redirect to obtain full Douyin desktop video URL."""
        clean_url = self.extract_url(short_url)
        try:
            res = requests.get(clean_url, headers=self.headers, allow_redirects=True, timeout=10)
            return res.url
        except Exception as e:
            print(f"[DouyinScraper] Failed to resolve short URL: {e}")
            return clean_url

    def download_video(self, url: str, output_path: str) -> str:
        """
        Downloads video to output_path. Supports Douyin, TikTok, YouTube Shorts, or direct MP4.
        Uses yt-dlp with fallback to direct streaming.
        """
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        clean_url = self.extract_url(url)

        # Direct MP4 file link
        if any(clean_url.lower().split("?")[0].endswith(ext) for ext in (".mp4", ".mov", ".m4v")):
            res = requests.get(clean_url, stream=True, timeout=60)
            res.raise_for_status()
            with open(output_path, "wb") as f:
                for chunk in res.iter_content(chunk_size=8192):
                    f.write(chunk)
            return output_path

        resolved_url = clean_url
        if "v.douyin.com" in clean_url or "vt.tiktok.com" in clean_url or "vm.tiktok.com" in clean_url:
            resolved_url = self.resolve_douyin_short_url(clean_url)

        # Attempt download via yt-dlp
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
            print(f"[DouyinScraper] yt-dlp error: {yt_err}. Trying direct stream...")

        # If yt-dlp failed or output wasn't created, check if file was created with extension
        for ext in [".mp4", ".mkv", ".webm"]:
            alt_path = output_path + ext
            if os.path.exists(alt_path):
                if os.path.exists(output_path):
                    os.remove(output_path)
                os.rename(alt_path, output_path)
                return output_path

        raise RuntimeError(f"Không thể tải video từ URL: {url}")
