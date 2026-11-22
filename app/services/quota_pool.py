import os
import re
import time
import subprocess
import requests
from typing import Dict, Any, List
from .security_fingerprint import SecurityFingerprintManager


def is_google_native_key(key: str) -> bool:
    """Recognizes both classic `AIza...` keys and new Google AI Studio / Express `AQ....` keys."""
    k = (key or "").strip()
    return k.startswith("AIza") or k.startswith("AQ.")


class QuotaPoolManager:
    """
    Multi-Key & Multi-Model Bucket Router.
    Tracks rate-limit / overload cooldowns at the granular `(key_fingerprint, model)` bucket level,
    multiplying a single free Google `AQ.` / `AIza` key's capacity across 6+ independent model buckets:
    - Vision Buckets: `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`, `gemini-3.6-flash`,
      `gemini-3.5-flash`, `gemini-3-flash-preview`
    - Text/SEO Buckets: `gemma-4-26b-a4b-it` (high RPD), `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`
    """

    VISION_MODEL_BUCKETS = [
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3-flash-preview",
        "gemini-3.7-flash",
        "gemini-3.8-flash",
    ]

    TEXT_MODEL_BUCKETS = [
        "gemma-4-26b-a4b-it",
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemma-4-31b-it",
        "gemini-3.6-flash",
    ]

    _cooldowns: Dict[str, float] = {}
    _stats: Dict[str, Dict[str, int]] = {}
    _rr_index: int = 0
    _model_rr_index: int = 0

    @classmethod
    def _bucket_id(cls, secret: str, model: str = "") -> str:
        fp = SecurityFingerprintManager.secret_fingerprint(secret)
        return f"{fp}:{model}" if model else fp

    @classmethod
    def _record_stat(cls, bucket: str, field: str):
        entry = cls._stats.setdefault(bucket, {"success": 0, "errors": 0, "rate_limited": 0})
        entry[field] = entry.get(field, 0) + 1

    @classmethod
    def mark_cooldown(cls, secret: str, seconds: int = 90, model: str = ""):
        bucket = cls._bucket_id(secret, model)
        cls._cooldowns[bucket] = time.time() + seconds
        cls._record_stat(bucket, "rate_limited")

    @classmethod
    def mark_success(cls, secret: str, model: str = ""):
        bucket = cls._bucket_id(secret, model)
        cls._cooldowns.pop(bucket, None)
        cls._record_stat(bucket, "success")

    @classmethod
    def mark_error(cls, secret: str, model: str = ""):
        bucket = cls._bucket_id(secret, model)
        cls._record_stat(bucket, "errors")

    @classmethod
    def is_in_cooldown(cls, secret: str, model: str = "") -> bool:
        bucket = cls._bucket_id(secret, model)
        until = cls._cooldowns.get(bucket, 0)
        if until and time.time() < until:
            return True
        if until:
            cls._cooldowns.pop(bucket, None)
        return False

    @classmethod
    def get_ordered_models_for_task(cls, secret: str, task: str = "vision") -> List[str]:
        """
        Returns healthy models rotated round-robin for the given `task` ('vision' or 'text'),
        putting any temporarily rate-limited models at the end.
        """
        base_list = list(cls.VISION_MODEL_BUCKETS if task == "vision" else cls.TEXT_MODEL_BUCKETS)
        if len(base_list) > 1:
            idx = cls._model_rr_index % len(base_list)
            cls._model_rr_index += 1
            base_list = base_list[idx:] + base_list[:idx]

        healthy = [m for m in base_list if not cls.is_in_cooldown(secret, m)]
        cooled = [m for m in base_list if cls.is_in_cooldown(secret, m)]
        return healthy + cooled

    @classmethod
    def get_all_providers(cls) -> List[Dict[str, Any]]:
        from ..config import config

        providers: List[Dict[str, Any]] = []
        seen_fps = set()

        def _add(kind: str, base_url: str, api_key: str, model: str, label: str):
            identity = f"{kind}|{base_url}|{api_key}"
            fp = SecurityFingerprintManager.secret_fingerprint(api_key or identity)
            if fp in seen_fps:
                return
            seen_fps.add(fp)
            # Aggregate stats across all model buckets of this key
            agg = {"success": 0, "errors": 0, "rate_limited": 0}
            for b_key, st in cls._stats.items():
                if b_key.startswith(fp):
                    for k_s in agg:
                        agg[k_s] += st.get(k_s, 0)

            providers.append({
                "kind": kind,
                "base_url": base_url.rstrip("/"),
                "api_key": api_key.strip(),
                "model": model.strip(),
                "label": label,
                "fingerprint": fp,
                "in_cooldown": cls.is_in_cooldown(api_key or identity),
                "cooldown_remaining_sec": max(0, int(cls._cooldowns.get(fp, 0) - time.time())),
                "stats": agg,
            })

        # 1. Google AI Studio / Express Gemini Native Keys (`GEMINI_API_KEYS`: supports both `AQ.` and `AIza`)
        raw_gemini_keys = config.get("GEMINI_API_KEYS", "")
        gemini_model = config.get("GEMINI_VIDEO_MODEL", "gemini-3.5-flash-lite").strip() or "gemini-3.5-flash-lite"
        for line in re.split(r"[\r\n,;]+", raw_gemini_keys):
            k = line.strip()
            if k:
                is_native = is_google_native_key(k)
                _add(
                    kind="gemini_native" if is_native else "openai_compat",
                    base_url="https://generativelanguage.googleapis.com/v1beta" if is_native else config.get("AI_BASE_URL", "https://api.shopaikey.com/v1"),
                    api_key=k,
                    model=gemini_model,
                    label="Google Gemini Native (Multi-Model Split)" if is_native else "Gemini Gateway Key",
                )

        # 2. Primary configured AI_API_KEY
        primary_key = config.get("AI_API_KEY", "").strip()
        primary_base = config.get("AI_BASE_URL", "https://api.shopaikey.com/v1").strip()
        primary_model = config.get("AI_MODEL", "gemini-2.5-flash-lite").strip() or "gemini-2.5-flash-lite"
        if primary_key:
            if is_google_native_key(primary_key):
                _add("gemini_native", "https://generativelanguage.googleapis.com/v1beta", primary_key, gemini_model, "Primary Google Gemini Key")
            else:
                _add("openai_compat", primary_base, primary_key, primary_model, "Primary AI Endpoint")

        # 3. Multi-Key Pool (`AI_KEY_POOL`)
        raw_pool = config.get("AI_KEY_POOL", "")
        for line in raw_pool.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "|" in line:
                parts = [p.strip() for p in line.split("|")]
                b_url = parts[0] if len(parts) > 0 else primary_base
                k_val = parts[1] if len(parts) > 1 else ""
                m_val = parts[2] if len(parts) > 2 and parts[2] else gemini_model
                _add("openai_compat", b_url, k_val, m_val, f"Pool ({b_url})")
            elif is_google_native_key(line):
                _add("gemini_native", "https://generativelanguage.googleapis.com/v1beta", line, gemini_model, "Pool Google Gemini Native")
            elif line.startswith("gsk_"):
                _add("openai_compat", "https://api.groq.com/openai/v1", line, "llama-3.3-70b-versatile", "Pool Groq Cloud Free")
            elif line.startswith("sk-or-"):
                _add("openai_compat", "https://openrouter.ai/api/v1", line, "google/gemini-2.5-flash", "Pool OpenRouter")
            else:
                _add("openai_compat", primary_base, line, primary_model, "Pool Gateway Key")

        # 4. Local Quota-Login Gateways (9Router localhost:20128)
        quota_gateway_url = config.get("QUOTA_LOGIN_GATEWAY_URL", "").strip()
        if quota_gateway_url:
            quota_key = config.get("QUOTA_LOGIN_API_KEY", "9router-local").strip() or "9router-local"
            _add("openai_compat", quota_gateway_url, quota_key, gemini_model, "Quota Login Router")

        return providers

    @classmethod
    def pick_healthy_providers(cls, require_vision: bool = False) -> List[Dict[str, Any]]:
        all_p = cls.get_all_providers()
        healthy = [p for p in all_p if not p["in_cooldown"]]
        candidates = healthy if healthy else all_p
        if require_vision:
            vision_ready = [
                dict(p) for p in candidates
                if not (p["kind"] == "openai_compat" and "groq.com" in p["base_url"])
            ]
            if vision_ready:
                candidates = vision_ready

        if len(candidates) > 1:
            start = cls._rr_index % len(candidates)
            cls._rr_index += 1
            candidates = candidates[start:] + candidates[:start]
        return candidates

    @classmethod
    def detect_local_quota_gateways(cls) -> Dict[str, Any]:
        detected = []
        for name, base_url, dashboard_url in [
            ("9Router (OAuth Quota Login: Antigravity / Gemini / Claude / Copilot)", "http://127.0.0.1:20128/v1", "http://127.0.0.1:20128"),
            ("CLIProxyAPI (OAuth Gemini / Codex)", "http://127.0.0.1:8317/v1", "http://127.0.0.1:8317"),
        ]:
            try:
                r = requests.get(f"{base_url}/models", timeout=1.5)
                detected.append({
                    "name": name,
                    "base_url": base_url,
                    "dashboard_url": dashboard_url,
                    "online": r.status_code in (200, 401),
                })
            except Exception:
                detected.append({
                    "name": name,
                    "base_url": base_url,
                    "dashboard_url": dashboard_url,
                    "online": False,
                })

        providers = cls.get_all_providers()
        safe_providers = [
            {
                "label": p["label"],
                "kind": p["kind"],
                "base_url": p["base_url"],
                "model": p["model"],
                "vision_buckets": cls.VISION_MODEL_BUCKETS[:5] if p["kind"] == "gemini_native" else [p["model"]],
                "text_buckets": cls.TEXT_MODEL_BUCKETS[:3] if p["kind"] == "gemini_native" else [p["model"]],
                "fingerprint": p["fingerprint"],
                "in_cooldown": p["in_cooldown"],
                "stats": p["stats"],
            }
            for p in providers
        ]
        return {
            "total_keys": len(safe_providers),
            "healthy_keys": sum(1 for p in safe_providers if not p["in_cooldown"]),
            "model_split_strategy": {
                "video_vision_buckets": cls.VISION_MODEL_BUCKETS[:5],
                "text_seo_buckets": cls.TEXT_MODEL_BUCKETS[:3],
            },
            "providers": safe_providers,
            "local_gateways": detected,
            "free_key_links": {
                "google_ai_studio": "https://aistudio.google.com/app/apikey",
                "groq_cloud": "https://console.groq.com/keys",
                "openrouter": "https://openrouter.ai/keys",
            },
            "9router_install_cmd": "npx -y 9router",
        }

    @classmethod
    def start_local_9router(cls) -> Dict[str, Any]:
        import shutil
        npx_bin = shutil.which("npx")
        if not npx_bin:
            return {
                "success": False,
                "error": "Máy chưa cài Node.js/npx. Bạn có thể lấy mã Gemini API miễn phí trong 5 giây tại https://aistudio.google.com/app/apikey và dán vào ô GEMINI_API_KEYS.",
            }
        try:
            r = requests.get("http://127.0.0.1:20128", timeout=1.5)
            if r.status_code < 500:
                from ..config import config
                config.set("QUOTA_LOGIN_GATEWAY_URL", "http://127.0.0.1:20128/v1")
                return {
                    "success": True,
                    "already_running": True,
                    "dashboard_url": "http://127.0.0.1:20128",
                    "message": "9Router đang chạy sẵn! Hãy mở http://127.0.0.1:20128 để bấm Login Google / Antigravity / Gemini CLI.",
                }
        except Exception:
            pass

        try:
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS if os.name == "nt" else 0
            subprocess.Popen(
                [npx_bin, "-y", "9router"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
            from ..config import config
            config.set("QUOTA_LOGIN_GATEWAY_URL", "http://127.0.0.1:20128/v1")
            return {
                "success": True,
                "dashboard_url": "http://127.0.0.1:20128",
                "message": "Đã khởi chạy cổng 9Router ở chế độ nền! Đợi ~5 giây rồi mở http://127.0.0.1:20128 để đăng nhập Quota Google / Antigravity / Gemini.",
            }
        except Exception as e:
            return {"success": False, "error": f"Không thể khởi chạy 9Router: {e}"}
