import logging
from fastapi import APIRouter, HTTPException, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import BatchScoringRequest, TraceScoreResponse, RoutingDecision, ScoringComponents
from ..scorer import compute_trace_score
from ..auth import verify_api_key_batch, Developer, API_CALL_COST
from ..database import get_db, BillingTransaction

logger = logging.getLogger("trace.api")

router = APIRouter()


@router.post("/score/batch", response_model=list[TraceScoreResponse])
async def score_batch(
    request: Request,
    batch_req: BatchScoringRequest,
    auth_tuple: tuple = Depends(verify_api_key_batch),
    db: AsyncSession = Depends(get_db),
):
    dev, api_key = auth_tuple
    provider_count = len(batch_req.providers)

    # Per-item billing: charge for each provider in the batch
    total_cost = API_CALL_COST * provider_count
    if dev.balance_usdc < total_cost and not api_key.is_test:
        raise HTTPException(
            status_code=402,
            detail=f"Insufficient balance. Batch of {provider_count} costs ${total_cost:.4f} USDC. Current balance: ${dev.balance_usdc:.4f}"
        )

    if not api_key.is_test:
        dev.balance_usdc -= total_cost
        txn = BillingTransaction(
            developer_id=dev.id,
            amount_usdc=-total_cost,
            balance_after=dev.balance_usdc,
            transaction_type="api_call",
            endpoint=f"/v1/score/batch ({provider_count} providers)",
        )
        db.add(txn)
        await db.commit()

    results = []
    for req in batch_req.providers:
        try:
            result = await compute_trace_score(
                provider_id=req.provider_id,
                job_capability=req.job.capability,
                price_usdc=req.job.price_usdc,
                cohort_median_price=req.cohort_median_price,
                provider_capabilities=req.provider_capabilities,
            )

            results.append(TraceScoreResponse(
                provider_id=req.provider_id,
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
                flags=result.flags,
                explanation=result.explanation,
                latency_ms=result.latency_ms,
                version="1.0.0",
            ))
        except Exception as e:
            logger.error(f"Batch score failed for provider {req.provider_id}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal scoring error")

    # Sort by score descending (routing recommendation)
    results.sort(key=lambda x: x.score, reverse=True)
    return results
