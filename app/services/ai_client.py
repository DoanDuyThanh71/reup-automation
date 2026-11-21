import os
import re
import json
import requests
from typing import Dict, Any, Optional, List, Tuple

POLICY_SAFE_WORDS = [
    (r"\b(chết|tử vong)\b", "đăng xuất"),
    (r"\b(giết|đánh nhau|đánh đập|chém)\b", "tác động vật lý"),
    (r"\b(tự tử|tự sát)\b", "nghĩ quẩn"),
    (r"\b(máu me|đổ máu)\b", "si-rô đỏ"),
    (r"\b(ma túy|thuốc phiện|cần sa)\b", "chất cấm"),
    (r"\b(súng đạn|vũ khí)\b", "đồ chơi nguy hiểm"),
    (r"\b(lừa đảo|chiếm đoạt)\b", "úp sọt"),
]

SRT_BLOCK_REGEX = re.compile(
    r"(\d+)\s*\r?\n(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})\s*\r?\n([\s\S]*?)(?=\r?\n\r?\n|\Z)"
)

def srt_time_to_ms(t_str: str) -> int:
    parts = re.split(r"[:,]", t_str.strip())
    if len(parts) != 4:
        return 0
    h, m, s, ms = (int(x) for x in parts)
    return h * 3600000 + m * 60000 + s * 1000 + ms

def ms_to_srt_time(ms: int) -> str:
    ms = max(0, int(ms))
    h = ms // 3600000
    ms %= 3600000
    m = ms // 60000
    ms %= 60000
    s = ms // 1000
    mili = ms % 1000
    return f"{h:02d}:{m:02d}:{s:02d},{mili:03d}"

def parse_srt_blocks(srt_content: str) -> List[Dict[str, Any]]:
    blocks = []
    for m in SRT_BLOCK_REGEX.finditer(srt_content.strip()):
        start_str, end_str = m.group(2), m.group(3)
        text = " ".join(line.strip() for line in m.group(4).splitlines() if line.strip())
        if not text:
            continue
        blocks.append({
            "id": len(blocks) + 1,
            "start_ms": srt_time_to_ms(start_str),
            "end_ms": srt_time_to_ms(end_str),
            "start_str": start_str,
            "end_str": end_str,
            "text": text
        })
    return blocks

def format_srt_blocks(blocks: List[Dict[str, Any]]) -> str:
    lines = []
    for idx, b in enumerate(blocks, 1):
        start_s = ms_to_srt_time(b["start_ms"])
        end_s = ms_to_srt_time(b["end_ms"])
        lines.append(f"{idx}\n{start_s} --> {end_s}\n{b['text']}\n")
    return "\n".join(lines)

