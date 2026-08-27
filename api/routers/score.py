import logging
from fastapi import APIRouter, HTTPException, Depends, Request

from ..models import ScoringRequest, TraceScoreResponse, RoutingDecision, ScoringComponents
from ..scorer import compute_trace_score
from ..auth import verify_api_key_with_context, Developer
from ..metrics import record_score_request
from ..database import get_db, UsageLog
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("trace.api")

router = APIRouter()


@router.post("/score", response_model=TraceScoreResponse)
async def score_provider(
    request: Request, 
    scoring_req: ScoringRequest, 
    auth_tuple: tuple = Depends(verify_api_key_with_context),
    db: AsyncSession = Depends(get_db)
):
    dev, api_key = auth_tuple
    try:
        result = await compute_trace_score(
            provider_id=scoring_req.provider_id,
            job_capability=scoring_req.job.capability,
            price_usdc=scoring_req.job.price_usdc,
            cohort_median_price=scoring_req.cohort_median_price,
            provider_capabilities=scoring_req.provider_capabilities,
        )

        # Record metrics
        components_dict = {
            "lcb": result.components.lcb,
            "default_risk": result.components.default_risk,
            "cost_norm": result.components.cost_norm,
            "trust_net": result.components.trust_net,
            "cap_match": result.components.cap_match,
            "sybil_risk": result.components.sybil_risk,
            "clique_penalty": result.components.clique_penalty,
        }
        record_score_request(
            provider_id=scoring_req.provider_id,
            routing_decision=result.routing_decision,
            score=result.score,
            components=components_dict,
            latency=result.latency_ms / 1000.0,  # Convert to seconds
        )

        # Log usage to DB
        usage_log = UsageLog(
            developer_id=dev.id,
            api_key_id=api_key.id,
            endpoint=request.url.path,
            provider_id=scoring_req.provider_id,
            routing_decision=result.routing_decision,
            score=result.score,
            latency_ms=result.latency_ms,
            flags=",".join(result.flags)
        )
        db.add(usage_log)
        await db.commit()

        return TraceScoreResponse(
            provider_id=scoring_req.provider_id,
            score=result.score,
            routing_decision=RoutingDecision(result.routing_decision),
            components=ScoringComponents(
                lcb=result.components.lcb,
                default_risk=result.components.default_risk,
                cost_norm=result.components.cost_norm,
                trust_net=result.components.trust_net,
                cap_match=result.components.cap_match,
                sybil_risk=result.components.sybil_risk,
                clique_penalty=result.components.clique_penalty,
            ),
            refresh_hint=result.refresh_hint,
            evidence_source_count=result.evidence_source_count,
            anchor_commitment=result.anchor_commitment,
            flags=result.flags,
            explanation=result.explanation,
            latency_ms=result.latency_ms,
            version="1.0.0",
        )
    except Exception as e:
        logger.error(f"Score computation failed for provider {scoring_req.provider_id}: {e}", exc_info=True)
        # Fail-closed for the pilot: Return a safe HOLD decision instead of 500 error
        return TraceScoreResponse(
            provider_id=scoring_req.provider_id,
            score=0.0,
            routing_decision=RoutingDecision.HOLD,
            components=ScoringComponents(
                lcb=0.0, default_risk=0.0, cost_norm=0.0, trust_net=0.0, cap_match=0.0, sybil_risk=0.0, clique_penalty=0.0
            ),
            flags=["SYSTEM_FAILURE"],
            explanation="TRACE internal scoring failure. Safely failing closed to HOLD.",
            latency_ms=0.0,
            version="1.0.0"
        )
