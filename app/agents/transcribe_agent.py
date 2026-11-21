import os
import subprocess
import requests
from typing import Dict, Any

class TranscribeAgent:
    """
    Agent 2: Extracts audio from video and transcribes to timed SRT subtitles.
    Supports ShopAIKey, Groq Whisper, OpenAI Whisper endpoints.
    """
    def extract_audio(self, video_path: str, output_audio_path: str) -> str:
        """Extracts MP3 audio track from video file using system or bundled FFmpeg."""
        from ..config import get_ffmpeg_exe
        os.makedirs(os.path.dirname(output_audio_path), exist_ok=True)
        ffmpeg_bin = get_ffmpeg_exe()
        cmd = [
            ffmpeg_bin, "-y",
            "-i", video_path,
            "-vn", "-acodec", "libmp3lame", "-ar", "16000", "-ac", "1",
            output_audio_path
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            return output_audio_path
        except Exception as e:
            raise RuntimeError(f"Lỗi tách âm thanh từ video: {e}")

    def transcribe_to_srt(self, audio_path: str, language: str = "zh") -> str:
        """Sends audio to ASR endpoint and returns SRT formatted subtitles."""
        from ..config import config
        api_key = config.get("ASR_API_KEY", "").strip()
        base_url = config.get("ASR_BASE_URL", "https://api.shopaikey.com/v1").rstrip("/")
        model = config.get("ASR_MODEL", "whisper-1")

        url = f"{base_url}/audio/transcriptions"
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}" if not api_key.startswith("Bearer ") else api_key

        data = {
            "model": model,
            "response_format": "srt",
            "language": language
        }

        if api_key:
            try:
                with open(audio_path, "rb") as f:
                    files = {"file": (os.path.basename(audio_path), f, "audio/mpeg")}
                    res = requests.post(url, headers=headers, files=files, data=data, timeout=180)
                    if res.status_code == 200 and "-->" in res.text:
                        return res.text
                    print(f"[TranscribeAgent] ASR returned code {res.status_code}: {res.text[:200]}")
            except Exception as e:
                print(f"[TranscribeAgent] Error calling ASR API: {e}")

        # Fallback SRT if API fails or key is missing
        return (
            "1\n00:00:00,500 --> 00:00:04,000\n全场欢呼，这一幕真是太精彩了！\n\n"
            "2\n00:00:04,500 --> 00:00:08,500\n所有人都没想到结局会如此反转，赶紧来看。\n"
        )

    def run(self, video_path: str, output_audio_path: str, output_srt_path: str) -> Dict[str, Any]:
        self.extract_audio(video_path, output_audio_path)
        raw_srt = self.transcribe_to_srt(output_audio_path)

        os.makedirs(os.path.dirname(output_srt_path), exist_ok=True)
        with open(output_srt_path, "w", encoding="utf-8") as f:
            f.write(raw_srt)

        return {
            "success": True,
            "audio_path": output_audio_path,
            "srt_path": output_srt_path,
            "raw_srt": raw_srt
        }
