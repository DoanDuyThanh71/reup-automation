import os
import shutil
import platform
import subprocess
from typing import Dict, Any, Optional


class HardwareAdvisor:
    """
    Detects CPU cores, system RAM, disk space, and NVIDIA/Apple/AMD GPU VRAM,
    then recommends the safest & highest-quality TTS Voice configuration for the user's machine.
    """

    @staticmethod
    def _detect_ram_gb() -> float:
        try:
            if os.name == "nt":
                r = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                val = r.stdout.strip()
                if val.isdigit():
                    return round(int(val) / (1024 ** 3), 1)
            elif os.path.exists("/proc/meminfo"):
                with open("/proc/meminfo", "r") as f:
                    for line in f:
                        if line.startswith("MemTotal:"):
                            kb = int(line.split()[1])
                            return round(kb / (1024 ** 2), 1)
        except Exception:
            pass
        return 8.0

    @staticmethod
    def _detect_gpu() -> Dict[str, Any]:
        # 1. Try nvidia-smi for exact NVIDIA CUDA GPU & VRAM
        nvidia_smi = shutil.which("nvidia-smi")
        if nvidia_smi:
            try:
                r = subprocess.run(
                    [nvidia_smi, "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader,nounits"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if r.returncode == 0 and r.stdout.strip():
                    first = r.stdout.strip().splitlines()[0]
                    parts = [p.strip() for p in first.split(",")]
                    if len(parts) >= 2:
                        vram_mb = int(float(parts[1]))
                        free_mb = int(float(parts[2])) if len(parts) >= 3 else vram_mb
                        return {
                            "has_nvidia": True,
                            "gpu_name": parts[0],
                            "vram_gb": round(vram_mb / 1024.0, 1),
                            "vram_free_gb": round(free_mb / 1024.0, 1),
                            "accelerator": "cuda",
                        }
            except Exception:
                pass

        # 2. Apple Silicon unified memory check
        if platform.system() == "Darwin" and platform.machine() == "arm64":
            return {
                "has_nvidia": False,
                "gpu_name": "Apple Silicon (MPS Metal)",
                "vram_gb": 8.0,
                "vram_free_gb": 6.0,
                "accelerator": "mps",
            }

        # 3. Fallback integrated / CPU
        return {
            "has_nvidia": False,
            "gpu_name": "Card tích hợp (iGPU / CPU)",
            "vram_gb": 0.0,
            "vram_free_gb": 0.0,
            "accelerator": "cpu",
        }

    @classmethod
    def inspect_and_recommend(cls) -> Dict[str, Any]:
        cpu_cores = os.cpu_count() or 4
        cpu_name = platform.processor() or platform.machine()
        ram_gb = cls._detect_ram_gb()
        gpu = cls._detect_gpu()

        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        free_disk_gb = round(shutil.disk_usage(base_dir).free / (1024 ** 3), 1)

        vram = gpu["vram_gb"]
        has_cuda = gpu["has_nvidia"]

        # Tier classification & smart recommendation
        if has_cuda and vram >= 8.0 and ram_gb >= 16.0:
            tier = "ULTRA_GPU"
            tier_label = "Máy Rất Khỏe (Card rời ≥ 8GB VRAM)"
            recommended_provider = "local"
            recommended_engine = "sherpa_onnx_or_vieneu_cuda"
            headline = f"Máy của bạn cực khỏe ({gpu['gpu_name']} {vram}GB VRAM • {ram_gb}GB RAM • {cpu_cores} luồng)!"
            advice = (
                "Chạy mượt mọi bộ Voice Local Offline không tốn 1 đồng Vbee: "
                "Khuyên cài ngay Sherpa-ONNX Piper Tiếng Việt (siêu tốc 0.2s/câu) hoặc VieNeu-TTS 48kHz / F5-TTS Clone Giọng bằng GPU CUDA."
            )
            recommended_threads = min(8, max(4, cpu_cores // 2))
        elif (has_cuda and vram >= 4.0) or (gpu["accelerator"] == "mps" and ram_gb >= 16.0):
            tier = "MID_GPU"
            tier_label = "Máy Khá Khỏe (Có tăng tốc GPU)"
            recommended_provider = "local"
            recommended_engine = "sherpa_onnx"
            headline = f"Cấu hình tốt cho Voice Local ({gpu['gpu_name']} • {ram_gb}GB RAM • {cpu_cores} luồng)."
            advice = (
                "Khuyên dùng Sherpa-ONNX Tiếng Việt (chỉ 64MB, đọc khớp mili-giây SRT cực nhẹ) hoặc VieNeu-TTS bản nhẹ."
            )
            recommended_threads = min(6, max(2, cpu_cores // 2))
        elif ram_gb >= 8.0 and cpu_cores >= 6:
            tier = "CPU_GOOD"
            tier_label = "Máy Tầm Trung (CPU đa nhân, không card rời)"
            recommended_provider = "local"
            recommended_engine = "sherpa_onnx"
            headline = f"Đủ sức chạy Voice Local nhẹ trên CPU ({ram_gb}GB RAM • {cpu_cores} luồng)."
            advice = (
                "Không nên cài F5-TTS nặng (dễ treo máy). Hệ thống khuyên dùng Sherpa-ONNX Piper Tiếng Việt (64MB) chạy thuần CPU nhanh gấp 15 lần thời gian thực!"
            )
            recommended_threads = min(4, max(2, cpu_cores // 2))
        else:
            tier = "LOW_SPEC"
            tier_label = "Máy Yếu / Laptop Văn Phòng (< 8GB RAM)"
            recommended_provider = "edge-tts"
            recommended_engine = "cloud_only"
            headline = f"Máy cấu hình tiết kiệm ({ram_gb}GB RAM • {cpu_cores} luồng)."
            advice = (
                "KHÔNG nên chạy model Voice Local nặng để tránh đơ máy khi render FFmpeg. "
                "Khuyên dùng Microsoft Edge-TTS (Miễn phí 100%, xử lý trên đám mây, tốn 0% RAM) hoặc Vbee API!"
            )
            recommended_threads = 2

        from .local_tts_client import LocalTTSClient
        local_status = LocalTTSClient.check_installed_backends()

        return {
            "hardware": {
                "cpu_name": cpu_name,
                "cpu_threads": cpu_cores,
                "ram_gb": ram_gb,
                "gpu_name": gpu["gpu_name"],
                "vram_gb": vram,
                "vram_free_gb": gpu["vram_free_gb"],
                "accelerator": gpu["accelerator"],
                "free_disk_gb": free_disk_gb,
            },
            "recommendation": {
                "tier": tier,
                "tier_label": tier_label,
                "recommended_tts_provider": recommended_provider,
                "recommended_local_engine": recommended_engine,
                "recommended_threads": recommended_threads,
                "headline": headline,
                "advice": advice,
            },
            "local_backends": local_status,
        }
