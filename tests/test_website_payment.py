import os
import sys
from pathlib import Path
from fastapi.testclient import TestClient

WEBSITE_DIR = Path(__file__).resolve().parent.parent / "website"
if str(WEBSITE_DIR) not in sys.path:
    sys.path.insert(0, str(WEBSITE_DIR))

import payment_gateway  # noqa: E402
import server as portal_server  # noqa: E402


def test_sepay_gateway_qr_and_webhook_extraction(monkeypatch):
    monkeypatch.setenv("PAYMENT_PROVIDER", "sepay")
    monkeypatch.setenv("PAYMENT_PREFIX", "RS")
    monkeypatch.setenv("SEPAY_BANK_CODE", "MB")
    monkeypatch.setenv("SEPAY_ACCOUNT_NO", "0987654321")
    monkeypatch.setenv("SEPAY_ACCOUNT_NAME", "REUP STUDIO")
    monkeypatch.setenv("SEPAY_WEBHOOK_API_KEY", "secret-webhook-key-123")

    st = payment_gateway.gateway_status()
    assert st["configured"] is True
    assert st["provider"] == "sepay"
    assert st["prefix"] == "RS"

    link = payment_gateway.create_payment("812345678901", 50000, "Ve Buoi Meet")
    assert link.transfer_content == "RS812345678901"
    assert "MB-0987654321-compact2.png" in link.qr_image_url
    assert "amount=50000" in link.qr_image_url
    assert "addInfo=RS812345678901" in link.qr_image_url

    # Invalid auth rejected
    bad_ev = payment_gateway.SePayGateway.verify_webhook(
        {"Authorization": "Apikey wrong"},
        {"transferType": "in", "transferAmount": 50000, "content": "CK RS812345678901"},
    )
    assert bad_ev.valid_auth is False

    # Valid transfer with RS prefix extracted; CTV prefix from co-tuong ignored!
    ctv_ev = payment_gateway.SePayGateway.verify_webhook(
        {"Authorization": "Apikey secret-webhook-key-123"},
        {"transferType": "in", "transferAmount": 50000, "content": "CTV812345678901"},
    )
    assert ctv_ev.valid_auth is True
    assert ctv_ev.is_paid is False
    assert ctv_ev.order_code is None

    ok_ev = payment_gateway.SePayGateway.verify_webhook(
        {"Authorization": "Apikey secret-webhook-key-123"},
        {"transferType": "in", "transferAmount": 50000, "content": "MBVCB.123.RS812345678901 chuyen khoan"},
    )
    assert ok_ev.valid_auth is True
    assert ok_ev.is_paid is True
    assert ok_ev.order_code == "812345678901"


def test_portal_order_and_sepay_webhook_auto_activate(monkeypatch, tmp_path):
    monkeypatch.setattr(portal_server, "DB_PATH", tmp_path / "test_portal.db")
    portal_server.init_db()
    monkeypatch.setenv("PAYMENT_PROVIDER", "sepay")
    monkeypatch.setenv("PAYMENT_PREFIX", "RS")
    monkeypatch.setenv("SEPAY_BANK_CODE", "MB")
    monkeypatch.setenv("SEPAY_ACCOUNT_NO", "0987654321")
    monkeypatch.setenv("SEPAY_ACCOUNT_NAME", "REUP STUDIO")
    monkeypatch.setenv("SEPAY_WEBHOOK_API_KEY", "hook-secret-xyz")
    monkeypatch.setenv("SEPAY_API_TOKEN", "")

    client = TestClient(portal_server.app)

    # Register a device first, then buy PRO_MONTHLY -> device auto-upgrades to PRO upon webhook!
    r_dev = client.post(
        "/api/v1/register-device",
        json={"email": "pro_buyer@gmail.com", "hwid": "HWID-AAAA-BBBB-CCCC"},
    )
    assert r_dev.status_code == 200
    assert r_dev.json()["plan"] == "FREE_TRIAL"

    r_ord = client.post(
        "/api/v1/order",
        json={"email": "pro_buyer@gmail.com", "zalo_phone": "0912345678", "tier": "PRO_MONTHLY"},
    )
    assert r_ord.status_code == 200
    ord_data = r_ord.json()
    code = ord_data["order_code"]
    assert ord_data["transfer_content"] == f"RS{code}"
    assert ord_data["amount_vnd"] == 149000

    # Webhook triggers instant activation
    r_wh = client.post(
        "/api/payment/sepay-webhook",
        headers={"Authorization": "Apikey hook-secret-xyz"},
        json={"transferType": "in", "transferAmount": 149000, "content": f"GD {ord_data['transfer_content']}"},
    )
    assert r_wh.status_code == 200
    assert r_wh.json()["activated"] is True

    # Polling endpoint now returns PAID + minted PRO key
    r_poll = client.get(f"/api/v1/orders/{code}")
    assert r_poll.status_code == 200
    poll_data = r_poll.json()
    assert poll_data["status"] == "PAID"
    assert poll_data["fulfilled_key"].startswith("PRO-")

    # Device is now upgraded to PRO!
    r_dev2 = client.post(
        "/api/v1/register-device",
        json={"email": "pro_buyer@gmail.com", "hwid": "HWID-AAAA-BBBB-CCCC"},
    )
    assert r_dev2.json()["plan"] == "PRO"
