import os
import requests
from typing import Dict, Any, Optional

class FacebookPublisher:
    """
    Client for publishing Videos & Reels to Facebook Pages using Facebook Graph API.
    """
    GRAPH_API_VERSION = "v19.0"
    GRAPH_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"
    VIDEO_GRAPH_URL = f"https://graph-video.facebook.com/{GRAPH_API_VERSION}"

    def __init__(self, page_id: Optional[str] = None, page_access_token: Optional[str] = None):
        self.page_id = page_id
        self.page_access_token = page_access_token

    def test_connection(self, page_id: Optional[str] = None, token: Optional[str] = None) -> Dict[str, Any]:
        """Tests Facebook Page token validity and returns page details."""
        p_id = page_id or self.page_id
        p_token = token or self.page_access_token

        if not p_id or not p_token:
            return {"success": False, "error": "Thiếu Facebook Page ID hoặc Page Access Token"}

        url = f"{self.GRAPH_URL}/{p_id}"
        params = {
            "fields": "id,name,category,link,picture",
            "access_token": p_token
        }

        try:
            res = requests.get(url, params=params, timeout=15)
            data = res.json()
            if res.status_code == 200 and "id" in data:
                return {
                    "success": True,
                    "page_id": data.get("id"),
                    "page_name": data.get("name"),
                    "category": data.get("category"),
                    "link": data.get("link")
                }
            error_msg = data.get("error", {}).get("message", res.text)
            return {"success": False, "error": f"Lỗi Facebook API: {error_msg}"}
        except Exception as e:
            return {"success": False, "error": f"Lỗi kết nối Facebook: {str(e)}"}

    def publish_video(self, video_path: str, title: str, description: str, page_id: Optional[str] = None, token: Optional[str] = None) -> Dict[str, Any]:
        """
        Uploads and publishes a regular video to the Facebook Page feed.
        Endpoint: POST https://graph-video.facebook.com/v19.0/{page-id}/videos
        """
        p_id = page_id or self.page_id
        p_token = token or self.page_access_token

        if not os.path.exists(video_path):
            return {"success": False, "error": f"Không tìm thấy file video: {video_path}"}
        if not p_id or not p_token:
            return {"success": False, "error": "Thiếu Facebook Page ID hoặc Page Access Token"}

        url = f"{self.VIDEO_GRAPH_URL}/{p_id}/videos"
        data = {
            "title": title[:255] if title else "Video",
            "description": description,
            "access_token": p_token,
            "published": "true"
        }

        try:
            with open(video_path, "rb") as f:
                files = {"source": (os.path.basename(video_path), f, "video/mp4")}
                res = requests.post(url, data=data, files=files, timeout=300)
                res_data = res.json()

                if res.status_code == 200 and "id" in res_data:
                    return {
                        "success": True,
                        "post_id": res_data.get("id"),
                        "message": "Đã đăng video lên Facebook Page thành công"
                    }
                err_msg = res_data.get("error", {}).get("message", res.text)
                return {"success": False, "error": f"Lỗi đăng video Facebook: {err_msg}"}
        except Exception as e:
            return {"success": False, "error": f"Lỗi upload video Facebook: {str(e)}"}

    def publish_reel(self, video_path: str, description: str, page_id: Optional[str] = None, token: Optional[str] = None) -> Dict[str, Any]:
        """
        Publishes video as a Facebook Reel using the 3-step Reels Publishing API.
        Step 1: Initialize session (upload_phase=start)
        Step 2: Upload binary data to upload_url
        Step 3: Finish and publish (upload_phase=finish)
        """
        p_id = page_id or self.page_id
        p_token = token or self.page_access_token

        if not os.path.exists(video_path):
            return {"success": False, "error": f"Không tìm thấy file video: {video_path}"}
        if not p_id or not p_token:
            return {"success": False, "error": "Thiếu Facebook Page ID hoặc Page Access Token"}

        file_size = os.path.getsize(video_path)

        # Step 1: Initialize Reels Session
        init_url = f"{self.GRAPH_URL}/{p_id}/video_reels"
        init_payload = {
            "upload_phase": "start",
            "access_token": p_token
        }

        try:
            init_res = requests.post(init_url, data=init_payload, timeout=20)
            init_data = init_res.json()
            if init_res.status_code != 200 or "video_id" not in init_data:
                err = init_data.get("error", {}).get("message", init_res.text)
                # Fallback to normal video upload if Page is not eligible for Reels API
                print(f"[FacebookPublisher] Reels start failed ({err}). Falling back to regular video upload...")
                return self.publish_video(video_path, title=description[:100], description=description, page_id=p_id, token=p_token)

            video_id = init_data["video_id"]
            upload_url = init_data.get("upload_url")

            # Step 2: Upload Video Binary
            headers = {
                "Authorization": f"OAuth {p_token}",
                "offset": "0",
                "file_size": str(file_size)
            }
            with open(video_path, "rb") as f:
                upload_res = requests.post(upload_url, data=f, headers=headers, timeout=300)
                if upload_res.status_code not in (200, 201):
                    return {"success": False, "error": f"Lỗi upload binary Reels: {upload_res.text}"}

            # Step 3: Finish & Publish Reel
            finish_payload = {
                "upload_phase": "finish",
                "access_token": p_token,
                "video_id": video_id,
                "video_state": "PUBLISHED",
                "description": description
            }
            finish_res = requests.post(init_url, data=finish_payload, timeout=30)
            finish_data = finish_res.json()

            if finish_res.status_code == 200 and finish_data.get("success", False):
                return {
                    "success": True,
                    "post_id": video_id,
                    "message": "Đã xuất bản Facebook Reel thành công!"
                }
            err = finish_data.get("error", {}).get("message", finish_res.text)
            return {"success": False, "error": f"Lỗi finish Reel: {err}"}
        except Exception as e:
            return {"success": False, "error": f"Lỗi ngoại lệ khi đăng Facebook Reel: {str(e)}"}
