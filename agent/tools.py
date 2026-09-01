"""
HTTP tools the autonomous buyer agent (agent/buyer.py) is allowed to call.

Every tool is a thin wrapper over an endpoint buildathon/merchant/app.py
already exposes -- the agent gets no capability an ordinary HTTP caller
doesn't already have. There is deliberately no tool that scores an agent
directly or bypasses /buy-credits: the LLM decides *what to try to buy*,
TRACE and the merchant's caps decide *whether it is allowed*, and nothing
the model can call changes that split.

A non-2xx response from /buy-credits (a per-purchase cap 400, a rolling
velocity-limit 429, an auth 401) is returned as a structured dict, NOT
raised -- the whole point is that the agent sees the refusal and adapts,
the same way a real integrator's code would.
"""
from typing import Optional

import httpx


class MerchantTools:
    def __init__(self, base_url: str, api_key: Optional[str] = None, timeout: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        await self._client.aclose()

    async def get_catalog(self) -> dict:
        r = await self._client.get(f"{self.base_url}/catalog", headers=self._headers)
        r.raise_for_status()
        return r.json()

    async def check_trust(self, agent_id: str) -> dict:
        r = await self._client.get(
            f"{self.base_url}/agents/{agent_id}/trust-check", headers=self._headers
        )
        r.raise_for_status()
        return r.json()

    async def buy_credits(
        self,
        agent_id: str,
        credits: int = 1,
        tier: Optional[str] = None,
        auto_upsell: bool = False,
        idempotency_key: Optional[str] = None,
    ) -> dict:
        body: dict = {"agent_id": agent_id, "credits": credits, "auto_upsell": auto_upsell}
        if tier:
            body["tier"] = tier
        if idempotency_key:
            body["idempotency_key"] = idempotency_key
        r = await self._client.post(
            f"{self.base_url}/buy-credits", json=body, headers=self._headers
        )
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail", "")
            except Exception:  # noqa: BLE001 -- body may not be JSON on some errors
                detail = r.text[:300]
            return {
                "error": True,
                "status_code": r.status_code,
                "detail": detail,
                "hint": _error_hint(r.status_code),
            }
        return r.json()

    async def get_capture_status(self, razorpay_order_id: str) -> dict:
        r = await self._client.get(
            f"{self.base_url}/orders/{razorpay_order_id}/capture-status", headers=self._headers
        )
        r.raise_for_status()
        return r.json()


def _error_hint(status_code: int) -> str:
    if status_code == 400:
        return (
            "Rejected before scoring -- usually the per-purchase credit cap or an "
            "unknown tier. A smaller purchase, or a smaller tier, may go through."
        )
    if status_code == 429:
        return (
            "The rolling per-agent spend cap was hit. Waiting it out is not an "
            "option in this session -- treat the remaining budget as spent, "
            "summarize, and stop."
        )
    if status_code == 401:
        return "The merchant API key is missing or wrong. Not recoverable from here."
    return "Unexpected error from the merchant API."
