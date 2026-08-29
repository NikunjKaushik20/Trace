import hmac
import hashlib
import logging

from fastapi import APIRouter, Request, HTTPException
from sqlalchemy.future import select

from ..config import settings
from ..models import (
    SettlementWebhookPayload,
    SettlementWebhookResponse,
    LightningSettlementWebhookPayload,
)
from ..database import AsyncSessionLocal, EventRecord
from ..state import state_manager
from ..lightning import verify_lightning_settlement

logger = logging.getLogger("trace.api")

router = APIRouter()


def _verify_signature(payload_bytes: bytes, signature_header: str) -> bool:
    """
    Generic HMAC-SHA256-over-raw-body verification, matching the header name
    a settlement facilitator sends. NOTE: confirm the exact header name and
    algorithm against the real facilitator's webhook docs before pointing a
    live facilitator at this endpoint — this is a secure default, not a
    verified integration with any specific provider's API.
    """
    if not signature_header:
        return False
    expected = hmac.new(
        settings.x402_facilitator_webhook_secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


@router.post("/webhooks/x402", response_model=SettlementWebhookResponse)
async def x402_settlement_webhook(request: Request):
    """
    Facilitator-verified settlement confirmation. Independent source of
    truth for job outcomes, separate from developer self-reports via
    /v1/events. Cross-checks against any existing self-report for the same
    job_id:
      - no prior record -> settlement itself becomes the recorded outcome
      - prior record agrees -> marked facilitator_verified
      - prior record disagrees -> marked disputed, and a corrective failure
        outcome is applied on top of whatever was already counted
    """
    if not settings.x402_facilitator_webhook_secret:
        raise HTTPException(
            status_code=503,
            detail="x402 facilitator webhook is not configured on this deployment",
        )

    payload_bytes = await request.body()
    sig_header = request.headers.get("x-webhook-signature", "")

    if not _verify_signature(payload_bytes, sig_header):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    data = SettlementWebhookPayload.model_validate_json(payload_bytes)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(EventRecord).filter(EventRecord.job_id == data.job_id)
        )
        record = result.scalars().first()

        if record is None:
            # Settlement arrived with no self-report at all (common for
            # integrators who only wire payments, not explicit reporting).
            # The settlement itself is the ground truth for this job.
            record = EventRecord(
                job_id=data.job_id,
                provider_id=data.provider_id,
                buyer_id=data.buyer_id,
                reporter_id=f"facilitator:{data.facilitator}",
                price_usdc=data.price_usdc,
                success=data.settled,
                settlement_proof=data.settlement_proof,
                verification_status="facilitator_verified",
            )
            session.add(record)
            await session.commit()
            await state_manager.apply_outcome(data.provider_id, data.settled)
            return SettlementWebhookResponse(
                status="recorded", verification_status="facilitator_verified"
            )

        record.settlement_proof = data.settlement_proof

        if record.success == data.settled:
            record.verification_status = "facilitator_verified"
            await session.commit()
            return SettlementWebhookResponse(
                status="confirmed", verification_status="facilitator_verified"
            )

        # Self-report said one thing, settlement says another. Flag it and
        # apply a corrective outcome — this is a stronger fraud signal than
        # an ordinary failure, since the provider (or their integrator)
        # actively misreported the result.
        record.verification_status = "disputed"
        await session.commit()
        logger.warning(
            f"Settlement mismatch for job_id={data.job_id} provider={data.provider_id}: "
            f"self-reported success={record.success}, facilitator settled={data.settled}"
        )
        await state_manager.apply_outcome(data.provider_id, success=False)
        return SettlementWebhookResponse(status="disputed", verification_status="disputed")


@router.post("/webhooks/lightning", response_model=SettlementWebhookResponse)
async def lightning_settlement_webhook(payload: LightningSettlementWebhookPayload):
    """
    Preimage-verified settlement confirmation for the Lightning rail.
    Independent source of truth for job outcomes, same role as
    /webhooks/x402 but with a different trust model: there's no facilitator
    to sign a claim, so the proof is the payment preimage itself --
    verify_lightning_settlement() checks sha256(preimage) == the invoice's
    payment_hash, which is only satisfiable if the invoice was actually paid.

    One structural asymmetry vs. the x402 path: a preimage can only prove a
    payment DID settle, never that one didn't (there's no cryptographic way
    to prove a negative here). So this endpoint only ever asserts
    success=True -- it cannot report a verified failure the way x402's
    facilitator-signed `settled=False` can.
    """
    result = verify_lightning_settlement(payload.bolt11_invoice, payload.preimage)
    if not result.valid:
        raise HTTPException(status_code=400, detail=f"Invalid Lightning settlement proof: {result.reason}")

    async with AsyncSessionLocal() as session:
        query = await session.execute(
            select(EventRecord).filter(EventRecord.job_id == payload.job_id)
        )
        record = query.scalars().first()

        if record is None:
            # Settlement arrived with no self-report at all -- the verified
            # preimage itself becomes the ground truth for this job.
            record = EventRecord(
                job_id=payload.job_id,
                provider_id=payload.provider_id,
                buyer_id=payload.buyer_id,
                reporter_id="facilitator:lightning-preimage",
                price_usdc=float(result.amount_sats) if result.amount_sats is not None else None,
                success=True,
                rail="lightning",
                settlement_proof=result.payment_hash,
                verification_status="preimage_verified",
            )
            session.add(record)
            await session.commit()
            await state_manager.apply_outcome(payload.provider_id, True)
            return SettlementWebhookResponse(status="recorded", verification_status="preimage_verified")

        record.settlement_proof = result.payment_hash

        if record.success:
            record.verification_status = "preimage_verified"
            await session.commit()
            return SettlementWebhookResponse(status="confirmed", verification_status="preimage_verified")

        # Self-report said the job failed, but we have cryptographic proof
        # payment settled -- flag it and apply the verified truth as a
        # corrective outcome, same pattern as the x402 dispute path.
        record.verification_status = "disputed"
        await session.commit()
        logger.warning(
            f"Settlement mismatch for job_id={payload.job_id} provider={payload.provider_id}: "
            f"self-reported success=False, Lightning preimage proves payment settled"
        )
        await state_manager.apply_outcome(payload.provider_id, success=True)
        return SettlementWebhookResponse(status="disputed", verification_status="disputed")
