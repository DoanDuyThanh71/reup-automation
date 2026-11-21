import os
import shutil
import subprocess
from typing import Dict, Any
from ..config import get_ffmpeg_exe

class RenderAgent:
    """
    Agent 5: Merges dubbed audio and burns stylized Vietnamese subtitles into video.
    Uses relative subtitle filename inside working directory to prevent Windows drive-letter,
    whitespace, and Unicode path escaping failures in FFmpeg libass.
    """
    def escape_ffmpeg_path(self, path: str) -> str:
        """Escapes Windows and Linux file paths for FFmpeg filter_complex."""
        clean = path.replace("\\", "/")
        clean = clean.replace(":", "\\:")
        clean = clean.replace("'", "'\\''")
        return clean

    def run(self, input_video_path: str, dubbed_audio_path: str, srt_path: str, output_video_path: str) -> Dict[str, Any]:
        abs_in_video = os.path.abspath(input_video_path)
        abs_dub_audio = os.path.abspath(dubbed_audio_path)
        abs_srt = os.path.abspath(srt_path)
        abs_out_video = os.path.abspath(output_video_path)

        work_dir = os.path.dirname(abs_out_video)
        os.makedirs(work_dir, exist_ok=True)

        # Ensure a clean ASCII filename for SRT inside work_dir so libass never fails on Unicode/colons
        local_srt_name = "_burn_sub.srt"
        local_srt_path = os.path.join(work_dir, local_srt_name)
        if os.path.exists(abs_srt) and os.path.abspath(abs_srt) != os.path.abspath(local_srt_path):
            shutil.copyfile(abs_srt, local_srt_path)
        elif not os.path.exists(local_srt_path):
            local_srt_name = os.path.basename(abs_srt)

        ffmpeg_bin = get_ffmpeg_exe()

        # High-visibility subtitle styling (Yellow bold text with black outline)
        style = (
            "FontSize=16,"
            "FontName=Arial,"
            "Bold=1,"
            "PrimaryColour=&H0000FFFF&,"   # Bright Yellow in BGR hex
            "OutlineColour=&H00000000&,"   # Black Outline
            "BorderStyle=1,"
            "Outline=2.5,"
            "Shadow=1,"
            "Alignment=2,"                 # Bottom Center
            "MarginV=35"
        )

        filter_str = (
            f"[0:v]subtitles='{local_srt_name}':force_style='{style}'[v];"
            f"[0:a]volume=0.25[a_orig];"
            f"[1:a]volume=1.2[a_dub];"
            f"[a_orig][a_dub]amix=inputs=2:duration=first:dropout_transition=2[a]"
        )

        cmd = [
            ffmpeg_bin, "-y",
            "-i", abs_in_video,
            "-i", abs_dub_audio,
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
                "file_size": os.path.getsize(abs_out_video)
            }
        except subprocess.CalledProcessError as e:
            err = e.stderr.decode("utf-8", errors="ignore") if e.stderr else str(e)
            print(f"[RenderAgent] Subtitle burn failed: {err}. Falling back to audio replacement only...")
            fallback_cmd = [
                ffmpeg_bin, "-y",
                "-i", abs_in_video,
                "-i", abs_dub_audio,
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
                "warning": "Đã render video không burn sub do thiếu thư viện libass trên FFmpeg."
            }
