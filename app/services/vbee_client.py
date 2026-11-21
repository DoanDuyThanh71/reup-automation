import os
import time
import requests
from typing import Dict, Any, Optional

VOICE_MAP = {
    "vi_female_hn_ngoc_huyen": "hn_female_ngochuyen_full_48k-fhg",
    "vi_male_hn_nam_mien_bac": "hn_male_manhdung_full_24k-st",
    "vi_female_sg_lan_nhi": "sg_female_thaotrinh_full_44k-phg"
}

class VbeeClient:
    """
    Vbee AI Voice Dubbing client using Vbee Studio API.
    Uploads SRT to Vbee and receives synchronized Vietnamese dubbed audio.
    """
    def __init__(self, refresh_token_cookie: Optional[str] = None):
        from ..config import config
        self.refresh_token_cookie = refresh_token_cookie or config.get("VBEE_REFRESH_TOKEN_COOKIE", "")
        self.access_token = None
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://studio.vbee.vn",
            "Referer": "https://studio.vbee.vn/"
        })

    def refresh_access_token(self) -> str:
        cookie = self.refresh_token_cookie.strip()
        if not cookie:
            raise ValueError("Chưa cấu hình VBEE_REFRESH_TOKEN_COOKIE!")

        url = "https://accounts.vbee.vn/api/v1/auth/refresh-token"
        headers = {
            "Cookie": cookie,
            "Content-Type": "application/json"
        }
        body = {"clientId": "aivoice-web-application"}

        res = self.session.post(url, json=body, headers=headers, timeout=15)
        res.raise_for_status()
        data = res.json()

        token = data.get("result", {}).get("access_token") or data.get("access_token")
        if token:
            self.access_token = token
            self.session.headers["Authorization"] = f"Bearer {token}"
            return token
        raise RuntimeError(f"Không thể lấy Vbee access token: {data}")

    def test_connection(self) -> Dict[str, Any]:
        try:
            token = self.refresh_access_token()
            return {"success": True, "message": "Xác thực Vbee thành công!", "token_preview": token[:15] + "..."}
        except Exception as e:
            return {"success": False, "error": f"Lỗi xác thực Vbee: {str(e)}"}

    def get_presigned_url(self, filename: str = "subtitle.srt") -> Dict[str, Any]:
        url = "https://vbee.vn/api/v1/files/presigned-url-for-uploading"
        params = {
            "fileName": filename,
            "extension": "srt",
            "directory": "dubbing"
        }
        res = self.session.get(url, params=params, timeout=15)
        res.raise_for_status()
        return res.json().get("result", {})

    def upload_srt_to_vbee(self, srt_file_path: str) -> str:
        presigned_info = self.get_presigned_url(os.path.basename(srt_file_path))
        upload_url = presigned_info.get("url") or presigned_info.get("presigned_url")
        if not upload_url:
            raise RuntimeError("Không lấy được presigned URL từ Vbee")

        with open(srt_file_path, "rb") as f:
            headers = {"Content-Type": "text/plain"}
            res = requests.put(upload_url, data=f, headers=headers, timeout=60)
            res.raise_for_status()

        return upload_url.split("?")[0]

    def create_dubbing_task(self, srt_url: str, voice_code: str = "hn_female_ngochuyen_full_48k-fhg", speed: float = 1.0) -> str:
        actual_voice = VOICE_MAP.get(voice_code, voice_code)
        url = "https://vbee.vn/api/v1/dubbing"
        payload = {
            "title": f"Auto Dubbing {int(time.time())}",
            "subtitleLink": srt_url,
            "voiceCode": actual_voice,
            "speed": speed,
            "audioType": "mp3"
        }
        res = self.session.post(url, json=payload, timeout=15)
        res.raise_for_status()
        data = res.json()
        if data.get("status") == 0 or data.get("error_code"):
            raise RuntimeError(f"Vbee Dubbing Error: {data.get('error_message')}")

        result_data = data.get("result", {})
        return result_data.get("id") or result_data.get("request_id") or result_data.get("_id")

    def poll_dubbing_result(self, request_id: str, max_retries: int = 40, delay: int = 4) -> str:
        url = f"https://vbee.vn/api/v1/dubbing/{request_id}"
        for _ in range(max_retries):
            res = self.session.get(url, timeout=15)
            if res.status_code == 200:
                data = res.json().get("result", {})
                status = data.get("status")
                if status in ("COMPLETED", "SUCCESS", "DONE") and data.get("audio_link"):
                    return data.get("audio_link")
                if status in ("FAILED", "ERROR"):
                    raise RuntimeError(f"Vbee xử lý lồng tiếng thất bại: {data.get('error_message')}")
            time.sleep(delay)
        raise TimeoutError("Hết thời gian chờ Vbee xử lý lồng tiếng.")

    def process_full_dubbing(self, srt_path: str, output_audio_path: str, voice_code: str = "vi_female_hn_ngoc_huyen") -> str:
        """Runs the entire Vbee pipeline: refresh token -> upload srt -> request dub -> download mp3."""
        self.refresh_access_token()
        srt_s3_url = self.upload_srt_to_vbee(srt_path)
        task_id = self.create_dubbing_task(srt_s3_url, voice_code=voice_code)
        audio_url = self.poll_dubbing_result(task_id)

        # Download result audio
        res = requests.get(audio_url, timeout=60)
        res.raise_for_status()
        with open(output_audio_path, "wb") as f:
            f.write(res.content)

        return output_audio_path
