# -*- coding: utf-8 -*-
"""
payOS minimal stdlib client adapted from co-tuong/web-mvp/payos.py:
creates payment link, polls status, and verifies HMAC-SHA256 webhook signatures.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

DEFAULT_API_BASE = "https://api-merchant.payos.vn"
DEFAULT_PUBLIC_BASE = "http://127.0.0.1:8088"
TIMEOUT_S = 15


class PayOSError(Exception):
    """Raised when payOS API returns an error or network fails."""


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def credentials() -> tuple[str, str, str]:
    return _env("PAYOS_CLIENT_ID"), _env("PAYOS_API_KEY"), _env("PAYOS_CHECKSUM_KEY")


def is_configured() -> bool:
    return all(credentials())


def checksum_key() -> str:
    return _env("PAYOS_CHECKSUM_KEY")


def api_base() -> str:
    return (_env("PAYOS_API_BASE") or DEFAULT_API_BASE).rstrip("/")


def public_base() -> str:
    return (_env("PUBLIC_BASE_URL") or DEFAULT_PUBLIC_BASE).rstrip("/")


def _hmac_hex(key: str, msg: str) -> str:
    return hmac.new(key.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).hexdigest()


def _sort_obj(obj: dict[str, Any]) -> dict[str, Any]:
    return {k: obj[k] for k in sorted(obj.keys())}


def data_to_signature_string(data: dict[str, Any]) -> str:
    parts: list[str] = []
    for k in sorted(data.keys()):
        v = data[k]
        if v is None or v == "null" or v == "undefined":
            val = ""
        elif isinstance(v, list):
            val = json.dumps(
                [_sort_obj(i) if isinstance(i, dict) else i for i in v],
                separators=(",", ":"),
                ensure_ascii=False,
            )
        elif isinstance(v, dict):
            val = json.dumps(_sort_obj(v), separators=(",", ":"), ensure_ascii=False)
        elif isinstance(v, bool):
            val = "true" if v else "false"
        else:
            val = str(v)
        parts.append(f"{k}={val}")
    return "&".join(parts)


def verify_data_signature(data: dict[str, Any], signature: str | None, key: str | None = None) -> bool:
    key = key if key is not None else checksum_key()
    if not key or not signature or not isinstance(data, dict):
        return False
    computed = _hmac_hex(key, data_to_signature_string(data))
    return hmac.compare_digest(computed.lower(), str(signature).strip().lower())


def payment_request_signature(
    amount: int, cancel_url: str, description: str, order_code: int, return_url: str, key: str
) -> str:
    msg = (
        f"amount={amount}&cancelUrl={cancel_url}&description={description}"
        f"&orderCode={order_code}&returnUrl={return_url}"
    )
    return _hmac_hex(key, msg)


def _request(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    client_id, api_key, _ = credentials()
    url = api_base() + path
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=payload, method=method)
    req.add_header("x-client-id", client_id)
    req.add_header("x-api-key", api_key)
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise PayOSError(f"payOS HTTP {exc.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise PayOSError(f"Không kết nối được payOS: {type(exc).__name__}") from None
    try:
        res = json.loads(raw)
    except ValueError:
        raise PayOSError("payOS trả dữ liệu không phải JSON") from None
    if not isinstance(res, dict) or str(res.get("code")) != "00" or not isinstance(res.get("data"), dict):
        desc = res.get("desc") if isinstance(res, dict) else ""
        raise PayOSError(f"payOS từ chối: {desc or 'không rõ'}")
    return res


def short_description(order_code: str) -> str:
    prefix = _env("PAYMENT_PREFIX", "RS") or "RS"
    return f"{prefix}{str(order_code)[-6:]}"


def create_payment_link(
    order_code: str,
    amount: int,
    plan_label: str,
    contact: str = "",
) -> dict[str, Any]:
    _, _, key = credentials()
    code_int = int(order_code)
    base = public_base()
    return_url = f"{base}/?thanh-toan=xong&don={code_int}"
    cancel_url = f"{base}/?thanh-toan=huy&don={code_int}"
    description = short_description(order_code)
    body: dict[str, Any] = {
        "orderCode": code_int,
        "amount": int(amount),
        "description": description,
        "returnUrl": return_url,
        "cancelUrl": cancel_url,
        "items": [{"name": plan_label[:50], "quantity": 1, "price": int(amount)}],
        "signature": payment_request_signature(int(amount), cancel_url, description, code_int, return_url, key),
    }
    if contact:
        if "@" in contact:
            body["buyerEmail"] = contact
        else:
            body["buyerPhone"] = contact
    res = _request("POST", "/v2/payment-requests", body)
    data = res["data"]
    sig = res.get("signature")
    if sig and not verify_data_signature(data, sig, key):
        print("[payos] canh bao: chu ky phan hoi tao link khong khop", file=sys.stderr)
    if not data.get("checkoutUrl"):
        raise PayOSError("payOS không trả checkoutUrl")
    return data


def get_payment(order_code: str) -> dict[str, Any]:
    res = _request("GET", f"/v2/payment-requests/{int(order_code)}")
    return res["data"]
