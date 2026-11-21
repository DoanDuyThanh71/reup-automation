import os
from typing import Dict, Any, Optional
from ..config import config
from ..services.vbee_client import VbeeClient, DEFAULT_VBEE_APP_ID, DEFAULT_VBEE_TOKEN
from ..services.edge_tts_client import EdgeTTSClient

class DubbingAgent:
    """
    Agent 4: Dubs video narration using Vbee Official TTS API (default) with per-cue
    millisecond timestamp synchronization, and automatic fallback to Edge-TTS / Google TTS.
    """
    def __init__(self):
        self.vbee = VbeeClient()
        self.edge_tts = EdgeTTSClient()

    def run(self, translated_srt_path: str, output_audio_path: str, voice_code: Optional[str] = None) -> Dict[str, Any]:
        os.makedirs(os.path.dirname(os.path.abspath(output_audio_path)), exist_ok=True)
        provider = (config.get("TTS_PROVIDER", "vbee") or "vbee").lower()

        vbee_app_id = config.get("VBEE_APP_ID", DEFAULT_VBEE_APP_ID) or DEFAULT_VBEE_APP_ID
        vbee_token = config.get("VBEE_ACCESS_TOKEN", DEFAULT_VBEE_TOKEN) or DEFAULT_VBEE_TOKEN
        vbee_cookie = config.get("VBEE_REFRESH_TOKEN_COOKIE", "")

        # Refresh client instances with latest config
        self.vbee.app_id = vbee_app_id
        self.vbee.access_token = vbee_token
        self.vbee.refresh_token_cookie = vbee_cookie or self.vbee.refresh_token_cookie
        self.edge_tts.voice = config.get("EDGE_TTS_VOICE", "vi-VN-HoaiMyNeural")

        # Try Vbee Official API (or Studio fallback) when provider is vbee
        if provider == "vbee" and ((vbee_app_id and vbee_token) or vbee_cookie.strip()):
            try:
                configured_voice = config.get("VBEE_VOICE_CODE", "hn_female_ngochuyen_full_48k-fhg")
                actual_voice = voice_code if (voice_code and "Neural" not in voice_code) else configured_voice
                self.vbee.process_full_dubbing(translated_srt_path, output_audio_path, voice_code=actual_voice)
                return {
                    "success": True,
                    "audio_path": output_audio_path,
                    "provider": "vbee",
                    "voice": actual_voice
                }
            except Exception as e:
                print(f"[DubbingAgent] Vbee error: {e}. Falling back to Edge-TTS...")

        # Edge-TTS fallback
        fallback_voice = voice_code if (voice_code and "Neural" in voice_code) else config.get("EDGE_TTS_VOICE", "vi-VN-HoaiMyNeural")
        self.edge_tts.generate_speech(translated_srt_path, output_audio_path, voice=fallback_voice, is_srt=True)

        return {
            "success": True,
            "audio_path": output_audio_path,
            "provider": "edge-tts",
            "voice": fallback_voice
        }
