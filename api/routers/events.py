import logging
from fastapi import APIRouter, Depends, Request, HTTPException
from datetime import datetime
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError

from ..models import EventReport, EventReportResponse
from ..state import state_manager
from ..auth import verify_api_key_with_context, Developer
from ..rate_limit import limiter, RATE_LIMIT_EVENTS
from ..database import AsyncSessionLocal, EventRecord, get_db, UsageLog

logger = logging.getLogger("trace.api")

router = APIRouter()


@router.post("/events", response_model=EventReportResponse)
@limiter.limit(RATE_LIMIT_EVENTS)
async def report_event(
    request: Request, 
    event: EventReport, 
    auth_tuple: tuple = Depends(verify_api_key_with_context)
):
    dev, api_key = auth_tuple
    """
    Report a job outcome event.
    
    Validation:
    - job_id must be unique (atomic deduplication via UNIQUE constraint)
    - buyer_id must match the authenticated developer's ID (prevents spoofing)
    - Records event for audit trail
    """
    provider_id = event.provider_id
    buyer_id = event.buyer_id
    job_id = event.job_id
    success = event.success
    
    # Enforce buyer identity: the buyer_id must be the authenticated developer's ID
    # or one of their API key prefixes. This prevents trust graph poisoning by
    # spoofing events from other buyers.
    async with AsyncSessionLocal() as session:
        from ..database import APIKey
        result = await session.execute(
            select(APIKey).filter(APIKey.developer_id == dev.id, APIKey.is_active == True)
        )
        api_keys = result.scalars().all()
        key_prefixes = {k.key_prefix for k in api_keys}
        
        # Allow if buyer_id matches the developer's UUID or any of their key prefixes
        allowed_identities = {dev.id, dev.email} | key_prefixes
        buyer_matches = buyer_id in allowed_identities or any(
            buyer_id.startswith(prefix.replace("...", "")) for prefix in key_prefixes
        )
        if not buyer_matches:
            raise HTTPException(
                status_code=403,
                detail="buyer_id does not match your authenticated identity. You can only report events for your own transactions."
            )
    
    # Atomic event recording with deduplication via UNIQUE constraint on job_id
    # This eliminates the race condition from check-then-insert
    async with AsyncSessionLocal() as session:
        try:
            async with session.begin_nested():
                event_record = EventRecord(
                    job_id=job_id,
                    provider_id=provider_id,
                    buyer_id=buyer_id,
                    reporter_id=dev.email,
                    capability=event.capability,
                    price_usdc=event.price_usdc,
                    success=success,
                    rail=event.rail,
                )
                session.add(event_record)
        except IntegrityError:
            raise HTTPException(
                status_code=409,
                detail=f"Event for job_id '{job_id}' already reported"
            )
        
        await session.commit()
    
    # Add trust edge (buyer -> provider)
    await state_manager.add_trust_edge(buyer_id, provider_id)
    
    # Update provider history. Shared with the facilitator settlement
    # webhook path (api/routers/webhooks.py) via state_manager.apply_outcome
    # so both call sites update EMA/CUSUM state identically.
    await state_manager.apply_outcome(provider_id, success)
    
    # Log usage to DB
    async with AsyncSessionLocal() as session:
        usage_log = UsageLog(
            developer_id=dev.id,
            api_key_id=api_key.id,
            endpoint=request.url.path,
            provider_id=provider_id,
            routing_decision="EVENT_SUCCESS" if success else "EVENT_FAILED"
        )
        session.add(usage_log)
        await session.commit()
    
    return EventReportResponse(
        status="success",
        processed_at=datetime.utcnow().isoformat()
    )