import os
from typing import Dict, Any, Optional
from ..config import config
from ..services.vbee_client import VbeeClient
from ..services.edge_tts_client import EdgeTTSClient

class DubbingAgent:
    """
    Agent 4: Dubs video narration using Vbee Studio API with automatic fallback to Edge-TTS.
    """
    def __init__(self):
        self.vbee = VbeeClient()
        self.edge_tts = EdgeTTSClient()

    def run(self, translated_srt_path: str, output_audio_path: str, voice_code: Optional[str] = None) -> Dict[str, Any]:
        os.makedirs(os.path.dirname(output_audio_path), exist_ok=True)
        provider = config.get("TTS_PROVIDER", "vbee").lower()
        vbee_cookie = config.get("VBEE_REFRESH_TOKEN_COOKIE", "")

        used_provider = provider
        # Try Vbee if requested and cookie is available
        if provider == "vbee" and vbee_cookie.strip():
            try:
                actual_voice = voice_code or config.get("VBEE_VOICE_CODE", "vi_female_hn_ngoc_huyen")
                self.vbee.process_full_dubbing(translated_srt_path, output_audio_path, voice_code=actual_voice)
                return {
                    "success": True,
                    "audio_path": output_audio_path,
                    "provider": "vbee",
                    "voice": actual_voice
                }
            except Exception as e:
                print(f"[DubbingAgent] Vbee error: {e}. Falling back to Edge-TTS...")
                used_provider = "edge-tts"

        # Edge-TTS fallback
        fallback_voice = voice_code if voice_code and "Neural" in voice_code else config.get("EDGE_TTS_VOICE", "vi-VN-HoaiMyNeural")
        self.edge_tts.generate_speech(translated_srt_path, output_audio_path, voice=fallback_voice, is_srt=True)

        return {
            "success": True,
            "audio_path": output_audio_path,
            "provider": "edge-tts",
            "voice": fallback_voice
        }
