import os
import subprocess
from typing import Dict, Any

class RenderAgent:
    """
    Agent 5: Merges dubbed audio and burns stylized Vietnamese subtitles into video.
    """
    def escape_ffmpeg_path(self, path: str) -> str:
        """Escapes Windows and Linux file paths for FFmpeg filter_complex."""
        clean = path.replace("\\", "/")
        clean = clean.replace(":", "\\:")
        clean = clean.replace("'", "'\\''")
        return clean

    def run(self, input_video_path: str, dubbed_audio_path: str, srt_path: str, output_video_path: str) -> Dict[str, Any]:
        os.makedirs(os.path.dirname(output_video_path), exist_ok=True)
        escaped_srt = self.escape_ffmpeg_path(srt_path)

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

        filter_str = f"[0:v]subtitles='{escaped_srt}':force_style='{style}'[v]"

        cmd = [
            "ffmpeg", "-y",
            "-i", input_video_path,
            "-i", dubbed_audio_path,
            "-filter_complex", filter_str,
            "-map", "[v]",
            "-map", "1:a",
            "-c:v", "libx264",
            "-preset", "faster",
            "-crf", "22",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            output_video_path
        ]

        try:
            res = subprocess.run(cmd, check=True, capture_output=True)
            if not os.path.exists(output_video_path) or os.path.getsize(output_video_path) == 0:
                raise RuntimeError("File video đầu ra rỗng sau khi render.")
            return {
                "success": True,
                "output_video_path": output_video_path,
                "file_size": os.path.getsize(output_video_path)
            }
        except subprocess.CalledProcessError as e:
            err = e.stderr.decode("utf-8", errors="ignore")
            # If font/subtitles filter failed on stripped environment, fallback to audio-only replacement
            print(f"[RenderAgent] Subtitle burn failed: {err}. Falling back to audio replacement only...")
            fallback_cmd = [
                "ffmpeg", "-y",
                "-i", input_video_path,
                "-i", dubbed_audio_path,
                "-c:v", "copy",
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-shortest",
                output_video_path
            ]
            subprocess.run(fallback_cmd, check=True, capture_output=True)
            return {
                "success": True,
                "output_video_path": output_video_path,
                "file_size": os.path.getsize(output_video_path),
                "warning": "Đã render video không burn sub do lỗi thư viện font FFmpeg."
            }
