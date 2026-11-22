# -*- coding: utf-8 -*-
"""
Portable, zero-dependency VietQR payment gateway supporting SePay (0 VND/month)
and payOS — synced from DoanDuyThanh71/co-tuong (`web-mvp/payment_gateway.py`)
with DEFAULT_PREFIX = "RS" so Reup Studio & Co Tuong share one SePay bank account
cleanly without webhook order collisions.
"""
from __future__ import annotations

import hmac
import json
import math
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any, Mapping

try:
    if __package__:
        from . import payos as _payos  # type: ignore[no-redef]
    else:
        import payos as _payos  # type: ignore[no-redef]
except ImportError:
    _payos = None  # type: ignore[assignment]

DEFAULT_PREFIX = "RS"
VIETQR_IMG_BASE = "https://img.vietqr.io/image"
DEFAULT_SEPAY_API_BASE = "https://my.sepay.vn"


class PaymentGatewayError(Exception):
    """Raised when a payment gateway configuration or API call fails."""


@dataclass(frozen=True)
class PaymentLink:
    provider: str
    order_code: str
    amount_vnd: int
    transfer_content: str
    qr_image_url: str = ""
    qr_code: str = ""
    checkout_url: str = ""
    payment_link_id: str = ""
    bank_code: str = ""
    account_number: str = ""
    account_name: str = ""
    bin: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WebhookEvent:
    provider: str
    valid_auth: bool
    is_paid: bool
    order_code: str | None
    amount_vnd: int = 0
    reference: str = ""
    raw_content: str = ""
    gateway: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def get_prefix() -> str:
    return _env("PAYMENT_PREFIX", DEFAULT_PREFIX) or DEFAULT_PREFIX


def transfer_content(order_code: str | int) -> str:
    code = str(order_code).strip()
    return f"{get_prefix()}{code}"


def _parse_positive_int(raw: Any) -> int:
    if raw is None or isinstance(raw, bool):
        return 0
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return 0
    if not math.isfinite(val) or val <= 0:
        return 0
    return int(val)


def _header_ci(headers: Mapping[str, str] | None, name: str) -> str:
    if not headers:
        return ""
    target = name.lower()
    for key, val in headers.items():
        if str(key).lower() == target:
            return str(val).strip()
    return ""