class AIClient:
    """
    OpenAI-compatible AI Client supporting 9Router (AiFF), ShopAIKey, OpenAI, Gemini, DeepSeek, Groq.
    Implements strict 1-to-1 timestamp-preserving SRT translation so subtitle cues never drift from original video timing.
    """
    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None, model: Optional[str] = None):
        from ..config import config
        self.base_url = (base_url or config.get("AI_BASE_URL", "https://9router.n8n71.com/v1")).rstrip("/")
        self.api_key = api_key or config.get("AI_API_KEY", "")
        self.model = model or config.get("AI_MODEL", "AiFF")

    def test_connection(self) -> Dict[str, Any]:
        """Tests connectivity to the AI provider endpoint."""
        url = f"{self.base_url}/chat/completions"
        headers = {"Content-Type": "application/json"}
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

    def _call_chat(self, prompt: str, system_prompt: str = "", temperature: float = 0.3, max_tokens: int = 2000) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {"Content-Type": "application/json"}
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
        return data["choices"][0]["message"]["content"].strip()

    def sanitize_policy_words(self, text: str) -> str:
        """Replaces sensitive words with compliant slang to prevent TikTok & Facebook shadowbans."""
        sanitized = text
        for pattern, replacement in POLICY_SAFE_WORDS:
            sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)
        return sanitized

    def translate_srt(self, srt_content: str) -> str:
        """
        Translates raw foreign SRT into concise, natural spoken Vietnamese while preserving
        100% of original start/end timestamps 1-to-1 (via JSON array batch translation, with fallback).
        """
        if not srt_content or not srt_content.strip():
            return ""

        blocks = parse_srt_blocks(srt_content)
        if not blocks:
            # Fallback if input is not standard multi-block SRT
            system_prompt = (
                "Bạn là biên dịch viên phụ đề phim ngắn Douyin sang tiếng Việt. "
                "Giữ nguyên 100% số thứ tự và mốc thời gian (00:00:00,000 --> 00:00:00,000), chỉ dịch câu thoại ngắn gọn."
            )
            raw_out = self._call_chat(f"Hãy dịch toàn bộ nội dung phụ đề SRT sau sang tiếng Việt:\n\n{srt_content[:2500]}", system_prompt=system_prompt)
            raw_out = re.sub(r"^```[a-zA-Z]*\n", "", raw_out)
            raw_out = re.sub(r"\n```$", "", raw_out)
            return self.sanitize_policy_words(raw_out)

        # Translate in batches of 25 lines using strict 1-to-1 JSON array mapping
        # (Exact algorithm proven in user's Sub video (1).json 'Code in JavaScript2' + 'Merged Srt')
        batch_size = 25
        for start_i in range(0, len(blocks), batch_size):
            batch = blocks[start_i:start_i + batch_size]
            source_texts = [b["text"] for b in batch]
            n_items = len(source_texts)

            system_prompt = (
                "Bạn là biên dịch viên lồng tiếng phim ngắn Douyin sang tiếng Việt chuyên nghiệp. "
                f"Nhiệm vụ: Dịch mảng JSON gồm {n_items} câu thoại tiếng Trung dưới đây sang tiếng Việt tự nhiên, "
                "ngắn gọn, súc tích để đọc vừa khít thời lượng câu gốc. "
                f"YÊU CẦU BẮT BUỘC: Đầu ra PHẢI là một Mảng JSON (JSON Array) có đúng {n_items} phần tử chuỗi tiếng Việt tương ứng 1-1. "
                "KHÔNG gộp câu, KHÔNG tách câu, chỉ trả về JSON Array thuần túy."
            )
            prompt = json.dumps(source_texts, ensure_ascii=False)
            raw_reply = self._call_chat(prompt=prompt, system_prompt=system_prompt, temperature=0.25, max_tokens=2000)

            clean_reply = re.sub(r"^```[a-zA-Z]*\s*", "", raw_reply.strip())
            clean_reply = re.sub(r"\s*```$", "", clean_reply).strip()

            translated_batch: List[str] = []
            try:
                parsed = json.loads(clean_reply)
                if isinstance(parsed, list):
                    translated_batch = [str(x).strip() for x in parsed]
            except Exception:
                # Fallback if model returned SRT or line-by-line instead of JSON array
                parsed_srt = parse_srt_blocks(clean_reply)
                if parsed_srt:
                    translated_batch = [b["text"] for b in parsed_srt]
                else:
                    matches = re.findall(r'"((?:\\.|[^"\\])*)"', clean_reply)
                    if matches:
                        translated_batch = [m.strip() for m in matches]
                    else:
                        translated_batch = [line.strip() for line in clean_reply.splitlines() if line.strip() and "-->" not in line and not line.strip().isdigit()]

            for idx_in_batch, b in enumerate(batch):
                if idx_in_batch < len(translated_batch) and translated_batch[idx_in_batch]:
                    b["text"] = self.sanitize_policy_words(translated_batch[idx_in_batch])
                else:
                    b["text"] = self.sanitize_policy_words(b["text"])

        return format_srt_blocks(blocks)

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

        clean_text = re.sub(r"^```[a-zA-Z]*\n", "", response_text.strip())
        clean_text = re.sub(r"\n```$", "", clean_text).strip()

        try:
            data = json.loads(clean_text)
        except Exception:
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

        data["title"] = self.sanitize_policy_words(data.get("title", ""))
        data["caption"] = self.sanitize_policy_words(data.get("caption", ""))
        return data
