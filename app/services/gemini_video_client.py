import os
import re
import json
import base64
import subprocess
import requests
from typing import Dict, Any, Optional, List, Tuple
from .ai_client import AIClient, parse_srt_blocks, format_srt_blocks
from .quota_pool import QuotaPoolManager


TRANSLATION_STYLE_PRESETS: Dict[str, str] = {
    "review_tom_tat": (
        "Phong cách Review / Tóm tắt phim kịch tính: Kể lại mạch phim gãy gọn, cuốn hút, nhịp nhanh dứt khoát. "
        "Phân biệt rõ Nam chính (anh / chàng trai), Nữ chính (cô / cô gái), Phản diện (hắn / ả / gã). "
        "Tuyệt đối không lẫn lộn người nói hay đổi đại từ xưng hô giữa chừng."
    ),
    "tong_tai_hien_dai": (
        "Bối cảnh Tổng tài / Đô thị hiện đại: Giữ xưng hô tự nhiên chuẩn phim hiện đại "
        "(cặp đôi: Anh - Em; xa cách/đối đầu: Tôi - Cô/Anh; cấp dưới với sếp: Chủ tịch/Tổng giám đốc - Tôi; "
        "phản diện: Tao - Mày / Hắn - Ả). Khóa cứng cặp xưng hô của từng cặp nhân vật xuyên suốt cả tập."
    ),
    "co_trang_tien_hiep": (
        "Bối cảnh Cổ trang / Cung đấu / Tiên hiệp: Dùng từ vựng cổ trang chuẩn xác "
        "(Trẫm - Nàng/Ái khanh, Bổn vương/Bổn tọa, Công tử - Tiểu thư, Sư phụ - Đệ tử, Huynh - Muội, Ta - Ngươi). "
        "Tuyệt đối không dùng từ lóng hiện đại."
    ),
    "hoc_duong_thanh_xuan": (
        "Bối cảnh Học đường / Thanh xuân vườn trường: Ngôn từ trẻ trung, tự nhiên "
        "(bạn bè cùng trang lứa: Cậu - Tớ hoặc Tôi - Bà/Ông; tiền bối: Đàn anh/Chị - Em; giáo viên: Thầy/Cô - Em)."
    ),
    "gia_dinh_drama": (
        "Bối cảnh Gia đình / Mẹ chồng nàng dâu / Đời sống: Xưng hô đúng thứ bậc gia đình Việt Nam "
        "(Bố/Mẹ - Con, Anh/Chị - Em, Chồng - Vợ: Anh - Em). Giữ cảm xúc thoại chân thực, kịch tính."
    ),
}


