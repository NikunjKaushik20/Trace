"""
TRACE trust gate for the Buildathon merchant demo.

Same idea as sdk/x402_middleware.py's TRACEMiddleware.check(), with two
differences:

1. It checks against TRACE's real routing_decision vocabulary --
   ROUTE / ROUTE_WITH_CAUTION / HOLD / DENY / QUARANTINE / REFER, per
   api/models.py's RoutingDecision enum and api/scorer.py's route()
   function -- not the ("HOLD", "INVESTIGATE") pair the SDK sample checks,
   which doesn't actually match anything route() returns.
2. It has an `enforce` toggle so the demo can run the identical scoring
   call in "naive" mode (score computed and logged, but never blocks the
   purchase) and "protected" mode (blocks on any non-allow decision) --
   that's how the before/after comparison is produced.
"""
import asyncio
from dataclasses import dataclass, field
from typing import Optional

import httpx

ALLOW_DECISIONS = {"ROUTE", "ROUTE_WITH_CAUTION"}

# api/rate_limit.py caps /v1/events at RATE_LIMIT_EVENTS (120/minute by
# default). Seeding a demo marketplace fires far more than that in a burst,
# so this is a real limit an integrator has to handle, not just a test
# artifact -- retry with a fixed backoff instead of raising.
MAX_RATE_LIMIT_RETRIES = 30
RATE_LIMIT_BACKOFF_S = 2.0


async def _post_with_retry(client: httpx.AsyncClient, url: str, **kwargs) -> httpx.Response:
    for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
        resp = await client.post(url, **kwargs)
        if resp.status_code != 429:
            resp.raise_for_status()
            return resp
        if attempt == MAX_RATE_LIMIT_RETRIES:
            resp.raise_for_status()
        await asyncio.sleep(RATE_LIMIT_BACKOFF_S)
    raise RuntimeError("unreachable")


@dataclass
class GateResult:
    allowed: bool
    would_allow: bool
    routing_decision: str
    score: float
    flags: list
    explanation: str
    components: dict
    latency_ms: float
    enforced: bool


class TraceGate:
    def __init__(self, base_url: str, api_key: str, enforce: bool = True, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.enforce = enforce
        self._client = httpx.AsyncClient(timeout=timeout)

    async def close(self):
        await self._client.aclose()

    async def check(self, agent_id: str, capability: str, price_inr: float) -> GateResult:
        resp = await _post_with_retry(
            self._client,
            f"{self.base_url}/v1/score",
            json={
                "provider_id": agent_id,
                "job": {"capability": capability, "price_usdc": price_inr},
            },
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        result = resp.json()

        decision = result["routing_decision"]
        would_allow = decision in ALLOW_DECISIONS
        allowed = would_allow if self.enforce else True

        return GateResult(
            allowed=allowed,
            would_allow=would_allow,
            routing_decision=decision,
            score=result["score"],
            flags=result.get("flags", []),
            explanation=result.get("explanation", ""),
            components=result.get("components", {}),
            latency_ms=result.get("latency_ms", 0.0),
            enforced=self.enforce,
        )

    async def report_outcome(
        self,
        agent_id: str,
        buyer_id: str,
        job_id: str,
        success: bool,
        capability: str = "buy_credits",
        price_inr: Optional[float] = None,
    ) -> None:
        await _post_with_retry(
            self._client,
            f"{self.base_url}/v1/events",
            json={
                "provider_id": agent_id,
                "buyer_id": buyer_id,
                "job_id": job_id,
                "capability": capability,
                "price_usdc": price_inr,
                "success": success,
            },
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
