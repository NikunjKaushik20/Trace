"""
Razorpay payment-capture webhook receiver for the Buildathon merchant demo.

/buy-credits only proves a Razorpay *order* was created -- Razorpay
doesn't consider a payment real until a buyer completes checkout and
Razorpay calls this endpoint with payment.captured (or payment.failed).
Signature verification follows the same HMAC-SHA256-over-raw-body pattern
already used in api/routers/webhooks.py's x402 settlement webhook, for
the same reason: the webhook secret is the only thing that makes "a
payment happened" more trustworthy than an unauthenticated POST claiming
so. NOTE, same caveat as that file: confirm the exact header name and
payload shape against Razorpay's current webhook docs before pointing a
live webhook at this -- this is a secure default, not a verified
integration already exercised against Razorpay's real webhook traffic.

Deliberately additive and read-only with respect to the purchase flow: it
records captures for observability, it does not change /buy-credits'
gate.check()/report_outcome() behavior. That decision (report on
order-creation + would_allow, not on eventual capture) is already
validated against the naive/protected comparison in
tests/test_merchant_app.py; changing it to fire on capture instead would
need its own regression pass against that same comparison, and running it
for real needs a public callback URL (e.g. ngrok) reachable by Razorpay --
which is why the live panel demo uses the synthetic marketplace run
instead of this webhook. This flow is demonstrated in the recorded pitch
video and by tests/test_razorpay_webhook.py's signed-payload tests, not
by a live public endpoint running continuously.
"""
import hashlib
import hmac
import json
import logging
import os
from dataclasses import dataclass
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger("buildathon.merchant.webhooks")

router = APIRouter()

# Deliberately a separate secret from the root repo's RAZORPAY_WEBHOOK_SECRET
# (api/config.py's x402_facilitator_webhook_secret / the portal billing
# webhook) -- different endpoint, different purpose, no reason to share a
# credential across them.
RAZORPAY_WEBHOOK_SECRET = os.environ.get("BUILDATHON_RAZORPAY_WEBHOOK_SECRET", "")

CAPTURE_EVENTS = ("payment.captured", "payment.failed")


@dataclass
class CapturedPayment:
    razorpay_order_id: str
    razorpay_payment_id: Optional[str]
    event: str  # "payment.captured" | "payment.failed"
    amount_paise: int


# In-memory, single-process -- same documented scope as merchant/app.py's
# idempotency cache and velocity tracker. A real deployment would persist
# this (DB row keyed by razorpay_order_id), same call already made for
# TRACE's own EventRecord.
captured_payments: Dict[str, CapturedPayment] = {}


def _verify_signature(payload_bytes: bytes, signature_header: str) -> bool:
    if not RAZORPAY_WEBHOOK_SECRET or not signature_header:
        return False
    expected = hmac.new(
        RAZORPAY_WEBHOOK_SECRET.encode("utf-8"), payload_bytes, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


@router.post("/webhooks/razorpay")
async def razorpay_webhook(request: Request):
    if not RAZORPAY_WEBHOOK_SECRET:
        raise HTTPException(
            status_code=503,
            detail="Razorpay webhook is not configured on this deployment "
                   "(BUILDATHON_RAZORPAY_WEBHOOK_SECRET unset).",
        )

    payload_bytes = await request.body()
    sig_header = request.headers.get("x-razorpay-signature", "")
    if not _verify_signature(payload_bytes, sig_header):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    try:
        payload = json.loads(payload_bytes)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Malformed JSON payload")

    event = payload.get("event", "")
    if event not in CAPTURE_EVENTS:
        return {"status": "ignored", "event": event}

    entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
    order_id = entity.get("order_id")
    if not order_id:
        raise HTTPException(status_code=400, detail="Missing payload.payment.entity.order_id")

    captured_payments[order_id] = CapturedPayment(
        razorpay_order_id=order_id,
        razorpay_payment_id=entity.get("id"),
        event=event,
        amount_paise=entity.get("amount", 0),
    )
    logger.info(f"Razorpay webhook: {event} for order {order_id} (payment {entity.get('id')})")
    return {"status": "recorded", "event": event, "order_id": order_id}


@router.get("/orders/{razorpay_order_id}/capture-status")
async def get_capture_status(razorpay_order_id: str):
    """Query whether a given /buy-credits order was actually captured --
    the honest answer to 'did money really move,' distinct from
    /buy-credits' own status field which only ever reflects order
    *creation* (see app.py's PurchaseResponse docstring)."""
    captured = captured_payments.get(razorpay_order_id)
    if captured is None:
        return {"razorpay_order_id": razorpay_order_id, "captured": False, "event": None}
    return {
        "razorpay_order_id": razorpay_order_id,
        "captured": captured.event == "payment.captured",
        "event": captured.event,
        "razorpay_payment_id": captured.razorpay_payment_id,
    }
