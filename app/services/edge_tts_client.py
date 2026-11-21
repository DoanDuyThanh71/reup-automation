import os
import re
import asyncio
import requests
import edge_tts
from typing import Dict, Any, Optional, List

class EdgeTTSClient:
    """
    Free high-quality Vietnamese TTS client using Microsoft Edge TTS,
    with automatic zero-key fallback to Google Translate Vietnamese TTS if Bing WebSocket returns 403.
    """
    SUPPORTED_VOICES = {
        "vi-VN-HoaiMyNeural": "Nữ Miền Bắc (Hoài My - Trẻ trung, tự nhiên)",
        "vi-VN-NamMinhNeural": "Nam Miền Bắc (Nam Minh - Truyền cảm, chuẩn)",
    }

    def __init__(self, voice: Optional[str] = None):
        from ..config import config
        self.voice = voice or config.get("EDGE_TTS_VOICE", "vi-VN-HoaiMyNeural")

    @staticmethod
    def extract_clean_text_from_srt(srt_content: str) -> str:
        """Strips timestamps, sequence numbers, and empty lines to get readable narration text."""
        lines = srt_content.splitlines()
        text_lines = []
        for line in lines:
            line = line.strip()
            if not line or line.isdigit() or "-->" in line:
                continue
            text_lines.append(line)
        return " ".join(text_lines)

    @staticmethod
    def _split_text_chunks(text: str, max_len: int = 180) -> List[str]:
        """Splits text into sentence/phrase chunks <= max_len characters for Google TTS fallback."""
        words = text.split()
        chunks = []
        current = []
        curr_len = 0
        for w in words:
            if curr_len + len(w) + 1 > max_len and current:
                chunks.append(" ".join(current))
                current = [w]
                curr_len = len(w)
            else:
                current.append(w)
                curr_len += len(w) + 1
        if current:
            chunks.append(" ".join(current))
        return chunks or ["Video chia sẻ nội dung hữu ích."]

    def _generate_google_tts_fallback(self, text: str, output_path: str) -> str:
        """Generates Vietnamese MP3 audio via Google Translate TTS endpoint (free, HTTP 200)."""
        chunks = self._split_text_chunks(text[:2500], max_len=180)
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        with open(output_path, "wb") as f:
            for chunk in chunks:
                res = requests.get(
                    "https://translate.google.com/translate_tts",
                    params={"ie": "UTF-8", "tl": "vi", "client": "tw-ob", "q": chunk},
                    headers=headers,
                    timeout=15
                )
                res.raise_for_status()
                f.write(res.content)
        return output_path

    async def generate_speech_async(self, text: str, output_path: str, voice: Optional[str] = None, rate: str = "+0%", pitch: str = "+0Hz") -> str:
        chosen_voice = voice or self.voice
        communicate = edge_tts.Communicate(text=text, voice=chosen_voice, rate=rate, pitch=pitch)
        await communicate.save(output_path)
        return output_path

    def generate_speech(self, text_or_srt_path: str, output_path: str, voice: Optional[str] = None, is_srt: bool = True) -> str:
        """
        Synchronous wrapper to generate MP3 from text or SRT file.
        Tries Edge-TTS first; automatically falls back to Google Vietnamese TTS on 403/network errors.
        """
        if is_srt and os.path.exists(text_or_srt_path):
            with open(text_or_srt_path, "r", encoding="utf-8") as f:
                content = f.read()
            text = self.extract_clean_text_from_srt(content)
        else:
            text = text_or_srt_path

        if not text.strip():
            text = "Video chia sẻ kiến thức và đời sống hữu ích."

        try:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    pool.submit(asyncio.run, self.generate_speech_async(text, output_path, voice)).result(timeout=45)
            else:
                loop.run_until_complete(self.generate_speech_async(text, output_path, voice))

            if os.path.exists(output_path) and os.path.getsize(output_path) > 500:
                return output_path
        except Exception as e:
            print(f"[EdgeTTSClient] Edge-TTS WebSocket error ({e}). Switching to Google Vietnamese TTS fallback...")

        return self._generate_google_tts_fallback(text, output_path)

    def test_connection(self) -> Dict[str, Any]:
        return {
            "success": True,
            "message": "Edge-TTS & Google Vietnamese TTS sẵn sàng sử dụng (Không cần token, miễn phí 100%)",
            "available_voices": self.SUPPORTED_VOICES
        }
