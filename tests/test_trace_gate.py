"""
Unit tests for the merchant's TRACE gate decision logic. No network calls --
httpx.MockTransport stands in for the TRACE API.

Run from the Trace-API repo root:
    pytest buildathon/tests/test_trace_gate.py -v
"""
import httpx
import pytest

from buildathon.merchant.trace_gate import TraceGate


def _gate_with_response(enforce: bool, routing_decision: str, score: float = 0.5) -> TraceGate:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "routing_decision": routing_decision,
                "score": score,
                "flags": [],
                "explanation": "test",
                "components": {},
                "latency_ms": 1.0,
            },
        )

    gate = TraceGate(base_url="http://testserver", api_key="sk_test_fake", enforce=enforce)
    gate._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return gate


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", ["ROUTE", "ROUTE_WITH_CAUTION"])
async def test_allow_decisions_pass_when_enforced(decision):
    gate = _gate_with_response(enforce=True, routing_decision=decision)
    result = await gate.check("agent_x", "buy_credits", 100.0)
    assert result.allowed is True
    assert result.would_allow is True


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", ["HOLD", "DENY", "QUARANTINE", "REFER"])
async def test_non_allow_decisions_block_when_enforced(decision):
    gate = _gate_with_response(enforce=True, routing_decision=decision)
    result = await gate.check("agent_x", "buy_credits", 100.0)
    assert result.allowed is False
    assert result.would_allow is False


@pytest.mark.asyncio
async def test_naive_mode_allows_even_a_blocked_decision():
    """The whole point of the naive/protected comparison: enforce=False must
    never block, even though the underlying score is exactly the same."""
    gate = _gate_with_response(enforce=False, routing_decision="QUARANTINE")
    result = await gate.check("agent_sybil_0", "buy_credits", 100.0)
    assert result.would_allow is False  # the real decision is still visible
    assert result.allowed is True       # but naive mode doesn't act on it