class GeminiVideoAnalyzer:
    """
    2-Stage Specialized Pipeline designed for full ~5-10 minute standard videos (80-150+ subtitle cues):
    - Stage A (`VIDEO_VIEW_MODEL` — e.g. `gemini-3.6-flash` / `gemini-3.5-flash`):
      Watches the full 5+ minute video, identifies every character's visual identity & relationship,
      builds a strict `character_bible` (pronoun rules so characters are NEVER confused), detects Shopee
      products, and extracts speaker-tagged `raw_srt` across the entire video duration.
    - Stage B (`SUB_TRANSLATE_MODEL` — e.g. `gemini-3.5-flash-lite` / `gemini-3.1-flash-lite` / `gemma-4-26b-a4b-it`):
      Translates `raw_srt` in context-aware batches of 25 cues using the `character_bible` + user's
      `CUSTOM_TRANSLATE_PROMPT` + sliding previous-lines memory, preserving 100% exact timestamps!
    """

    def _get_video_duration_sec(self, video_path: str) -> float:
        from ..config import get_ffmpeg_exe
        ffmpeg_bin = get_ffmpeg_exe()
        try:
            r = subprocess.run([ffmpeg_bin, "-i", video_path], capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=10)
            m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", r.stderr or "")
            if m:
                return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
        except Exception:
            pass
        return 300.0

    def build_vision_proxy(self, video_path: str, proxy_path: str, max_duration_sec: int = 660) -> str:
        """
        Compresses full 5-11 minute videos into an ultra-lightweight MP4 (< 3.5 MB)
        while keeping burned-in hardsubs and character faces sharp for Gemini Vision.
        """
        from ..config import get_ffmpeg_exe
        os.makedirs(os.path.dirname(os.path.abspath(proxy_path)), exist_ok=True)
        ffmpeg_bin = get_ffmpeg_exe()
        dur = self._get_video_duration_sec(video_path)

        # Adaptive resolution/bitrate so a 5-minute (300s) video stays ~2.0-2.8 MB
        if dur > 180:
            vf = "scale=-2:240,fps=1"
            crf = "36"
            ab = "20k"
        else:
            vf = "scale=-2:280,fps=1"
            crf = "35"
            ab = "24k"

        cmd = [
            ffmpeg_bin, "-y",
            "-i", video_path,
            "-t", str(max_duration_sec),
            "-vf", vf,
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", crf,
            "-c:a", "aac", "-ar", "16000", "-ac", "1", "-b:a", ab,
            proxy_path,
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        return proxy_path

    def _build_stage1_view_prompt(self, custom_prompt: str = "", product_hint: str = "") -> str:
        hint_line = f'- Gợi ý sản phẩm Shopee ưu tiên: "{product_hint}"\n' if product_hint else ""
        ctx_line = f'- Yêu cầu bối cảnh / xưng hô từ người dùng: "{custom_prompt}"\n' if custom_prompt else ""
        return (
            "Bạn là Đạo diễn Hình ảnh & Biên kịch Phân tích Video chuyên nghiệp.\n"
            "Hãy XEM TRỌN VẸN toàn bộ video từ đầu đến cuối (kể cả video dài 5-10 phút), ĐỌC chữ cứng trên màn hình (hardsub) và NGHE âm thanh.\n"
            f"{hint_line}{ctx_line}\n"
            "NHIỆM VỤ BƯỚC 1 (PHÂN TÍCH NHÂN VẬT & TRÍCH XUẤT KỊCH BẢN GỐC):\n"
            "1. Lập `character_bible` (Bảng Nhân Vật & Quy Tắc Xưng Hô Cố Định): Liệt kê từng nhân vật xuất hiện (ngoại hình/vai trò, giới tính, quan hệ với nhau, và CẶP ĐẠI TỪ XƯNG HÔ TIẾNG VIỆT CỐ ĐỊNH giữa họ để khi dịch không bao giờ lẫn lộn người nói).\n"
            "2. Trích xuất ĐẦY ĐỦ 100% các câu thoại/lời dẫn từ đầu đến hết video thành `raw_srt` chuẩn định dạng SRT (`HH:MM:SS,mmm --> HH:MM:SS,mmm`). Ở đầu mỗi câu trong `raw_srt`, hãy gắn nhãn người nói trong ngoặc vuông ví dụ `[Dẫn chuyện]`, `[Nam chính]`, `[Nữ chính]`, `[Phản diện]` rồi mới tới nội dung câu gốc.\n"
            "3. Nhận diện món đồ/sản phẩm thực tế trong video cho `product_name_vn` và viết `title`, `caption`, `hashtags`.\n\n"
            "Trả về DUY NHẤT một JSON thuần hợp lệ (KHÔNG bọc ```json):\n"
            "{\n"
            '  "genre_context": "Mô tả ngắn bối cảnh phim (VD: Tổng tài đô thị / Cổ trang / Học đường...)",\n'
            '  "character_bible": "Danh sách nhân vật & quy tắc xưng hô bắt buộc (VD: Nam chính Lâm Phong - Nữ chính Tô Uyển: xưng Anh - Em; Gã bảo vệ với Lâm Phong: xưng Tôi - Cậu...)",\n'
            '  "raw_srt": "1\\n00:00:00,500 --> 00:00:03,200\\n[Nam chính] Câu gốc 1\\n\\n2\\n00:00:03,400 --> 00:00:06,500\\n[Nữ chính] Câu gốc 2",\n'
            '  "title": "TIÊU ĐỀ IN HOA GIẬT GÂN VIRAL DƯỚI 80 KÝ TỰ",\n'
            '  "caption": "Đoạn mô tả 2-3 câu cuốn hút giữ chân người xem",\n'
            '  "hashtags": "#reviewphim #xuhuong #douyin #trending",\n'
            '  "product_name_vn": "tên sản phẩm cụ thể nhìn thấy trong video",\n'
            '  "summary": "Tóm tắt nội dung chính của toàn bộ video"\n'
            "}"
        )

    def _call_gemini_native_vision(self, api_key: str, model: str, b64_video: str, prompt: str) -> Optional[str]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {
            "contents": [
                {
                    "parts": [
                        {"inlineData": {"mimeType": "video/mp4", "data": b64_video}},
                        {"text": prompt},
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 8192,
                "responseMimeType": "application/json",
            },
        }
        res = requests.post(url, json=payload, timeout=150)
        if res.status_code in (429, 503, 402):
            QuotaPoolManager.mark_cooldown(api_key, seconds=60 if res.status_code == 503 else 120, model=model)
            return None
        if res.status_code != 200:
            QuotaPoolManager.mark_error(api_key, model=model)
            return None
        QuotaPoolManager.mark_success(api_key, model=model)
        candidates = res.json().get("candidates") or []
        if candidates:
            parts = ((candidates[0].get("content") or {}).get("parts")) or []
            if parts and parts[0].get("text"):
                return parts[0]["text"]
        return None

    def _call_openai_compat_vision(self, base_url: str, api_key: str, model: str, b64_video: str, prompt: str) -> Optional[str]:
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:video/mp4;base64,{b64_video}"}},
                    ],
                }
            ],
            "temperature": 0.2,
            "max_tokens": 8192,
        }
        res = requests.post(f"{base_url.rstrip('/')}/chat/completions", headers=headers, json=payload, timeout=150)
        if res.status_code in (429, 503, 402):
            QuotaPoolManager.mark_cooldown(api_key or base_url, seconds=60 if res.status_code == 503 else 120, model=model)
            return None
        if res.status_code != 200:
            QuotaPoolManager.mark_error(api_key or base_url, model=model)
            return None
        QuotaPoolManager.mark_success(api_key or base_url, model=model)
        choices = res.json().get("choices") or []
        if choices:
            return (choices[0].get("message") or {}).get("content")
        return None

    def _call_translate_model(self, system_prompt: str, user_prompt: str, preferred_translate_model: str) -> Optional[Tuple[str, str]]:
        """
        Calls Stage B (`SUB_TRANSLATE_MODEL`) explicitly prioritized by the user's selected translation model,
        with automatic failover across text/lite buckets so 5-minute multi-batch translations never drop!
        """
        providers = QuotaPoolManager.pick_healthy_providers(require_vision=False)
        for prov in providers:
            if prov["kind"] == "gemini_native":
                ordered = QuotaPoolManager.get_ordered_models_for_task(prov["api_key"], task="text")
                chain = [preferred_translate_model] + [m for m in ordered if m != preferred_translate_model]
                full_prompt = f"{system_prompt}\n\n{user_prompt}"
                for m_name in chain:
                    if QuotaPoolManager.is_in_cooldown(prov["api_key"], m_name):
                        continue
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{m_name}:generateContent?key={prov['api_key']}"
                    gen_cfg: Dict[str, Any] = {"temperature": 0.2, "maxOutputTokens": 4096}
                    if not m_name.startswith("gemma-"):
                        gen_cfg["responseMimeType"] = "application/json"
                    try:
                        r = requests.post(
                            url,
                            json={"contents": [{"parts": [{"text": full_prompt}]}], "generationConfig": gen_cfg},
                            timeout=60,
                        )
                        if r.status_code in (429, 503, 402):
                            QuotaPoolManager.mark_cooldown(prov["api_key"], seconds=60, model=m_name)
                            continue
                        if r.status_code == 200:
                            cands = r.json().get("candidates") or []
                            if cands:
                                txt = (((cands[0].get("content") or {}).get("parts")) or [{}])[0].get("text", "")
                                if txt:
                                    QuotaPoolManager.mark_success(prov["api_key"], model=m_name)
                                    return txt.strip(), f"{m_name} ({prov['fingerprint']})"
                    except Exception:
                        continue
            else:
                chain = [preferred_translate_model, prov["model"], "gemini-2.5-flash-lite"]
                seen = set()
                for m_name in chain:
                    if not m_name or m_name in seen:
                        continue
                    seen.add(m_name)
                    headers = {"Content-Type": "application/json"}
                    if prov["api_key"]:
                        headers["Authorization"] = f"Bearer {prov['api_key']}"
                    try:
                        r = requests.post(
                            f"{prov['base_url']}/chat/completions",
                            headers=headers,
                            json={
                                "model": m_name,
                                "messages": [
                                    {"role": "system", "content": system_prompt},
                                    {"role": "user", "content": user_prompt},
                                ],
                                "temperature": 0.2,
                                "max_tokens": 4096,
                            },
                            timeout=60,
                        )
                        if r.status_code in (429, 503, 402):
                            QuotaPoolManager.mark_cooldown(prov["api_key"] or prov["base_url"], seconds=60, model=m_name)
                            continue
                        if r.status_code == 200:
                            txt = (((r.json().get("choices") or [{}])[0].get("message")) or {}).get("content", "")
                            if txt:
                                QuotaPoolManager.mark_success(prov["api_key"] or prov["base_url"], model=m_name)
                                return txt.strip(), f"{m_name} ({prov['fingerprint']})"
                    except Exception:
                        continue
        return None

    @staticmethod
    def _strip_speaker_tag(line: str) -> str:
        """Removes leading `[Nam chính]:` / `(Nữ chính)` tags so TTS never speaks stage labels."""
        cleaned = re.sub(r"^\s*[\[\(][^\]\)]{1,28}[\]\)]\s*[:\-–]?\s*", "", line.strip())
        return cleaned.strip() or line.strip()

    def translate_srt_with_context(
        self,
        raw_srt: str,
        genre_context: str,
        character_bible: str,
        custom_prompt: str,
        translate_model: str,
    ) -> Tuple[str, str]:
        """
        Stage B: Translates 5-minute `raw_srt` in batches of 25 lines using `SUB_TRANSLATE_MODEL`,
        passing `character_bible` + `custom_prompt` + previous 4 translated lines to prevent any pronoun drift.
        """
        blocks = parse_srt_blocks(raw_srt)
        sanitizer = AIClient()
        if not blocks:
            return sanitizer.sanitize_policy_words(raw_srt), "none"

        batch_size = 25
        prev_context_pairs: List[str] = []
        used_model_badge = translate_model

        for start_i in range(0, len(blocks), batch_size):
            batch = blocks[start_i:start_i + batch_size]
            source_lines = [b["text"] for b in batch]
            n_items = len(source_lines)

            prev_str = "\n".join(prev_context_pairs[-5:]) if prev_context_pairs else "(Đầu video)"
            system_prompt = (
                "Bạn là biên dịch viên kịch bản lồng tiếng & Review Phim chuyên nghiệp tại Việt Nam.\n"
                f"=== BỐI CẢNH VIDEO ===\n{genre_context}\n"
                f"=== BẢNG NHÂN VẬT & QUY TẮC XƯNG HÔ CỐ ĐỊNH (BẮT BUỘC TUÂN THỦ 100%) ===\n{character_bible}\n"
                f"=== YÊU CẦU RIÊNG CỦA ĐẠO DIỄN (CUSTOM PROMPT) ===\n{custom_prompt}\n\n"
                "QUY TẮC BẮT BUỘC:\n"
                f"1. Dịch mảng JSON gồm {n_items} câu dưới đây sang tiếng Việt tự nhiên, gãy gọn, đúng nhịp lồng tiếng.\n"
                "2. Dựa vào nhãn `[Nhân vật]` ở đầu câu gốc và Bảng Nhân Vật để giữ ĐÚNG 100% cách xưng hô (anh-em, tôi-cô, trẫm-nàng, hắn-cô ấy...), TUYỆT ĐỐI KHÔNG LẪN LỘN NGƯỜI NÓI.\n"
                "3. XÓA BỎ hoàn toàn nhãn `[Nhân vật]` ở kết quả tiếng Việt (chỉ xuất câu thoại/lời dẫn sạch để máy đọc lồng tiếng).\n"
                f"4. Trả về DUY NHẤT 1 Mảng JSON (JSON Array) có ĐÚNG {n_items} chuỗi tiếng Việt tương ứng 1-1."
            )
            user_prompt = (
                f"Các câu vừa dịch liền trước để nối mạch xưng hô:\n{prev_str}\n\n"
                f"Hãy dịch mảng {n_items} câu tiếp theo (chỉ trả về JSON Array {n_items} phần tử):\n"
                f"{json.dumps(source_lines, ensure_ascii=False)}"
            )

            call_res = self._call_translate_model(system_prompt, user_prompt, preferred_translate_model=translate_model)
            translated_batch: List[str] = []
            if call_res:
                raw_reply, used_model_badge = call_res
                clean_reply = re.sub(r"^```[a-zA-Z]*\s*", "", raw_reply.strip())
                clean_reply = re.sub(r"\s*```$", "", clean_reply).strip()
                if not clean_reply.startswith("["):
                    m_arr = re.search(r"\[[\s\S]*\]", clean_reply)
                    if m_arr:
                        clean_reply = m_arr.group(0)
                try:
                    parsed = json.loads(clean_reply)
                    if isinstance(parsed, list):
                        translated_batch = [str(x).strip() for x in parsed]
                except Exception:
                    matches = re.findall(r'"((?:\\.|[^"\\])*)"', clean_reply)
                    if matches:
                        translated_batch = [m.strip() for m in matches]

            for idx_in_batch, blk in enumerate(batch):
                orig_line = blk["text"]
                if idx_in_batch < len(translated_batch) and translated_batch[idx_in_batch]:
                    vn_clean = self._strip_speaker_tag(translated_batch[idx_in_batch])
                else:
                    vn_clean = self._strip_speaker_tag(orig_line)
                vn_clean = sanitizer.sanitize_policy_words(vn_clean)
                blk["text"] = vn_clean
                prev_context_pairs.append(f"{orig_line} => {vn_clean}")

        return format_srt_blocks(blocks), used_model_badge

    def analyze_and_translate_video(
        self,
        video_path: str,
        work_dir: str,
        product_hint: str = "",
        custom_prompt: Optional[str] = None,
        view_model: Optional[str] = None,
        translate_model: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Executes the 2-Stage Pipeline:
          Stage A (`VIDEO_VIEW_MODEL`): Watches full 5+ min video -> Character Bible + Speaker-Tagged Raw SRT.
          Stage B (`SUB_TRANSLATE_MODEL`): Context-locked Vietnamese SRT translation honoring Custom Prompt.
        """
        from ..config import config

        preset_key = config.get("TRANSLATE_STYLE_PRESET", "review_tom_tat").strip()
        preset_text = TRANSLATION_STYLE_PRESETS.get(preset_key, TRANSLATION_STYLE_PRESETS["review_tom_tat"])
        user_custom = (
            custom_prompt
            if custom_prompt is not None
            else config.get("CUSTOM_TRANSLATE_PROMPT", "").strip()
        )
        effective_prompt = f"{preset_text}\n{user_custom}".strip() if user_custom else preset_text

        pref_view_model = (
            view_model
            or config.get("VIDEO_VIEW_MODEL", "")
            or config.get("GEMINI_VIDEO_MODEL", "gemini-3.1-flash-lite")
        ).strip() or "gemini-3.1-flash-lite"

        pref_trans_model = (
            translate_model
            or config.get("SUB_TRANSLATE_MODEL", "gemini-3.5-flash-lite")
        ).strip() or "gemini-3.5-flash-lite"

        proxy_path = os.path.join(work_dir, "_gemini_vision_proxy.mp4")
        try:
            self.build_vision_proxy(video_path, proxy_path, max_duration_sec=660)
            with open(proxy_path, "rb") as f:
                b64_video = base64.b64encode(f.read()).decode("ascii")
        except Exception as e:
            print(f"[GeminiVideoAnalyzer] Failed to build vision proxy: {e}")
            return None
        finally:
            if os.path.exists(proxy_path):
                try:
                    os.remove(proxy_path)
                except Exception:
                    pass

        stage1_prompt = self._build_stage1_view_prompt(custom_prompt=effective_prompt, product_hint=product_hint)
        stage1_data = None
        view_badge = ""

        providers = QuotaPoolManager.pick_healthy_providers(require_vision=True)
        for prov in providers:
            if prov["kind"] == "gemini_native":
                ordered_v = QuotaPoolManager.get_ordered_models_for_task(prov["api_key"], task="vision")
                v_chain = [pref_view_model] + [m for m in ordered_v if m != pref_view_model]
                for m_name in v_chain:
                    if QuotaPoolManager.is_in_cooldown(prov["api_key"], m_name):
                        continue
                    try:
                        raw_out = self._call_gemini_native_vision(prov["api_key"], m_name, b64_video, stage1_prompt)
                        stage1_data = self._extract_stage1_json(raw_out)
                        if stage1_data:
                            view_badge = f"{m_name} ({prov['fingerprint']})"
                            break
                    except Exception as e:
                        print(f"[GeminiVideoAnalyzer] Stage 1 Native ({m_name}) error: {e}")
                if stage1_data:
                    break
            else:
                v_chain = [pref_view_model, "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-3-flash-preview"]
                seen_m = set()
                for m_name in v_chain:
                    if not m_name or m_name in seen_m:
                        continue
                    seen_m.add(m_name)
                    try:
                        raw_out = self._call_openai_compat_vision(prov["base_url"], prov["api_key"], m_name, b64_video, stage1_prompt)
                        stage1_data = self._extract_stage1_json(raw_out)
                        if stage1_data:
                            view_badge = f"{m_name} ({prov['fingerprint']})"
                            break
                    except Exception as e:
                        print(f"[GeminiVideoAnalyzer] Stage 1 Compat ({m_name}) error: {e}")
                if stage1_data:
                    break

        if not stage1_data:
            return None

        raw_srt = stage1_data["raw_srt"]
        genre_context = stage1_data["genre_context"]
        character_bible = stage1_data["character_bible"]

        # Stage B: Context-aware Vietnamese translation with dedicated SUB_TRANSLATE_MODEL
        vn_srt, trans_badge = self.translate_srt_with_context(
            raw_srt=raw_srt,
            genre_context=genre_context,
            character_bible=character_bible,
            custom_prompt=effective_prompt,
            translate_model=pref_trans_model,
        )

        sanitizer = AIClient()
        return {
            "vietnamese_srt": vn_srt,
            "raw_srt": raw_srt,
            "genre_context": genre_context,
            "character_bible": character_bible,
            "title": sanitizer.sanitize_policy_words(stage1_data["title"]),
            "caption": sanitizer.sanitize_policy_words(stage1_data["caption"]),
            "hashtags": stage1_data["hashtags"],
            "product_name_vn": stage1_data["product_name_vn"] or product_hint or "đồ gia dụng thông minh",
            "summary": stage1_data["summary"],
            "view_model_used": view_badge,
            "translate_model_used": trans_badge,
            "provider_used": f"Xem Video: {view_badge} ➔ Dịch Sub: {trans_badge}",
        }

    @staticmethod
    def _extract_stage1_json(raw_text: Optional[str]) -> Optional[Dict[str, Any]]:
        if not raw_text:
            return None
        clean = re.sub(r"^```[a-zA-Z]*\s*", "", raw_text.strip())
        clean = re.sub(r"\s*```$", "", clean).strip()
        if not clean.startswith("{"):
            m = re.search(r"\{[\s\S]*\}", clean)
            if m:
                clean = m.group(0)
        try:
            data = json.loads(clean)
        except Exception:
            return None

        raw_srt = str(data.get("raw_srt") or data.get("vietnamese_srt") or "").strip()
        if "-->" not in raw_srt:
            return None

        return {
            "genre_context": str(data.get("genre_context") or "Phim ngắn Douyin"),
            "character_bible": str(data.get("character_bible") or "Giữ xưng hô tự nhiên, nhất quán theo ngữ cảnh."),
            "raw_srt": raw_srt,
            "title": str(data.get("title") or "DIỄN BIẾN BẤT NGỜ KHIẾN AI CŨNG ĐỨNG HÌNH"),
            "caption": str(data.get("caption") or "Xem hết video để biết cái kết không tưởng ở phút cuối nhé!"),
            "hashtags": str(data.get("hashtags") or "#reviewphim #xuhuong #douyin #trending"),
            "product_name_vn": str(data.get("product_name_vn") or ""),
            "summary": str(data.get("summary") or ""),
        }
