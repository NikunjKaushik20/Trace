"""
Tests for buildathon/merchant/webhooks.py's Razorpay payment-capture
webhook. No network calls -- signed payloads are constructed directly with
the same HMAC-SHA256 scheme the endpoint verifies.

Run from the Trace-API repo root:
    pytest buildathon/tests/test_razorpay_webhook.py -v
"""
import hashlib
import hmac
import json

import httpx
import pytest

from buildathon.merchant.app import app
import buildathon.merchant.webhooks as webhooks_module

TEST_SECRET = "whsec_test_only_do_not_use_in_prod"


def _signed_payload(payload: dict) -> tuple:
    body = json.dumps(payload).encode("utf-8")
    sig = hmac.new(TEST_SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return body, sig


def _payment_payload(event: str, order_id: str = "order_test_abc123", payment_id: str = "pay_test_xyz", amount_paise: int = 5000) -> dict:
    return {
        "event": event,
        "payload": {"payment": {"entity": {"order_id": order_id, "id": payment_id, "amount": amount_paise}}},
    }


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    monkeypatch.setattr(webhooks_module, "RAZORPAY_WEBHOOK_SECRET", TEST_SECRET)
    webhooks_module.captured_payments.clear()
    yield
    webhooks_module.captured_payments.clear()


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_rejects_when_secret_not_configured(monkeypatch):
    monkeypatch.setattr(webhooks_module, "RAZORPAY_WEBHOOK_SECRET", "")
    body, sig = _signed_payload(_payment_payload("payment.captured"))

    async with _client() as c:
        resp = await c.post("/webhooks/razorpay", content=body, headers={"x-razorpay-signature": sig})

    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_rejects_invalid_signature():
    body, _ = _signed_payload(_payment_payload("payment.captured"))

    async with _client() as c:
        resp = await c.post("/webhooks/razorpay", content=body, headers={"x-razorpay-signature": "not-the-real-signature"})

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_rejects_missing_signature_header():
    body, _ = _signed_payload(_payment_payload("payment.captured"))

    async with _client() as c:
        resp = await c.post("/webhooks/razorpay", content=body)

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_valid_payment_captured_is_recorded_and_queryable():
    body, sig = _signed_payload(_payment_payload("payment.captured", order_id="order_captured_1"))

    async with _client() as c:
        webhook_resp = await c.post("/webhooks/razorpay", content=body, headers={"x-razorpay-signature": sig})
        status_resp = await c.get("/orders/order_captured_1/capture-status")

    assert webhook_resp.status_code == 200
    assert webhook_resp.json()["status"] == "recorded"

    status_body = status_resp.json()
    assert status_body["captured"] is True
    assert status_body["event"] == "payment.captured"
    assert status_body["razorpay_payment_id"] == "pay_test_xyz"


@pytest.mark.asyncio
async def test_valid_payment_failed_is_recorded_as_not_captured():
    body, sig = _signed_payload(_payment_payload("payment.failed", order_id="order_failed_1"))

    async with _client() as c:
        await c.post("/webhooks/razorpay", content=body, headers={"x-razorpay-signature": sig})
        status_resp = await c.get("/orders/order_failed_1/capture-status")

    status_body = status_resp.json()
    assert status_body["captured"] is False
    assert status_body["event"] == "payment.failed"


@pytest.mark.asyncio
async def test_unrelated_event_is_ignored():
    body, sig = _signed_payload({"event": "order.paid", "payload": {}})

    async with _client() as c:
        resp = await c.post("/webhooks/razorpay", content=body, headers={"x-razorpay-signature": sig})

    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"
    assert webhooks_module.captured_payments == {}


@pytest.mark.asyncio
async def test_missing_order_id_is_rejected():
    payload = {"event": "payment.captured", "payload": {"payment": {"entity": {"id": "pay_no_order"}}}}
    body, sig = _signed_payload(payload)

    async with _client() as c:
        resp = await c.post("/webhooks/razorpay", content=body, headers={"x-razorpay-signature": sig})

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_capture_status_unknown_order_reports_not_captured():
    async with _client() as c:
        resp = await c.get("/orders/never-seen-order/capture-status")

    body = resp.json()
    assert body["captured"] is False
    assert body["event"] is None
