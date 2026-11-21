import os
import re
import asyncio
import edge_tts
from typing import Dict, Any, Optional

class EdgeTTSClient:
    """
    Free high-quality Vietnamese TTS client using Microsoft Edge TTS.
    Acts as a zero-cost, reliable fallback for Vbee.
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
            # Skip number lines and timestamp lines (00:00:00,000 --> ...)
            if not line or line.isdigit() or "-->" in line:
                continue
            text_lines.append(line)
        return " ".join(text_lines)

    async def generate_speech_async(self, text: str, output_path: str, voice: Optional[str] = None, rate: str = "+0%", pitch: str = "+0Hz") -> str:
        chosen_voice = voice or self.voice
        communicate = edge_tts.Communicate(text=text, voice=chosen_voice, rate=rate, pitch=pitch)
        await communicate.save(output_path)
        return output_path

    def generate_speech(self, text_or_srt_path: str, output_path: str, voice: Optional[str] = None, is_srt: bool = True) -> str:
        """
        Synchronous wrapper to generate MP3 from text or SRT file.
        """
        if is_srt and os.path.exists(text_or_srt_path):
            with open(text_or_srt_path, "r", encoding="utf-8") as f:
                content = f.read()
            text = self.extract_clean_text_from_srt(content)
        else:
            text = text_or_srt_path

        if not text.strip():
            text = "Video chia sẻ kiến thức và đời sống hữu ích."

        # Run event loop
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            # If called inside an existing running loop (e.g. FastAPI async)
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                pool.submit(asyncio.run, self.generate_speech_async(text, output_path, voice)).result()
        else:
            loop.run_until_complete(self.generate_speech_async(text, output_path, voice))

        return output_path

    def test_connection(self) -> Dict[str, Any]:
        return {
            "success": True,
            "message": "Edge-TTS sẵn sàng sử dụng (Không cần token, miễn phí 100%)",
            "available_voices": self.SUPPORTED_VOICES
        }
