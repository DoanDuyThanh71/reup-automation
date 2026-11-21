import os
import time
import wave
import array
import hashlib
import subprocess
import concurrent.futures
import requests
from typing import Dict, Any, Optional, List

from .ai_client import parse_srt_blocks, format_srt_blocks

VOICE_MAP = {
    "vi_female_hn_ngoc_huyen": "hn_female_ngochuyen_full_48k-fhg",
    "vi_male_hn_nam_mien_bac": "hn_male_manhdung_news_48k-fhg",
    "vi_female_sg_lan_nhi": "sg_female_thaotrinh_full_44k-phg",
    "hn_female_ngochuyen_full_48k-fhg": "hn_female_ngochuyen_full_48k-fhg",
    "hn_male_manhdung_news_48k-fhg": "hn_male_manhdung_news_48k-fhg",
    "sg_female_thaotrinh_full_44k-phg": "sg_female_thaotrinh_full_44k-phg",
}

DEFAULT_VBEE_APP_ID = "63a47dd0-f273-4b4a-a9bf-ae354f38b554"
DEFAULT_VBEE_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpYXQiOjE3Nzg3NDA4MDN9.vSKa74Mutjtk6lGpEg2iuCItXZUrn9W9EBymYflEuXo"

class VbeeClient:
    """
    Vbee Official AIVoice TTS & Timestamp-Synchronized Dubbing Client.
    - Uses Vbee Developer API (`https://vbee.vn/api/v1/tts`) with App ID & Bearer Token by default:
      App ID: 63a47dd0-f273-4b4a-a9bf-ae354f38b554
    - Synthesizes each SRT subtitle block individually in parallel and places each voice clip
      at its exact start_ms timestamp on a 44.1kHz PCM timeline, automatically adjusting speed
      (atempo) when a sentence exceeds its time window so voice, subtitle, and original video stay 100% locked.
    """
    TTS_API_URL = "https://vbee.vn/api/v1/tts"
    SAMPLE_RATE = 44100

    def __init__(self, refresh_token_cookie: Optional[str] = None, app_id: Optional[str] = None, access_token: Optional[str] = None):
        from ..config import config
        self.app_id = (app_id or config.get("VBEE_APP_ID", DEFAULT_VBEE_APP_ID) or DEFAULT_VBEE_APP_ID).strip()
        self.access_token = (access_token or config.get("VBEE_ACCESS_TOKEN", DEFAULT_VBEE_TOKEN) or DEFAULT_VBEE_TOKEN).strip()
        self.refresh_token_cookie = (refresh_token_cookie or config.get("VBEE_REFRESH_TOKEN_COOKIE", "")).strip()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
        })

    def _load_latest_credentials(self):
        from ..config import config
        cfg_app_id = config.get("VBEE_APP_ID", DEFAULT_VBEE_APP_ID).strip()
        cfg_token = config.get("VBEE_ACCESS_TOKEN", DEFAULT_VBEE_TOKEN).strip()
        if cfg_app_id:
            self.app_id = cfg_app_id
        if cfg_token:
            self.access_token = cfg_token

    def refresh_access_token(self) -> str:
        """Returns configured Bearer token or refreshes via Vbee Studio cookie if provided."""
        self._load_latest_credentials()
        if self.access_token and not self.refresh_token_cookie:
            return self.access_token

        if self.refresh_token_cookie:
            url = "https://accounts.vbee.vn/api/v1/auth/refresh-token"
            headers = {"Cookie": self.refresh_token_cookie, "Content-Type": "application/json"}
            res = self.session.post(url, json={"clientId": "aivoice-web-application"}, headers=headers, timeout=15)
            res.raise_for_status()
            data = res.json()
            token = data.get("result", {}).get("access_token") or data.get("access_token")
            if token:
                self.access_token = token
                return token

        if self.access_token:
            return self.access_token
        raise ValueError("Chưa cấu hình VBEE_ACCESS_TOKEN hoặc VBEE_REFRESH_TOKEN_COOKIE!")

    def test_connection(self) -> Dict[str, Any]:
        """Tests Vbee TTS API with the configured App ID and Bearer Token."""
        try:
            self._load_latest_credentials()
            if not self.app_id or not self.access_token:
                return {"success": False, "error": "Thiếu VBEE_APP_ID hoặc VBEE_ACCESS_TOKEN"}

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }
            payload = {
                "app_id": self.app_id,
                "response_type": "indirect",
                "callback_url": "https://httpbin.org/post",
                "input_text": "Kiểm tra kết nối Vbee thành công.",
                "voice_code": "hn_female_ngochuyen_full_48k-fhg",
                "audio_type": "mp3",
                "bitrate": 128,
                "speed_rate": "1.0"
            }
            res = requests.post(self.TTS_API_URL, headers=headers, json=payload, timeout=15)
            data = res.json()
            if res.status_code == 200 and data.get("status") == 1:
                req_id = data.get("result", {}).get("request_id", "")
                return {
                    "success": True,
                    "message": f"Kết nối Vbee TTS API thành công! (App ID: {self.app_id[:8]}..., Request: {req_id[:8]}...)",
                    "app_id": self.app_id
                }
            return {"success": False, "error": f"Vbee API trả về lỗi: {data}"}
        except Exception as e:
            return {"success": False, "error": f"Lỗi kết nối Vbee: {str(e)}"}

    def synthesize_text_to_mp3(self, text: str, output_mp3_path: str, voice_code: str = "hn_female_ngochuyen_full_48k-fhg", speed: float = 1.0) -> str:
        """
        Synthesizes a single sentence/segment to MP3 via Vbee Official API (`POST https://vbee.vn/api/v1/tts`),
        with disk caching so identical lines are instant.
        """
        self._load_latest_credentials()
        actual_voice = VOICE_MAP.get(voice_code, voice_code)
        if not actual_voice or actual_voice.startswith("vi-VN-"):
            actual_voice = "hn_female_ngochuyen_full_48k-fhg"

        clean_text = text.strip()
        if not clean_text:
            raise ValueError("Empty text for Vbee TTS")

        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        cache_dir = os.path.join(base_dir, "temp", "vbee_cache")
        os.makedirs(cache_dir, exist_ok=True)
        cache_key = hashlib.sha1(f"{self.app_id}|{actual_voice}|{speed}|{clean_text}".encode("utf-8")).hexdigest()[:20]
        cached_mp3 = os.path.join(cache_dir, f"vbee_{cache_key}.mp3")

        if os.path.exists(cached_mp3) and os.path.getsize(cached_mp3) > 400:
            if os.path.abspath(cached_mp3) != os.path.abspath(output_mp3_path):
                with open(cached_mp3, "rb") as src, open(output_mp3_path, "wb") as dst:
                    dst.write(src.read())
            return output_mp3_path

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "app_id": self.app_id,
            "response_type": "indirect",
            "callback_url": "https://httpbin.org/post",
            "input_text": clean_text,
            "voice_code": actual_voice,
            "audio_type": "mp3",
            "bitrate": 128,
            "speed_rate": str(round(max(0.7, min(1.5, speed)), 2))
        }

        res = requests.post(self.TTS_API_URL, headers=headers, json=payload, timeout=20)
        res.raise_for_status()
        data = res.json()
        if data.get("status") != 1:
            raise RuntimeError(f"Vbee TTS tạo request thất bại: {data}")

        req_id = data.get("result", {}).get("request_id")
        if not req_id:
            raise RuntimeError(f"Vbee TTS không trả về request_id: {data}")

        # Poll for completion
        poll_url = f"{self.TTS_API_URL}/{req_id}"
        for _ in range(35):
            time.sleep(1.2)
            p_res = requests.get(poll_url, headers=headers, timeout=15)
            if p_res.status_code == 200:
                res_obj = p_res.json().get("result", {})
                status = str(res_obj.get("status", "")).upper()
                audio_link = res_obj.get("audio_link") or res_obj.get("audioLink")
                if status in ("SUCCESS", "COMPLETED", "DONE") and audio_link:
                    dl = requests.get(audio_link, timeout=30)
                    dl.raise_for_status()
                    if len(dl.content) < 300:
                        raise RuntimeError("Vbee trả về file âm thanh rỗng")
                    with open(cached_mp3, "wb") as f:
                        f.write(dl.content)
                    with open(output_mp3_path, "wb") as f:
                        f.write(dl.content)
                    return output_mp3_path
                if status in ("FAILED", "ERROR"):
                    raise RuntimeError(f"Vbee xử lý lỗi: {res_obj}")

        raise TimeoutError(f"Quá thời gian chờ Vbee TTS cho câu: {clean_text[:30]}")

    def _mp3_to_trimmed_pcm_samples(self, mp3_path: str, target_slot_ms: int) -> array.array:
        """
        Decodes an MP3 segment to 44.1kHz mono 16-bit PCM samples, removes leading/trailing silence,
        and automatically speeds up with atempo if the speech exceeds target_slot_ms.
        """
        from ..config import get_ffmpeg_exe
        ffmpeg_bin = get_ffmpeg_exe()
        tmp_wav = mp3_path + ".trim.wav"
        tmp_fit_wav = mp3_path + ".fit.wav"

        try:
            # 1. Trim silence at start and end so voice starts right at start_ms
            trim_filter = (
                "silenceremove=start_periods=1:start_silence=0.03:start_threshold=-42dB:"
                "stop_periods=-1:stop_silence=0.06:stop_threshold=-42dB"
            )
            cmd1 = [
                ffmpeg_bin, "-y", "-loglevel", "error",
                "-i", mp3_path,
                "-af", trim_filter,
                "-ac", "1", "-ar", str(self.SAMPLE_RATE), "-sample_fmt", "s16",
                tmp_wav
            ]
            subprocess.run(cmd1, check=True, capture_output=True)

            with wave.open(tmp_wav, "rb") as wf:
                n_frames = wf.getnframes()
                raw_bytes = wf.readframes(n_frames)

            speech_ms = int((n_frames / self.SAMPLE_RATE) * 1000)

            # 2. If speech is longer than available slot window, apply atempo (up to 1.45x) so it fits cleanly
            if target_slot_ms > 400 and speech_ms > target_slot_ms * 1.03:
                tempo = min(1.45, max(1.05, speech_ms / float(target_slot_ms)))
                cmd2 = [
                    ffmpeg_bin, "-y", "-loglevel", "error",
                    "-i", tmp_wav,
                    "-af", f"atempo={tempo:.3f}",
                    "-ac", "1", "-ar", str(self.SAMPLE_RATE), "-sample_fmt", "s16",
                    tmp_fit_wav
                ]
                subprocess.run(cmd2, check=True, capture_output=True)
                with wave.open(tmp_fit_wav, "rb") as wf2:
                    raw_bytes = wf2.readframes(wf2.getnframes())

            samples = array.array("h")
            if len(raw_bytes) % 2 == 1:
                raw_bytes = raw_bytes[:-1]
            samples.frombytes(raw_bytes)
            return samples
        finally:
            for p in (tmp_wav, tmp_fit_wav):
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass

    def process_full_dubbing(self, srt_path: str, output_audio_path: str, voice_code: str = "hn_female_ngochuyen_full_48k-fhg") -> str:
        """
        Synthesizes every subtitle block in srt_path via Vbee Official TTS API (parallel workers)
        and places each voice clip at its exact start_ms timestamp on the master timeline so that
        voice, burned subtitles, and original video stay 100% synchronized.
        """
        from ..config import get_ffmpeg_exe
        from .edge_tts_client import EdgeTTSClient

        with open(srt_path, "r", encoding="utf-8") as f:
            srt_content = f.read()

        blocks = parse_srt_blocks(srt_content)
        if not blocks:
            return self.synthesize_text_to_mp3("Video chia sẻ nội dung hấp dẫn.", output_audio_path, voice_code=voice_code)

        work_dir = os.path.dirname(os.path.abspath(output_audio_path))
        seg_dir = os.path.join(work_dir, "_vbee_segments")
        os.makedirs(seg_dir, exist_ok=True)

        edge_fallback = EdgeTTSClient()

        def _synth_one(idx_and_block):
            i, blk = idx_and_block
            seg_mp3 = os.path.join(seg_dir, f"seg_{i:04d}.mp3")
            try:
                self.synthesize_text_to_mp3(blk["text"], seg_mp3, voice_code=voice_code, speed=1.05)
            except Exception as e:
                print(f"[VbeeClient] Segment {i} Vbee error ({e}), using fallback TTS for segment...")
                edge_fallback.generate_speech(blk["text"], seg_mp3, is_srt=False)
            return i, seg_mp3

        # Synthesize segments concurrently (4 workers to respect Vbee concurrency while finishing fast)
        seg_files: Dict[int, str] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(_synth_one, (i, b)) for i, b in enumerate(blocks)]
            for fut in concurrent.futures.as_completed(futures):
                i, path = fut.result()
                seg_files[i] = path

        # Build master 44.1kHz PCM timeline buffer aligned to exact start_ms of each SRT cue
        last_end_ms = max(b["end_ms"] for b in blocks) + 3000
        total_samples = int((last_end_ms / 1000.0) * self.SAMPLE_RATE)
        timeline = array.array("h", [0]) * total_samples

        cursor_sample = 0
        for i, blk in enumerate(blocks):
            start_ms = blk["start_ms"]
            end_ms = blk["end_ms"]
            next_start_ms = blocks[i + 1]["start_ms"] if i + 1 < len(blocks) else (end_ms + 3000)

            # Available window before next subtitle starts
            max_window_ms = max(600, min(end_ms - start_ms + 400, next_start_ms - start_ms - 40))
            seg_mp3 = seg_files.get(i)
            if not seg_mp3 or not os.path.exists(seg_mp3):
                continue

            try:
                seg_samples = self._mp3_to_trimmed_pcm_samples(seg_mp3, target_slot_ms=max_window_ms)
            except Exception as e:
                print(f"[VbeeClient] Segment {i} PCM decode failed: {e}")
                continue

            start_sample = max(cursor_sample, int((start_ms / 1000.0) * self.SAMPLE_RATE))
            end_sample = start_sample + len(seg_samples)

            if end_sample > len(timeline):
                timeline.extend([0] * (end_sample - len(timeline) + self.SAMPLE_RATE))

            timeline[start_sample:end_sample] = seg_samples
            cursor_sample = end_sample + int(0.03 * self.SAMPLE_RATE)

            # Sync SRT block display timestamps to exact voice placement
            actual_start_ms = int((start_sample / self.SAMPLE_RATE) * 1000)
            actual_end_ms = int((end_sample / self.SAMPLE_RATE) * 1000)
            blk["start_ms"] = actual_start_ms
            blk["end_ms"] = max(actual_start_ms + 500, min(actual_end_ms + 150, next_start_ms - 30))

        # Write synchronized SRT back so burned subtitles match the Vbee voice to the millisecond
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(format_srt_blocks(blocks))

        # Export master timeline WAV -> MP3
        master_wav = output_audio_path + ".master.wav"
        try:
            with wave.open(master_wav, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.SAMPLE_RATE)
                wf.writeframes(timeline.tobytes())

            ffmpeg_bin = get_ffmpeg_exe()
            subprocess.run([
                ffmpeg_bin, "-y", "-loglevel", "error",
                "-i", master_wav,
                "-c:a", "libmp3lame", "-b:a", "192k",
                output_audio_path
            ], check=True, capture_output=True)
        finally:
            if os.path.exists(master_wav):
                try:
                    os.remove(master_wav)
                except Exception:
                    pass

        return output_audio_path
