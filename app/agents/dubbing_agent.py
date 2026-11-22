import os
from typing import Dict, Any, Optional
from ..config import config
from ..services.vbee_client import VbeeClient, DEFAULT_VBEE_APP_ID, DEFAULT_VBEE_TOKEN
from ..services.edge_tts_client import EdgeTTSClient
from ..services.local_tts_client import LocalTTSClient


class DubbingAgent:
    """
    Agent 4: Dubs video narration supporting 3 tiers:
    1. Local On-Device Voice (`local` -> Sherpa-ONNX Piper VITS / VieNeu-TTS 48kHz / Custom Local Server)
       with 1:1 millisecond SRT timeline sync and zero token/API cost.
    2. Vbee Official TTS API (`vbee`) with per-cue millisecond timestamp sync.
    3. Microsoft Edge-TTS / Google TTS (`edge-tts`) zero-RAM cloud fallback.
    """
    def __init__(self):
        self.vbee = VbeeClient()
        self.edge_tts = EdgeTTSClient()

    def run(self, translated_srt_path: str, output_audio_path: str, voice_code: Optional[str] = None) -> Dict[str, Any]:
        os.makedirs(os.path.dirname(os.path.abspath(output_audio_path)), exist_ok=True)
        provider = (config.get("TTS_PROVIDER", "vbee") or "vbee").lower()

        if voice_code and voice_code.startswith("local:"):
            provider = "local"
            local_engine = voice_code.split(":", 1)[1]
        else:
            local_engine = None

        # 1. Local On-Device Voice Mode
        if provider == "local":
            try:
                local_tts = LocalTTSClient(engine=local_engine)
                local_tts.process_full_dubbing(translated_srt_path, output_audio_path)
                return {
                    "success": True,
                    "audio_path": output_audio_path,
                    "provider": "local-tts",
                    "voice": f"local:{local_tts.engine}",
                }
            except Exception as e:
                print(f"[DubbingAgent] Local TTS error ({e}). Falling back to Vbee / Edge-TTS...")

        # 2. Vbee Official API Mode
        vbee_app_id = config.get("VBEE_APP_ID", DEFAULT_VBEE_APP_ID) or DEFAULT_VBEE_APP_ID
        vbee_token = config.get("VBEE_ACCESS_TOKEN", DEFAULT_VBEE_TOKEN) or DEFAULT_VBEE_TOKEN
        vbee_cookie = config.get("VBEE_REFRESH_TOKEN_COOKIE", "")

        self.vbee.app_id = vbee_app_id
        self.vbee.access_token = vbee_token
        self.vbee.refresh_token_cookie = vbee_cookie or self.vbee.refresh_token_cookie
        self.edge_tts.voice = config.get("EDGE_TTS_VOICE", "vi-VN-HoaiMyNeural")

        if provider in ("vbee", "local") and ((vbee_app_id and vbee_token) or vbee_cookie.strip()):
            try:
                configured_voice = config.get("VBEE_VOICE_CODE", "hn_female_ngochuyen_full_48k-fhg")
                actual_voice = voice_code if (voice_code and "Neural" not in voice_code and not voice_code.startswith("local:")) else configured_voice
                self.vbee.process_full_dubbing(translated_srt_path, output_audio_path, voice_code=actual_voice)
                return {
                    "success": True,
                    "audio_path": output_audio_path,
                    "provider": "vbee",
                    "voice": actual_voice
                }
            except Exception as e:
                print(f"[DubbingAgent] Vbee error: {e}. Falling back to Edge-TTS...")

        # 3. Edge-TTS Cloud Free Fallback
        fallback_voice = voice_code if (voice_code and "Neural" in voice_code) else config.get("EDGE_TTS_VOICE", "vi-VN-HoaiMyNeural")
        self.edge_tts.generate_speech(translated_srt_path, output_audio_path, voice=fallback_voice, is_srt=True)

        return {
            "success": True,
            "audio_path": output_audio_path,
            "provider": "edge-tts",
            "voice": fallback_voice
        }