class SePayGateway:
    """
    Zero-monthly-fee VietQR gateway via SePay webhook and/or User API polling + img.vietqr.io.
    """

    @staticmethod
    def credentials() -> tuple[str, str, str, str]:
        return (
            _env("SEPAY_BANK_CODE"),
            _env("SEPAY_ACCOUNT_NO"),
            _env("SEPAY_ACCOUNT_NAME"),
            _env("SEPAY_WEBHOOK_API_KEY"),
        )

    @staticmethod
    def api_token() -> str:
        return _env("SEPAY_API_TOKEN")

    @staticmethod
    def api_base() -> str:
        return (_env("SEPAY_API_BASE") or DEFAULT_SEPAY_API_BASE).rstrip("/")

    @classmethod
    def has_api_token(cls) -> bool:
        return bool(cls.api_token())

    @staticmethod
    def has_webhook_key() -> bool:
        return bool(_env("SEPAY_WEBHOOK_API_KEY"))

    @classmethod
    def is_configured(cls) -> bool:
        bank, acc, acc_name, webhook_key = cls.credentials()
        return bool(bank and acc and acc_name and (webhook_key or cls.api_token()))

    @classmethod
    def create_payment(
        cls,
        order_code: str | int,
        amount_vnd: int,
        description: str = "",
    ) -> PaymentLink:
        bank, acc, acc_name, webhook_key = cls.credentials()
        if not (bank and acc and acc_name and (webhook_key or cls.api_token())):
            raise PaymentGatewayError("SePay chua duoc cau hinh day du.")
        code = str(order_code).strip()
        if not code:
            raise PaymentGatewayError("order_code khong hop le.")
        amt = int(amount_vnd)
        if amt <= 0:
            raise PaymentGatewayError("amount_vnd phai > 0.")

        memo = transfer_content(code)
        bank_q = urllib.parse.quote(bank, safe="")
        acc_q = urllib.parse.quote(acc, safe="")
        info_q = urllib.parse.quote(memo, safe="")
        name_q = urllib.parse.quote(acc_name, safe="")
        qr_url = (
            f"{VIETQR_IMG_BASE}/{bank_q}-{acc_q}-compact2.png"
            f"?amount={amt}&addInfo={info_q}&accountName={name_q}"
        )
        return PaymentLink(
            provider="sepay",
            order_code=code,
            amount_vnd=amt,
            transfer_content=memo,
            qr_image_url=qr_url,
            bank_code=bank,
            account_number=acc,
            account_name=acc_name,
        )

    @classmethod
    def list_transactions(cls, limit: int = 20, timeout: float = 8.0) -> list[dict[str, Any]]:
        token = cls.api_token()
        _, acc, _, _ = cls.credentials()
        if not token:
            raise PaymentGatewayError("SePay API token chua duoc cau hinh.")
        params: dict[str, Any] = {"limit": max(1, min(int(limit), 100))}
        if acc:
            params["account_number"] = acc
        url = f"{cls.api_base()}/userapi/transactions/list?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(
            url,
            method="GET",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "User-Agent": "ReupStudio/2.0",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            raise PaymentGatewayError(f"SePay API HTTP {exc.code}") from None
        except urllib.error.URLError as exc:
            raise PaymentGatewayError(f"SePay API loi ket noi: {exc.reason}") from None
        except TimeoutError:
            raise PaymentGatewayError("SePay API timeout") from None

        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise PaymentGatewayError("SePay API tra ve JSON khong hop le.") from None
        if not isinstance(payload, dict):
            raise PaymentGatewayError("SePay API tra ve du lieu khong hop le.")

        rows = payload.get("transactions")
        if rows is None:
            rows = payload.get("data")
        if not isinstance(rows, list):
            return []
        return [r for r in rows if isinstance(r, dict)]

    @classmethod
    def poll_order(
        cls,
        order_code: str | int,
        min_amount_vnd: int,
        limit: int = 25,
    ) -> WebhookEvent | None:
        target_code = str(order_code).strip()
        if not target_code or not cls.has_api_token():
            return None
        bank, _, _, _ = cls.credentials()
        txs = cls.list_transactions(limit=limit)
        for tx in txs:
            if "transfer_type" in tx and tx.get("transfer_type") is not None:
                if str(tx.get("transfer_type")).strip().lower() != "in":
                    continue
            amount_in = _parse_positive_int(tx.get("amount_in"))
            if amount_in < int(min_amount_vnd) or amount_in <= 0:
                continue
            content = tx.get("transaction_content")
            if content is None:
                content = tx.get("content")
            extracted = cls.extract_order_code({"content": content, "code": tx.get("code")})
            if extracted != target_code:
                continue
            return WebhookEvent(
                provider="sepay",
                valid_auth=True,
                is_paid=True,
                order_code=target_code,
                amount_vnd=amount_in,
                reference=str(tx.get("reference_number") or tx.get("id") or "")[:60],
                raw_content=str(content or tx.get("code") or "")[:200],
                gateway=str(tx.get("bank_brand_name") or bank or "sepay")[:30],
            )
        return None

    @staticmethod
    def verify_auth(headers: Mapping[str, str] | None) -> bool:
        expected = _env("SEPAY_WEBHOOK_API_KEY")
        if not expected:
            return False
        auth = _header_ci(headers, "authorization")
        if not auth:
            return False
        parts = auth.split(None, 1)
        if len(parts) != 2 or parts[0].lower() != "apikey":
            return False
        token = parts[1].strip()
        if not token:
            return False
        return hmac.compare_digest(token.encode("utf-8"), expected.encode("utf-8"))

    @staticmethod
    def extract_order_code(payload: Mapping[str, Any]) -> str | None:
        prefix = get_prefix()
        pattern = re.compile(
            rf"(?:^|[^A-Za-z0-9]){re.escape(prefix)}(\d{{6,18}})(?!\d)",
            re.IGNORECASE,
        )
        for field in (payload.get("content"), payload.get("code")):
            if not isinstance(field, str) or not field.strip():
                continue
            match = pattern.search(field)
            if match:
                return match.group(1)
        return None

    @classmethod
    def verify_webhook(
        cls,
        headers: Mapping[str, str] | None,
        payload: Mapping[str, Any] | None,
    ) -> WebhookEvent:
        if not cls.verify_auth(headers):
            return WebhookEvent(
                provider="sepay",
                valid_auth=False,
                is_paid=False,
                order_code=None,
            )
        if not isinstance(payload, Mapping):
            return WebhookEvent(
                provider="sepay",
                valid_auth=True,
                is_paid=False,
                order_code=None,
            )

        transfer_type = str(payload.get("transferType") or "").strip().lower()
        amount_vnd = _parse_positive_int(payload.get("transferAmount"))
        order_code = cls.extract_order_code(payload)
        raw_content = str(payload.get("content") or payload.get("code") or "")[:200]
        reference = str(payload.get("referenceCode") or payload.get("id") or "")[:60]
        gateway = str(payload.get("gateway") or "")[:30]

        is_paid = transfer_type == "in" and amount_vnd > 0 and order_code is not None
        return WebhookEvent(
            provider="sepay",
            valid_auth=True,
            is_paid=is_paid,
            order_code=order_code,
            amount_vnd=amount_vnd,
            reference=reference,
            raw_content=raw_content,
            gateway=gateway,
        )


