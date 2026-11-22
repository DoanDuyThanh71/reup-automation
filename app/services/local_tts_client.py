import os
import sys
import wave
import array
import shutil
import tarfile
import urllib.request
import threading
import subprocess
from typing import Dict, Any, Optional
from .ai_client import parse_srt_blocks, format_srt_blocks

_SHERPA_SYNTH_LOCK = threading.Lock()

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MODELS_DIR = os.path.join(BASE_DIR, "data", "models", "tts")
SHERPA_MODEL_NAME = "vits-piper-vi_VN-vais1000-medium"
SHERPA_MODEL_URL = f"https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/{SHERPA_MODEL_NAME}.tar.bz2"
SHERPA_MODEL_DIR = os.path.join(MODELS_DIR, SHERPA_MODEL_NAME)


# Tuned Review Phim (Movie Recap) Voice Presets for Local / Gemini Free Audio
LOCAL_VOICE_PRESETS: Dict[str, Dict[str, Any]] = {
    "gemini_nam_charon": {
        "label": "🎬 Gemini AI Review Phim — Nam Trầm Kịch Tính (Charon 1.15x • Miễn phí qua Key Gemini)",
        "kind": "gemini_tts",
        "voice_name": "Charon",
        "style_prompt": "Đọc giọng nam MC review phim kịch tính, cuốn hút, dứt khoát, tự nhiên: ",
        "tempo": 1.15,
    },
    "gemini_nu_kore": {
        "label": "🎬 Gemini AI Review Phim — Nữ Sắc Sảo Tổng Tài (Kore 1.15x • Miễn phí qua Key Gemini)",
        "kind": "gemini_tts",
        "voice_name": "Kore",
        "style_prompt": "Đọc giọng nữ review phim ngôn tình tổng tài sắc sảo, lôi cuốn, dứt khoát: ",
        "tempo": 1.15,
    },
    "rv_nu_kich_tinh": {
        "label": "🖥 Offline ONNX Nhẹ — Nữ Bắc VAIS-1000 (1.14x • Không cần mạng)",
        "kind": "sherpa",
        "speed": 1.14,
        "af_chain": "equalizer=f=3200:width_type=o:width=2:g=3,acompressor=threshold=-18dB:ratio=3:attack=5:release=60:makeup=2",
    },
    "rv_nam_tram": {
        "label": "🖥 Offline ONNX Nhẹ — Nam Trầm Giả Lập (Không cần mạng)",
        "kind": "sherpa",
        "speed": 1.02,
        "af_chain": "asetrate=22050*0.84,aresample=44100,atempo=1.26,equalizer=f=180:width_type=o:width=2:g=3,acompressor=threshold=-18dB:ratio=3:makeup=2",
    },
    "rv_nu_tu_nhien": {
        "label": "🖥 Offline ONNX Nhẹ — Nữ Đọc Truyện 1.04x",
        "kind": "sherpa",
        "speed": 1.04,
        "af_chain": "acompressor=threshold=-20dB:ratio=2.5:makeup=1.5",
    },
    "sherpa_onnx": {
        "label": "🖥 Offline ONNX Nhẹ — Nữ Bắc VAIS-1000",
        "kind": "sherpa",
        "speed": 1.12,
        "af_chain": "equalizer=f=3200:width_type=o:width=2:g=2.5,acompressor=threshold=-18dB:ratio=3:attack=5:release=60:makeup=2",
    },
}


