"""
Fires purchase attempts from the whole simulated population at the
merchant's /buy-credits endpoint, and collects the merchant's decision
for each one.
"""
from dataclasses import dataclass, asdict
from typing import List

import httpx

from .agents import Population


@dataclass
class AttemptResult:
    agent_id: str
    agent_class: str  # "honest" | "sybil" | "defector"
    status: str
    routing_decision: str
    would_allow: bool
    enforced: bool
    score: float
    flags: list
    explanation: str
    amount_inr: float
    razorpay_order_id: str | None
    job_id: str

    def as_dict(self) -> dict:
        return asdict(self)


async def run_purchase_attempts(merchant_base_url: str, population: Population) -> List[AttemptResult]:
    results: List[AttemptResult] = []
    async with httpx.AsyncClient(timeout=15.0) as client:
        for agent_id in population.honest_agent_ids:
            results.append(await _attempt(client, merchant_base_url, agent_id, "honest"))

        results.append(await _attempt(client, merchant_base_url, population.defector_agent_id, "defector"))

        for agent_id in population.sybil_agent_ids:
            results.append(await _attempt(client, merchant_base_url, agent_id, "sybil"))

    return results


async def _attempt(client: httpx.AsyncClient, base_url: str, agent_id: str, agent_class: str) -> AttemptResult:
    resp = await client.post(f"{base_url}/buy-credits", json={"agent_id": agent_id, "credits": 2})
    resp.raise_for_status()
    body = resp.json()
    return AttemptResult(
        agent_id=agent_id,
        agent_class=agent_class,
        status=body["status"],
        routing_decision=body["routing_decision"],
        would_allow=body["would_allow"],
        enforced=body["enforced"],
        score=body["score"],
        flags=body["flags"],
        explanation=body["explanation"],
        amount_inr=body["amount_inr"],
        razorpay_order_id=body.get("razorpay_order_id"),
        job_id=body["job_id"],
    )