class PayOSGateway:
    @staticmethod
    def is_configured() -> bool:
        return bool(_payos is not None and _payos.is_configured())

    @staticmethod
    def checksum_key() -> str:
        return _payos.checksum_key() if _payos is not None else ""

    @staticmethod
    def verify_signature(data: dict[str, Any], signature: str | None, key: str | None = None) -> bool:
        if _payos is None:
            return False
        return bool(_payos.verify_data_signature(data, signature, key))

    @staticmethod
    def create_payment(
        order_code: str | int,
        amount_vnd: int,
        description: str = "",
        contact: str = "",
    ) -> PaymentLink:
        if _payos is None or not _payos.is_configured():
            raise PaymentGatewayError("payOS chua duoc cau hinh.")
        code = str(order_code).strip()
        label = description or "Reup Studio"
        try:
            link = _payos.create_payment_link(
                order_code=code,
                amount=int(amount_vnd),
                plan_label=label,
                contact=contact,
            )
        except _payos.PayOSError as exc:
            raise PaymentGatewayError(str(exc)) from exc
        return PaymentLink(
            provider="payos",
            order_code=code,
            amount_vnd=int(amount_vnd),
            transfer_content=str(link.get("description") or _payos.short_description(code)),
            qr_code=str(link.get("qrCode") or ""),
            checkout_url=str(link.get("checkoutUrl") or ""),
            payment_link_id=str(link.get("paymentLinkId") or ""),
            account_number=str(link.get("accountNumber") or ""),
            account_name=str(link.get("accountName") or ""),
            bin=str(link.get("bin") or ""),
        )

    @staticmethod
    def get_payment(order_code: str | int) -> dict[str, Any]:
        if _payos is None:
            raise PaymentGatewayError("payOS module not available.")
        try:
            return _payos.get_payment(str(order_code))
        except _payos.PayOSError as exc:
            raise PaymentGatewayError(str(exc)) from exc


def get_active_provider() -> str | None:
    pref = _env("PAYMENT_PROVIDER", "auto").lower() or "auto"
    if pref == "payos":
        return "payos" if PayOSGateway.is_configured() else None
    if pref == "sepay":
        return "sepay" if SePayGateway.is_configured() else None
    if pref == "auto":
        if PayOSGateway.is_configured():
            return "payos"
        if SePayGateway.is_configured():
            return "sepay"
        return None
    return None


def gateway_status() -> dict[str, Any]:
    payos_ok = PayOSGateway.is_configured()
    sepay_ok = SePayGateway.is_configured()
    active = get_active_provider()
    return {
        "configured": active is not None,
        "provider": active,
        "configured_provider": _env("PAYMENT_PROVIDER", "auto").lower() or "auto",
        "payos_configured": payos_ok,
        "sepay_configured": sepay_ok,
        "sepay_api_poll": SePayGateway.has_api_token(),
        "prefix": get_prefix(),
    }


def create_payment(
    order_code: str | int,
    amount_vnd: int,
    description: str = "",
    contact: str = "",
) -> PaymentLink:
    active = get_active_provider()
    if active == "payos":
        return PayOSGateway.create_payment(
            order_code=order_code,
            amount_vnd=amount_vnd,
            description=description,
            contact=contact,
        )
    if active == "sepay":
        return SePayGateway.create_payment(
            order_code=order_code,
            amount_vnd=amount_vnd,
            description=description,
        )
    raise PaymentGatewayError("Chua co cong thanh toan nao duoc cau hinh.")
