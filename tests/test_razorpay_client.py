"""
Unit tests for the live-key safety guard in merchant/razorpay_client.py.
No network calls are made -- these only test key-format validation, which
happens before any HTTP request would be sent.

Run from the Trace-API repo root:
    pytest buildathon/tests/test_razorpay_client.py -v
"""
import pytest
import razorpay

from buildathon.merchant.razorpay_client import MerchantRazorpayClient, LiveKeyGuardError


def test_refuses_live_key():
    with pytest.raises(LiveKeyGuardError):
        MerchantRazorpayClient(key_id="rzp_live_abc123", key_secret="secret")


def test_refuses_missing_keys():
    with pytest.raises(RuntimeError):
        MerchantRazorpayClient(key_id="", key_secret="")


def test_accepts_test_key():
    # Construction only stores credentials; it doesn't call Razorpay.
    client = MerchantRazorpayClient(key_id="rzp_test_abc123", key_secret="secret")
    assert client is not None


def test_key_id_exposes_the_public_half_only():
    client = MerchantRazorpayClient(key_id="rzp_test_abc123", key_secret="topsecret")
    assert client.key_id == "rzp_test_abc123"
    # key_secret is never exposed through any public attribute or method --
    # only stored inside the wrapped razorpay.Client, which .key_id doesn't
    # touch.
    assert not hasattr(client, "key_secret")


def test_verify_payment_signature_accepts_a_correctly_signed_payload():
    """No network call -- this is pure HMAC-SHA256 math the SDK does
    locally, over order_id + '|' + payment_id, keyed by key_secret. Same
    computation Razorpay's own server did to produce the signature
    Checkout.js hands back on a genuine payment."""
    import hashlib
    import hmac

    secret = "topsecret"
    client = MerchantRazorpayClient(key_id="rzp_test_abc123", key_secret=secret)
    order_id, payment_id = "order_ABC", "pay_XYZ"
    signature = hmac.new(
        secret.encode("utf-8"), f"{order_id}|{payment_id}".encode("utf-8"), hashlib.sha256
    ).hexdigest()

    assert client.verify_payment_signature(order_id, payment_id, signature) is True


def test_verify_payment_signature_rejects_a_forged_payload():
    client = MerchantRazorpayClient(key_id="rzp_test_abc123", key_secret="topsecret")
    assert client.verify_payment_signature("order_ABC", "pay_XYZ", "not_a_real_signature") is False


def test_create_order_retries_a_transport_level_failure_then_succeeds(monkeypatch):
    """Reproduces the live 'Connection aborted... RemoteDisconnected' blip
    seen during manual testing: the first call never gets an HTTP response
    at all, the second one does. create_order should retry, not bubble the
    first failure."""
    import requests

    client = MerchantRazorpayClient(key_id="rzp_test_abc123", key_secret="topsecret")
    calls = []

    def flaky_create(payload):
        calls.append(payload)
        if len(calls) == 1:
            raise requests.exceptions.ConnectionError("Connection aborted.")
        return {"id": "order_ok", **payload}

    monkeypatch.setattr(client._client.order, "create", flaky_create)
    monkeypatch.setattr("buildathon.merchant.razorpay_client.time.sleep", lambda _: None)

    order = client.create_order(amount_inr_rupees=50, receipt="r1", notes={})

    assert order["id"] == "order_ok"
    assert len(calls) == 2


def test_create_order_gives_up_after_repeated_transport_failures(monkeypatch):
    """A persistent outage (not a one-off blip) should still surface as a
    real failure -- app.py's /buy-credits catches this and reports
    order_creation_failed rather than retrying forever."""
    import requests

    client = MerchantRazorpayClient(key_id="rzp_test_abc123", key_secret="topsecret")

    def always_fails(payload):
        raise requests.exceptions.ConnectionError("Connection aborted.")

    monkeypatch.setattr(client._client.order, "create", always_fails)
    monkeypatch.setattr("buildathon.merchant.razorpay_client.time.sleep", lambda _: None)

    with pytest.raises(requests.exceptions.ConnectionError):
        client.create_order(amount_inr_rupees=50, receipt="r1", notes={})


def test_create_order_does_not_retry_a_real_error_response(monkeypatch):
    """A BadRequestError means Razorpay answered -- retrying wastes time and
    can't change a genuinely bad request (e.g. malformed amount)."""
    client = MerchantRazorpayClient(key_id="rzp_test_abc123", key_secret="topsecret")
    calls = []

    def bad_request(payload):
        calls.append(payload)
        raise razorpay.errors.BadRequestError("amount must be at least 100")

    monkeypatch.setattr(client._client.order, "create", bad_request)

    with pytest.raises(razorpay.errors.BadRequestError):
        client.create_order(amount_inr_rupees=0.5, receipt="r1", notes={})

    assert len(calls) == 1
