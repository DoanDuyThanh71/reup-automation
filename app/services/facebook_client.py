import os
import re
import requests
from typing import Dict, Any, Optional, List
from .security_fingerprint import SecurityFingerprintManager


class FacebookPublisher:
    """
    Client for publishing Videos & Reels to Facebook Pages, posting first-comment Affiliate links,
    and pulling real-time Page & Reel/Video analytics using Facebook Graph API.
    """
    GRAPH_API_VERSION = "v21.0"
    GRAPH_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"
    VIDEO_GRAPH_URL = f"https://graph-video.facebook.com/{GRAPH_API_VERSION}"

    def __init__(self, page_id: Optional[str] = None, page_access_token: Optional[str] = None):
        self.page_id = self.sanitize_page_id(page_id) if page_id else page_id
        self.page_access_token = (page_access_token or "").strip() or None

    @staticmethod
    def sanitize_page_id(raw_id: Optional[str]) -> str:
        """Extracts numeric Page ID even if pasted from Graph Explorer markdown `[105836...](https://...)`."""
        if not raw_id:
            return ""
        text = str(raw_id).strip()
        m = re.search(r"\b(\d{8,24})\b", text)
        return m.group(1) if m else text

    def test_connection(self, page_id: Optional[str] = None, token: Optional[str] = None) -> Dict[str, Any]:
        """Tests Facebook Page token validity and returns page details."""
        p_id = self.sanitize_page_id(page_id or self.page_id)
        p_token = (token or self.page_access_token or "").strip()

        if not p_id or not p_token:
            return {"success": False, "error": "Thiếu Facebook Page ID hoặc Page Access Token"}

        url = f"{self.GRAPH_URL}/{p_id}"
        params = {
            "fields": "id,name,category,followers_count,fan_count,link,picture",
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
                    "followers_count": data.get("followers_count", 0),
                    "fan_count": data.get("fan_count", 0),
                    "link": data.get("link"),
                    "token_fingerprint": SecurityFingerprintManager.secret_fingerprint(p_token),
                }
            error_msg = data.get("error", {}).get("message", res.text)
            return {"success": False, "error": f"Lỗi Facebook API: {error_msg}"}
        except Exception as e:
            return {"success": False, "error": f"Lỗi kết nối Facebook: {str(e)}"}

    def post_comment(self, object_id: str, message: str, token: Optional[str] = None) -> Optional[str]:
        """Posts a comment (e.g., Shopee Affiliate link) under a published Video/Reel."""
        p_token = (token or self.page_access_token or "").strip()
        if not object_id or not message or not p_token:
            return None
        try:
            res = requests.post(
                f"{self.GRAPH_URL}/{object_id}/comments",
                data={"message": message, "access_token": p_token},
                timeout=15,
            )
            if res.status_code == 200:
                return res.json().get("id")
        except Exception as e:
            print(f"[FacebookPublisher] Comment note: {e}")
        return None

    def publish_video(
        self,
        video_path: str,
        title: str,
        description: str,
        page_id: Optional[str] = None,
        token: Optional[str] = None,
        affiliate_comment: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Uploads and publishes a regular video to the Facebook Page feed."""
        p_id = self.sanitize_page_id(page_id or self.page_id)
        p_token = (token or self.page_access_token or "").strip()

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
                    vid_id = res_data.get("id")
                    comment_id = self.post_comment(vid_id, affiliate_comment, token=p_token) if affiliate_comment else None
                    return {
                        "success": True,
                        "post_id": vid_id,
                        "comment_id": comment_id,
                        "permalink": f"https://www.facebook.com/{vid_id}",
                        "message": "Đã đăng video lên Facebook Page thành công"
                    }
                err_msg = res_data.get("error", {}).get("message", res.text)
                return {"success": False, "error": f"Lỗi đăng video Facebook: {err_msg}"}
        except Exception as e:
            return {"success": False, "error": f"Lỗi upload video Facebook: {str(e)}"}

    def publish_reel(
        self,
        video_path: str,
        description: str,
        page_id: Optional[str] = None,
        token: Optional[str] = None,
        affiliate_comment: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Publishes video as a Facebook Reel using the 3-step Reels Publishing API.
        """
        p_id = self.sanitize_page_id(page_id or self.page_id)
        p_token = (token or self.page_access_token or "").strip()

        if not os.path.exists(video_path):
            return {"success": False, "error": f"Không tìm thấy file video: {video_path}"}
        if not p_id or not p_token:
            return {"success": False, "error": "Thiếu Facebook Page ID hoặc Page Access Token"}

        file_size = os.path.getsize(video_path)
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
                print(f"[FacebookPublisher] Reels start failed ({err}). Falling back to regular video upload...")
                return self.publish_video(
                    video_path,
                    title=description[:100],
                    description=description,
                    page_id=p_id,
                    token=p_token,
                    affiliate_comment=affiliate_comment,
                )

            video_id = init_data["video_id"]
            upload_url = init_data.get("upload_url")

            headers = {
                "Authorization": f"OAuth {p_token}",
                "offset": "0",
                "file_size": str(file_size)
            }
            with open(video_path, "rb") as f:
                upload_res = requests.post(upload_url, data=f, headers=headers, timeout=300)
                if upload_res.status_code not in (200, 201):
                    return {"success": False, "error": f"Lỗi upload binary Reels: {upload_res.text}"}

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
                comment_id = self.post_comment(video_id, affiliate_comment, token=p_token) if affiliate_comment else None
                return {
                    "success": True,
                    "post_id": video_id,
                    "comment_id": comment_id,
                    "permalink": f"https://www.facebook.com/reel/{video_id}",
                    "message": "Đã xuất bản Facebook Reel thành công!"
                }
            err = finish_data.get("error", {}).get("message", finish_res.text)
            return {"success": False, "error": f"Lỗi finish Reel: {err}"}
        except Exception as e:
            return {"success": False, "error": f"Lỗi ngoại lệ khi đăng Facebook Reel: {str(e)}"}

    def fetch_page_analytics(self, limit: int = 10) -> Dict[str, Any]:
        """Fetches live Fanpage followers and recent Reels/Videos metrics (views, likes, comments)."""
        p_id = self.sanitize_page_id(self.page_id)
        p_token = (self.page_access_token or "").strip()
        if not p_id or not p_token:
            return {"connected": False, "error": "Chưa cấu hình Facebook Page"}

        page_info = self.test_connection(page_id=p_id, token=p_token)
        if not page_info.get("success"):
            return {"connected": False, "error": page_info.get("error")}

        videos_out: List[Dict[str, Any]] = []
        total_views = 0
        total_likes = 0
        total_comments = 0
        try:
            r = requests.get(
                f"{self.GRAPH_URL}/{p_id}/videos",
                params={
                    "fields": "id,title,description,views,length,created_time,permalink_url,likes.summary(true),comments.summary(true)",
                    "limit": limit,
                    "access_token": p_token,
                },
                timeout=15,
            )
            if r.status_code == 200:
                for item in r.json().get("data", []):
                    vw = int(item.get("views") or 0)
                    lk = int(((item.get("likes") or {}).get("summary") or {}).get("total_count") or 0)
                    cm = int(((item.get("comments") or {}).get("summary") or {}).get("total_count") or 0)
                    total_views += vw
                    total_likes += lk
                    total_comments += cm
                    perm = item.get("permalink_url") or ""
                    if perm and perm.startswith("/"):
                        perm = f"https://www.facebook.com{perm}"
                    videos_out.append({
                        "id": item.get("id"),
                        "title": (item.get("title") or (item.get("description") or "")[:70]).strip() or f"Video #{item.get('id')}",
                        "views": vw,
                        "likes": lk,
                        "comments": cm,
                        "length": item.get("length"),
                        "created_time": item.get("created_time"),
                        "permalink_url": perm or f"https://www.facebook.com/{item.get('id')}",
                    })
        except Exception as e:
            print(f"[FacebookPublisher] fetch_page_analytics warning: {e}")

        return {
            "connected": True,
            "page_id": page_info.get("page_id"),
            "page_name": page_info.get("page_name"),
            "followers_count": page_info.get("followers_count", 0),
            "fan_count": page_info.get("fan_count", 0),
            "link": page_info.get("link"),
            "token_fingerprint": page_info.get("token_fingerprint"),
            "total_views": total_views,
            "total_likes": total_likes,
            "total_comments": total_comments,
            "videos": videos_out,
        }