class LocalTTSClient:
    """
    On-Device Offline Vietnamese TTS Engine with Movie-Recap ("Review Phim") Voice Presets
    and Millisecond SRT Timeline Synchronization.
    """

    SAMPLE_RATE = 44100
    _sherpa_instance = None
    _sherpa_model_dir_loaded = None

    def __init__(
        self,
        engine: Optional[str] = None,
        custom_url: Optional[str] = None,
        ref_wav: Optional[str] = None,
        preset: Optional[str] = None,
    ):
        from ..config import config
        raw_eng = (engine or config.get("LOCAL_TTS_ENGINE", "rv_nu_kich_tinh") or "rv_nu_kich_tinh").strip().lower()
        if raw_eng in LOCAL_VOICE_PRESETS:
            self.engine = "sherpa_onnx"
            self.preset_name = preset or raw_eng
        else:
            self.engine = raw_eng
            self.preset_name = preset or "rv_nu_kich_tinh"

        self.custom_url = (custom_url or config.get("LOCAL_TTS_URL", "")).strip()
        self.ref_wav = (ref_wav or config.get("LOCAL_VOICE_REF_WAV", "")).strip()
        self.threads = int(config.get("LOCAL_TTS_THREADS", "4") or "4")

    @classmethod
    def check_installed_backends(cls) -> Dict[str, Any]:
        sherpa_pkg = False
        try:
            import sherpa_onnx  # noqa: F401
            sherpa_pkg = True
        except Exception:
            pass

        onnx_file = os.path.join(SHERPA_MODEL_DIR, "vi_VN-vais1000-medium.onnx")
        sherpa_model_ready = os.path.exists(onnx_file) and os.path.getsize(onnx_file) > 10_000_000

        vieneu_pkg = False
        try:
            import vieneu  # noqa: F401
            vieneu_pkg = True
        except Exception:
            pass

        return {
            "sherpa_onnx_installed": sherpa_pkg,
            "sherpa_model_downloaded": sherpa_model_ready,
            "sherpa_ready": bool(sherpa_pkg and sherpa_model_ready),
            "sherpa_model_dir": SHERPA_MODEL_DIR,
            "vieneu_installed": vieneu_pkg,
            "available_presets": {k: v["label"] for k, v in LOCAL_VOICE_PRESETS.items() if k != "sherpa_onnx"},
        }

    @classmethod
    def install_sherpa_vietnamese(cls) -> Dict[str, Any]:
        """
        1-Click Auto-Installer:
        - In Python dev mode: installs `sherpa-onnx` wheel if missing.
        - In `.exe` mode: `sherpa-onnx` is already bundled inside `_internal/`, so it only downloads
          the 64MB Vietnamese model archive into `./data/models/tts/`.
        """
        os.makedirs(MODELS_DIR, exist_ok=True)
        try:
            try:
                import sherpa_onnx  # noqa: F401
            except ImportError:
                if getattr(sys, "frozen", False):
                    return {"success": False, "error": "Bản .exe thiếu module sherpa_onnx nội bộ."}
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "sherpa-onnx<2.0", "-q"],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=240,
                )

            onnx_file = os.path.join(SHERPA_MODEL_DIR, "vi_VN-vais1000-medium.onnx")
            if not (os.path.exists(onnx_file) and os.path.getsize(onnx_file) > 10_000_000):
                archive_path = os.path.join(MODELS_DIR, f"{SHERPA_MODEL_NAME}.tar.bz2")
                urllib.request.urlretrieve(SHERPA_MODEL_URL, archive_path)
                with tarfile.open(archive_path, "r:bz2") as tar:
                    tar.extractall(path=MODELS_DIR)
                try:
                    os.remove(archive_path)
                except Exception:
                    pass

            cls._sherpa_instance = None
            status = cls.check_installed_backends()
            if status["sherpa_ready"]:
                from ..config import config
                config.set_many({"LOCAL_TTS_ENGINE": "rv_nu_kich_tinh"})
                return {
                    "success": True,
                    "message": "Đã cài đặt xong Giọng Local Review Phim Tiếng Việt (Sherpa-ONNX 64MB)! Chạy Offline 0đ siêu tốc.",
                    "status": status,
                }
            return {"success": False, "error": "Đã tải nhưng chưa thấy file model .onnx.", "status": status}
        except Exception as e:
            return {"success": False, "error": f"Lỗi cài đặt Local TTS: {e}"}

    def _get_sherpa_tts(self):
        if (
            LocalTTSClient._sherpa_instance is not None
            and LocalTTSClient._sherpa_model_dir_loaded == SHERPA_MODEL_DIR
        ):
            return LocalTTSClient._sherpa_instance

        import sherpa_onnx

        onnx_path = os.path.join(SHERPA_MODEL_DIR, "vi_VN-vais1000-medium.onnx")
        tokens_path = os.path.join(SHERPA_MODEL_DIR, "tokens.txt")
        data_dir = os.path.join(SHERPA_MODEL_DIR, "espeak-ng-data")
        if not os.path.exists(onnx_path):
            raise RuntimeError("Chưa tải bộ model Giọng Local Tiếng Việt.")

        tts_config = sherpa_onnx.OfflineTtsConfig(
            model=sherpa_onnx.OfflineTtsModelConfig(
                vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                    model=onnx_path,
                    lexicon="",
                    data_dir=data_dir,
                    tokens=tokens_path,
                ),
                provider="cpu",
                num_threads=max(1, min(8, self.threads)),
                debug=False,
            ),
            max_num_sentences=2,
        )
        LocalTTSClient._sherpa_instance = sherpa_onnx.OfflineTts(tts_config)
        LocalTTSClient._sherpa_model_dir_loaded = SHERPA_MODEL_DIR
        return LocalTTSClient._sherpa_instance

    def synthesize_segment_to_wav(self, text: str, out_wav: str, speed: Optional[float] = None) -> str:
        clean_text = (text or "").strip() or "."
        os.makedirs(os.path.dirname(os.path.abspath(out_wav)), exist_ok=True)

        if self.engine == "vieneu":
            from vieneu import Vieneu
            tts = Vieneu()
            kwargs = {"text": clean_text}
            if self.ref_wav and os.path.exists(self.ref_wav):
                kwargs["ref_audio"] = self.ref_wav
            audio = tts.infer(**kwargs)
            tts.save(audio, out_wav)
            return out_wav

        if self.engine == "custom_api" and self.custom_url:
            import requests
            r = requests.post(
                self.custom_url,
                json={"model": "local-tts", "input": clean_text, "voice": "vi_VN", "response_format": "wav"},
                timeout=60,
            )
            r.raise_for_status()
            with open(out_wav, "wb") as f:
                f.write(r.content)
            return out_wav

        preset_cfg = LOCAL_VOICE_PRESETS.get(self.preset_name, LOCAL_VOICE_PRESETS["rv_nu_kich_tinh"])

        # Gemini Native Emotional Review-Phim TTS (`gemini-3.8-flash-lite-tts` -> Charon / Kore)
        if preset_cfg.get("kind") == "gemini_tts":
            import base64
            import requests
            from .quota_pool import QuotaPoolManager
            from ..config import get_ffmpeg_exe

            providers = [p for p in QuotaPoolManager.get_all_providers() if p["kind"] == "gemini_native"]
            if providers:
                g_key = providers[0]["api_key"]
                v_name = preset_cfg.get("voice_name", "Charon")
                s_prompt = preset_cfg.get("style_prompt", "")
                tempo = preset_cfg.get("tempo", 1.15)
                for tts_model in ("gemini-3.8-flash-lite-tts", "gemini-2.5-flash-preview-tts"):
                    r = requests.post(
                        f"https://generativelanguage.googleapis.com/v1beta/models/{tts_model}:generateContent?key={g_key}",
                        json={
                            "contents": [{"parts": [{"text": f"{s_prompt}{clean_text}"}]}],
                            "generationConfig": {
                                "responseModalities": ["AUDIO"],
                                "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": v_name}}},
                            },
                        },
                        timeout=35,
                    )
                    if r.status_code == 200:
                        part = (((r.json().get("candidates") or [{}])[0].get("content") or {}).get("parts") or [{}])[0]
                        inline = part.get("inlineData") or {}
                        if inline.get("data"):
                            raw_bytes = base64.b64decode(inline["data"])
                            raw_in = out_wav + ".gem_in.wav"
                            if "pcm" in str(inline.get("mimeType", "")).lower():
                                with wave.open(raw_in, "wb") as wf:
                                    wf.setnchannels(1)
                                    wf.setsampwidth(2)
                                    wf.setframerate(24000)
                                    wf.writeframes(raw_bytes)
                            else:
                                with open(raw_in, "wb") as f:
                                    f.write(raw_bytes)
                            subprocess.run(
                                [get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", raw_in, "-af", f"atempo={tempo}", "-ac", "1", "-ar", str(self.SAMPLE_RATE), "-sample_fmt", "s16", out_wav],
                                check=True,
                                capture_output=True,
                            )
                            try:
                                os.remove(raw_in)
                            except Exception:
                                pass
                            return out_wav

        # Fallback / Sherpa VITS
        actual_speed = speed if speed is not None else preset_cfg.get("speed", 1.12)

        with _SHERPA_SYNTH_LOCK:
            tts = self._get_sherpa_tts()
            audio = tts.generate(clean_text, sid=0, speed=actual_speed)
        if len(audio.samples) == 0:
            raise RuntimeError("Sherpa-ONNX returned empty audio samples")

        raw_wav = out_wav + ".raw.wav"
        pcm16 = array.array("h", (max(-32767, min(32767, int(s * 32767.0))) for s in audio.samples))
        with wave.open(raw_wav, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(audio.sample_rate)
            wf.writeframes(pcm16.tobytes())

        # Apply Review Phim Broadcast Audio Mastering Chain via FFmpeg
        from ..config import get_ffmpeg_exe
        af_chain = preset_cfg.get("af_chain", "")
        cmd = [get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", raw_wav]
        if af_chain:
            cmd.extend(["-af", af_chain])
        cmd.extend(["-ac", "1", "-ar", str(self.SAMPLE_RATE), "-sample_fmt", "s16", out_wav])
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        finally:
            if os.path.exists(raw_wav):
                try:
                    os.remove(raw_wav)
                except Exception:
                    pass
        return out_wav

    def _wav_to_trimmed_pcm_samples(self, wav_path: str, target_slot_ms: int) -> array.array:
        from ..config import get_ffmpeg_exe
        ffmpeg_bin = get_ffmpeg_exe()
        tmp_wav = wav_path + ".norm.wav"
        tmp_fit_wav = wav_path + ".fit.wav"
        try:
            trim_filter = (
                "silenceremove=start_periods=1:start_silence=0.02:start_threshold=-42dB:"
                "stop_periods=-1:stop_silence=0.05:stop_threshold=-42dB"
            )
            subprocess.run(
                [
                    ffmpeg_bin, "-y", "-loglevel", "error",
                    "-i", wav_path,
                    "-af", trim_filter,
                    "-ac", "1", "-ar", str(self.SAMPLE_RATE), "-sample_fmt", "s16",
                    tmp_wav,
                ],
                check=True,
                capture_output=True,
            )
            with wave.open(tmp_wav, "rb") as wf:
                n_frames = wf.getnframes()
                raw_bytes = wf.readframes(n_frames)

            speech_ms = int((n_frames / self.SAMPLE_RATE) * 1000)
            if target_slot_ms > 400 and speech_ms > target_slot_ms * 1.03:
                tempo = min(1.45, max(1.05, speech_ms / float(target_slot_ms)))
                subprocess.run(
                    [
                        ffmpeg_bin, "-y", "-loglevel", "error",
                        "-i", tmp_wav,
                        "-af", f"atempo={tempo:.3f}",
                        "-ac", "1", "-ar", str(self.SAMPLE_RATE), "-sample_fmt", "s16",
                        tmp_fit_wav,
                    ],
                    check=True,
                    capture_output=True,
                )
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

    def process_full_dubbing(self, srt_path: str, output_audio_path: str) -> str:
        from ..config import get_ffmpeg_exe

        with open(srt_path, "r", encoding="utf-8") as f:
            blocks = parse_srt_blocks(f.read())

        work_dir = os.path.dirname(os.path.abspath(output_audio_path))
        seg_dir = os.path.join(work_dir, "_local_tts_segments")
        os.makedirs(seg_dir, exist_ok=True)

        if self.engine == "sherpa_onnx" and not self.check_installed_backends()["sherpa_ready"]:
            inst = self.install_sherpa_vietnamese()
            if not inst.get("success"):
                raise RuntimeError(inst.get("error", "Không thể tự cài Sherpa-ONNX"))

        if not blocks:
            tmp_w = os.path.join(seg_dir, "single.wav")
            self.synthesize_segment_to_wav("Video chia sẻ nội dung hấp dẫn.", tmp_w)
            subprocess.run(
                [get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", tmp_w, "-c:a", "libmp3lame", "-b:a", "192k", output_audio_path],
                check=True,
                capture_output=True,
            )
            return output_audio_path

        last_end_ms = max(b["end_ms"] for b in blocks) + 3000
        timeline = array.array("h", [0]) * int((last_end_ms / 1000.0) * self.SAMPLE_RATE)
        cursor_sample = 0

        for i, blk in enumerate(blocks):
            seg_wav = os.path.join(seg_dir, f"seg_{i:04d}.wav")
            self.synthesize_segment_to_wav(blk["text"], seg_wav)

            start_ms = blk["start_ms"]
            end_ms = blk["end_ms"]
            next_start_ms = blocks[i + 1]["start_ms"] if i + 1 < len(blocks) else (end_ms + 3000)
            max_window_ms = max(600, min(end_ms - start_ms + 400, next_start_ms - start_ms - 40))

            seg_samples = self._wav_to_trimmed_pcm_samples(seg_wav, target_slot_ms=max_window_ms)
            start_sample = max(cursor_sample, int((start_ms / 1000.0) * self.SAMPLE_RATE))
            end_sample = start_sample + len(seg_samples)
            if end_sample > len(timeline):
                timeline.extend([0] * (end_sample - len(timeline) + self.SAMPLE_RATE))

            timeline[start_sample:end_sample] = seg_samples
            cursor_sample = end_sample + int(0.03 * self.SAMPLE_RATE)

            blk["start_ms"] = int((start_sample / self.SAMPLE_RATE) * 1000)
            blk["end_ms"] = max(blk["start_ms"] + 500, min(int((end_sample / self.SAMPLE_RATE) * 1000) + 150, next_start_ms - 30))

        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(format_srt_blocks(blocks))

        master_wav = output_audio_path + ".local_master.wav"
        try:
            with wave.open(master_wav, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.SAMPLE_RATE)
                wf.writeframes(timeline.tobytes())

            subprocess.run(
                [get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", master_wav, "-c:a", "libmp3lame", "-b:a", "192k", output_audio_path],
                check=True,
                capture_output=True,
            )
        finally:
            if os.path.exists(master_wav):
                try:
                    os.remove(master_wav)
                except Exception:
                    pass

        return output_audio_path

    def test_connection(self) -> Dict[str, Any]:
        import time
        status = self.check_installed_backends()
        if self.engine == "sherpa_onnx" and not status["sherpa_ready"]:
            return {
                "success": False,
                "error": "Chưa tải bộ Giọng Local Tiếng Việt (64MB). Hãy bấm nút '⬇ Tự Động Cài Giọng Local (64MB)'!",
                "status": status,
            }
        tmp_wav = os.path.join(BASE_DIR, "temp", "_test_local_tts.wav")
        t0 = time.time()
        try:
            self.synthesize_segment_to_wav("Không ai ngờ gã ăn mày rách rưới trước cổng lại chính là vị chủ tịch quyền lực nhất thành phố.", tmp_wav)
            elapsed_ms = int((time.time() - t0) * 1000)
            return {
                "success": True,
                "message": f"Giọng Local ({self.preset_name}) hoạt động cực mượt! Tốc độ đọc câu Review Phim: {elapsed_ms}ms (Offline 100%, 0đ).",
                "status": status,
            }
        except Exception as e:
            return {"success": False, "error": f"Lỗi chạy thử Local TTS ({self.engine}): {e}", "status": status}
