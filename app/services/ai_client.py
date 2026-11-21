import os
import json
import re
import requests
from typing import Dict, Any, Optional

# Standard policy safety word mappings for TikTok and Facebook Reels
POLICY_SAFE_WORDS = [
    (r"\b(chết|tử vong)\b", "đăng xuất"),
    (r"\b(giết|đánh nhau|đánh đập|chém)\b", "tác động vật lý"),
    (r"\b(tự tử|tự sát)\b", "nghĩ quẩn"),
    (r"\b(máu me|đổ máu)\b", "si-rô đỏ"),
    (r"\b(ma túy|thuốc phiện|cần sa)\b", "chất cấm"),
    (r"\b(súng đạn|vũ khí)\b", "đồ chơi nguy hiểm"),
    (r"\b(lừa đảo|chiếm đoạt)\b", "úp sọt"),
]

class AIClient:
    """
    OpenAI-compatible AI Client supporting 9Router (AiFF), OpenAI, Gemini, DeepSeek, Groq.
    Handles Translation, SEO Generation, and Policy Compliance.
    """
    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None, model: Optional[str] = None):
        from ..config import config
        self.base_url = (base_url or config.get("AI_BASE_URL", "https://9router.n8n71.com/v1")).rstrip("/")
        self.api_key = api_key or config.get("AI_API_KEY", "")
        self.model = model or config.get("AI_MODEL", "AiFF")

    def test_connection(self) -> Dict[str, Any]:
        """Tests connectivity to the AI provider endpoint."""
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": "Ping test: Reply with 'OK'."}],
            "max_tokens": 10
        }
        try:
            res = requests.post(url, json=payload, headers=headers, timeout=12)
            if res.status_code == 200:
                data = res.json()
                reply = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                return {"success": True, "message": f"Kết nối AI thành công! Model phản hồi: {reply}"}
            return {"success": False, "error": f"Lỗi HTTP {res.status_code}: {res.text[:200]}"}
        except Exception as e:
            return {"success": False, "error": f"Lỗi kết nối AI: {str(e)}"}

    def _call_chat(self, prompt: str, system_prompt: str = "", temperature: float = 0.7, max_tokens: int = 1500) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json"
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        res = requests.post(url, json=payload, headers=headers, timeout=60)
        res.raise_for_status()
        data = res.json()
        content = data["choices"][0]["message"]["content"].strip()
        return content

    def sanitize_policy_words(self, text: str) -> str:
        """Replaces sensitive words with compliant slang to prevent TikTok & Facebook shadowbans."""
        sanitized = text
        for pattern, replacement in POLICY_SAFE_WORDS:
            sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)
        return sanitized

    def translate_srt(self, srt_content: str) -> str:
        """
        Translates raw foreign SRT (Chinese/English) into fluent, natural spoken Vietnamese.
        Strictly preserves SRT subtitle numbering and timestamp structure.
        """
        if not srt_content or not srt_content.strip():
            return ""

        system_prompt = (
            "Bạn là chuyên gia biên dịch phụ đề video phim và review chuyên nghiệp chuẩn Netflix. "
            "Nhiệm vụ: Dịch phụ đề từ tiếng Trung/tiếng Anh sang tiếng Việt tự nhiên, cuốn hút, gần gũi như người Việt nói chuyện. "
            "QUAN TRỌNG: Phải GIỮ NGUYÊN 100% số thứ tự cảnh và mốc thời gian (00:00:00,000 --> 00:00:00,000) của từng câu. "
            "Chỉ dịch nội dung chữ, mỗi câu phụ đề ngắn gọn, dễ đọc, 1 dòng duy nhất, không xuống dòng nhiều lần."
        )

        prompt = f"Hãy dịch toàn bộ nội dung phụ đề SRT sau sang tiếng Việt:\n\n{srt_content[:2500]}"
        translated_srt = self._call_chat(prompt=prompt, system_prompt=system_prompt, temperature=0.3, max_tokens=2000)

        # Remove markdown codeblocks if model outputs ```srt ... ```
        translated_srt = re.sub(r"^```[a-zA-Z]*\n", "", translated_srt)
        translated_srt = re.sub(r"\n```$", "", translated_srt)
        return self.sanitize_policy_words(translated_srt)

    def generate_seo_metadata(self, srt_content: str, product_hint: str = "") -> Dict[str, Any]:
        """
        Analyzes video transcript to generate viral title, engaging caption,
        hashtags, and Shopee search product keyword.
        """
        system_prompt = (
            "Bạn là chuyên gia sáng tạo nội dung hàng đầu cho TikTok và Facebook Reels tại Việt Nam. "
            "Dựa vào nội dung kịch bản/phụ đề video, hãy tạo nội dung đăng bài viral với tỷ lệ giữ chân cao."
        )

        prompt = f"""
Nội dung video / phụ đề:
"{srt_content[:2000]}"

Gợi ý sản phẩm/chủ đề (nếu có): "{product_hint}"

Hãy tạo kết quả đúng định dạng JSON thuần (KHÔNG bọc thẻ markdown):
{{
  "title": "MỘT DÒNG TIÊU ĐỀ IN HOA GIẬT GÂN GÂY TÒ MÒ, DƯỚI 80 KÝ TỰ",
  "caption": "Đoạn văn ngắn 2-3 câu khơi gợi sự tò mò khiến người xem phải xem hết video và để lại bình luận",
  "hashtags": "#KenhReup #reviewphim #douyin #videohot #xuhuong #trending",
  "product_name_vn": "tên sản phẩm tiếng Việt dùng để tìm trên sàn Shopee (ví dụ: gối cổ chữ u cao cấp)",
  "category": "Gia Dụng & Đời Sống",
  "summary": "Tóm tắt ngắn 1 câu về nội dung"
}}
"""
        response_text = self._call_chat(prompt=prompt, system_prompt=system_prompt, temperature=0.7)

        # Clean JSON markdown fences
        clean_text = re.sub(r"^```[a-zA-Z]*\n", "", response_text.strip())
        clean_text = re.sub(r"\n```$", "", clean_text).strip()

        try:
            data = json.loads(clean_text)
        except Exception:
            # Fallback if json parsing fails
            title_match = re.search(r'"title":\s*"([^"]+)"', clean_text)
            caption_match = re.search(r'"caption":\s*"([^"]+)"', clean_text)
            tags_match = re.search(r'"hashtags":\s*"([^"]+)"', clean_text)
            prod_match = re.search(r'"product_name_vn":\s*"([^"]+)"', clean_text)
            data = {
                "title": title_match.group(1) if title_match else "VIDEO REVIEW CỰC ĐỈNH KHÔNG THỂ BỎ QUA",
                "caption": caption_match.group(1) if caption_match else "Xem ngay đoạn kết bất ngờ ở cuối clip!",
                "hashtags": tags_match.group(1) if tags_match else "#xuhuong #review #trending #douyin",
                "product_name_vn": prod_match.group(1) if prod_match else (product_hint or "đồ gia dụng thông minh"),
                "category": "Tổng Hợp",
                "summary": "Video review nội dung hấp dẫn"
            }

        # Apply policy sanitization
        data["title"] = self.sanitize_policy_words(data.get("title", ""))
        data["caption"] = self.sanitize_policy_words(data.get("caption", ""))
        return data
