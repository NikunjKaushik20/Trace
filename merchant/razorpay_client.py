"""
Thin Razorpay test-mode client for the Buildathon merchant demo.

Independent of api/routers/portal.py's Razorpay integration, which bills
developers for TRACE API usage -- a different purpose. This one represents
the merchant charging an AI buyer agent for a purchase.

Safety: hard-refuses to run against a live key. This script fires
synthetic Sybil-ring purchase attempts; it must never be pointed at a real
payment credential.
"""
import os
import logging
import time

import razorpay
import requests

logger = logging.getLogger("buildathon.razorpay")

# Retry only transport-level failures (connection dropped, timed out --
# never got an HTTP response at all) -- e.g. the "Connection aborted...
# RemoteDisconnected" blip seen live during testing, gone on the very next
# attempt. A real response, even an error one (bad request, auth failure,
# Razorpay-side 5xx wrapped as razorpay.errors.*), means the request did
# land and retrying won't change the outcome -- those propagate immediately.
_TRANSIENT_ORDER_CREATE_RETRIES = 2
_TRANSIENT_ORDER_CREATE_BACKOFF_S = 0.4


class LiveKeyGuardError(RuntimeError):
    """Raised if a non-test Razorpay key is configured. Refuses to proceed."""


class MerchantRazorpayClient:
    def __init__(self, key_id: str | None = None, key_secret: str | None = None):
        key_id = key_id or os.environ.get("RAZORPAY_KEY_ID", "")
        key_secret = key_secret or os.environ.get("RAZORPAY_KEY_SECRET", "")

        if not key_id or not key_secret:
            raise RuntimeError(
                "RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET not set. "
                "Copy buildathon/.env.example to buildathon/.env and fill in "
                "your Razorpay TEST-mode keys (dashboard -> Test Mode -> API Keys)."
            )
        if not key_id.startswith("rzp_test_"):
            raise LiveKeyGuardError(
                f"Refusing to run: RAZORPAY_KEY_ID '{key_id[:12]}...' is not a "
                "test-mode key (expected 'rzp_test_' prefix). This demo fires "
                "synthetic fraud simulations and must never touch a live key."
            )

        self._client = razorpay.Client(auth=(key_id, key_secret))

    @property
    def key_id(self) -> str:
        """The public key_id half of the credential pair -- this one is
        meant to ship to a browser (Razorpay Checkout.js needs it to open
        the payment modal); key_secret never leaves this process."""
        return self._client.auth[0]

    def create_order(self, amount_inr_rupees: float, receipt: str, notes: dict) -> dict:
        """Create a Razorpay test-mode order. Amount is in whole rupees.

        Retries a couple of times on a transport-level failure (the request
        never reached Razorpay, or the connection was dropped before a
        response came back) -- not on an actual error response, which
        retrying can't fix."""
        amount_paise = int(round(amount_inr_rupees * 100))
        payload = {
            "amount": amount_paise,
            "currency": "INR",
            "receipt": receipt,
            "notes": notes,
        }
        attempts = _TRANSIENT_ORDER_CREATE_RETRIES + 1
        for attempt in range(1, attempts + 1):
            try:
                return self._client.order.create(payload)
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                if attempt == attempts:
                    raise
                logger.warning(
                    f"Razorpay order creation attempt {attempt}/{attempts} hit a transport "
                    f"error ({e}); retrying in {_TRANSIENT_ORDER_CREATE_BACKOFF_S}s."
                )
                time.sleep(_TRANSIENT_ORDER_CREATE_BACKOFF_S)

    def verify_payment_signature(
        self, razorpay_order_id: str, razorpay_payment_id: str, razorpay_signature: str
    ) -> bool:
        """Verify the HMAC-SHA256 signature Razorpay Checkout.js's client-side
        `handler` callback returns on a successful payment -- Razorpay's own
        documented pattern for confirming that callback wasn't forged before
        trusting it (the SDK computes
        HMAC_SHA256(order_id + "|" + payment_id, key_secret) and compares).
        This is a *complement* to the /webhooks/razorpay receiver, not a
        replacement: the webhook is Razorpay's own server telling us a
        payment captured (works without the browser ever calling back, and
        survives the buyer closing the tab); this is the browser telling us
        what Checkout.js told it, verified so it can't be forged, letting a
        fully local demo -- no public ngrok URL required -- show a captured
        payment immediately in the UI."""
        try:
            self._client.utility.verify_payment_signature({
                "razorpay_order_id": razorpay_order_id,
                "razorpay_payment_id": razorpay_payment_id,
                "razorpay_signature": razorpay_signature,
            })
            return True
        except razorpay.errors.SignatureVerificationError:
            return False
