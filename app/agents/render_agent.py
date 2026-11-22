import os
import shutil
import hashlib
import subprocess
from typing import Dict, Any
from ..config import get_ffmpeg_exe, config
from ..services.security_fingerprint import SecurityFingerprintManager


class RenderAgent:
    """
    Agent 5: Merges dubbed audio, burns stylized Vietnamese subtitles, and applies
    imperceptible Anti-Duplicate Video Fingerprinting (metadata stripping, unique UUID,
    micro-crop/color transform) so every exported MP4 has a clean, unique signature.
    """
    def escape_ffmpeg_path(self, path: str) -> str:
        clean = path.replace("\\", "/")
        clean = clean.replace(":", "\\:")
        clean = clean.replace("'", "'\\''")
        return clean

    @staticmethod
    def _file_sha256_short(path: str) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(262144), b""):
                h.update(chunk)
        return f"vfp:{h.hexdigest()[:12]}"

    def run(self, input_video_path: str, dubbed_audio_path: str, srt_path: str, output_video_path: str) -> Dict[str, Any]:
        abs_in_video = os.path.abspath(input_video_path)
        abs_dub_audio = os.path.abspath(dubbed_audio_path)
        abs_srt = os.path.abspath(srt_path)
        abs_out_video = os.path.abspath(output_video_path)

        work_dir = os.path.dirname(abs_out_video)
        os.makedirs(work_dir, exist_ok=True)

        local_srt_name = "_burn_sub.srt"
        local_srt_path = os.path.join(work_dir, local_srt_name)
        if os.path.exists(abs_srt) and os.path.abspath(abs_srt) != os.path.abspath(local_srt_path):
            shutil.copyfile(abs_srt, local_srt_path)
        elif not os.path.exists(local_srt_path):
            local_srt_name = os.path.basename(abs_srt)

        ffmpeg_bin = get_ffmpeg_exe()
        use_fp = config.get_bool("VIDEO_FINGERPRINT_PROTECTION", True)
        fp_params = SecurityFingerprintManager.get_video_anti_detect_params(os.path.basename(abs_out_video))

        style = (
            "FontSize=16,"
            "FontName=Arial,"
            "Bold=1,"
            "PrimaryColour=&H0000FFFF&,"
            "OutlineColour=&H00000000&,"
            "BorderStyle=1,"
            "Outline=2.5,"
            "Shadow=1,"
            "Alignment=2,"
            "MarginV=35"
        )

        v_chain = (
            f"{fp_params['vf_snippet']},subtitles='{local_srt_name}':force_style='{style}'"
            if use_fp
            else f"subtitles='{local_srt_name}':force_style='{style}'"
        )

        filter_str = (
            f"[0:v]{v_chain}[v];"
            f"[0:a]volume=0.12[a_orig];"
            f"[1:a]volume=1.35[a_dub];"
            f"[a_orig][a_dub]amix=inputs=2:duration=first:dropout_transition=2[a]"
        )

        cmd = [
            ffmpeg_bin, "-y",
            "-i", abs_in_video,
            "-i", abs_dub_audio,
            "-map_metadata", "-1",
            "-metadata", f"comment=media_id:{fp_params['media_uuid']}",
            "-filter_complex", filter_str,
            "-map", "[v]",
            "-map", "[a]",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "24",
            "-c:a", "aac",
            "-b:a", "192k",
            abs_out_video
        ]

        try:
            subprocess.run(cmd, cwd=work_dir, check=True, capture_output=True)
            if not os.path.exists(abs_out_video) or os.path.getsize(abs_out_video) == 0:
                raise RuntimeError("File video đầu ra rỗng sau khi render.")
            return {
                "success": True,
                "output_video_path": abs_out_video,
                "file_size": os.path.getsize(abs_out_video),
                "video_fingerprint": self._file_sha256_short(abs_out_video),
                "media_uuid": fp_params["media_uuid"],
            }
        except subprocess.CalledProcessError as e:
            err = e.stderr.decode("utf-8", errors="ignore") if e.stderr else str(e)
            print(f"[RenderAgent] Subtitle burn failed: {err}. Falling back to audio replacement only...")
            fallback_cmd = [
                ffmpeg_bin, "-y",
                "-i", abs_in_video,
                "-i", abs_dub_audio,
                "-map_metadata", "-1",
                "-metadata", f"comment=media_id:{fp_params['media_uuid']}",
                "-c:v", "copy",
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-shortest",
                abs_out_video
            ]
            subprocess.run(fallback_cmd, cwd=work_dir, check=True, capture_output=True)
            return {
                "success": True,
                "output_video_path": abs_out_video,
                "file_size": os.path.getsize(abs_out_video),
                "video_fingerprint": self._file_sha256_short(abs_out_video),
                "warning": "Đã render video không burn sub do thiếu thư viện libass trên FFmpeg."
            }
