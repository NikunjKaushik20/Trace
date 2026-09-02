"""
Tests for buildathon/merchant/reports.py's report-reading endpoints and
app.py's live trust-check endpoint.

Run from the Trace-API repo root:
    pytest buildathon/tests/test_reports.py -v
"""
import json

import httpx
import pytest

from buildathon.merchant.app import app
import buildathon.merchant.reports as reports_module
from buildathon.merchant.trace_gate import GateResult


class FakeGate:
    def __init__(self, score=0.6, routing_decision="ROUTE_WITH_CAUTION", flags=None):
        self.score = score
        self.routing_decision = routing_decision
        self.flags = flags or []
        self.check_calls = []

    async def check(self, agent_id, capability, price_inr):
        self.check_calls.append((agent_id, capability, price_inr))
        return GateResult(
            allowed=True, would_allow=True, routing_decision=self.routing_decision,
            score=self.score, flags=self.flags, explanation="test explanation",
            components={}, latency_ms=1.0, enforced=True,
        )

    async def report_outcome(self, **kwargs):
        raise AssertionError("trust-check must never report an outcome")


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_report_404_when_file_missing(monkeypatch, tmp_path):
    monkeypatch.setitem(reports_module.REPORT_FILES, "benchmark", tmp_path / "nope.json")
    async with _client() as c:
        resp = await c.get("/reports/benchmark")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_report_returns_real_file_contents(monkeypatch, tmp_path):
    fake_path = tmp_path / "benchmark_report.json"
    fake_path.write_text(json.dumps({"collusion_ring": {"fraud_reduction_vs_behavioral": "5%"}}))
    monkeypatch.setitem(reports_module.REPORT_FILES, "benchmark", fake_path)

    async with _client() as c:
        resp = await c.get("/reports/benchmark")

    body = resp.json()
    assert resp.status_code == 200
    assert "generated_at" in body
    assert body["data"]["collusion_ring"]["fraud_reduction_vs_behavioral"] == "5%"


@pytest.mark.asyncio
async def test_agent_directory_derives_from_naive_vs_protected_report(monkeypatch, tmp_path):
    fake_path = tmp_path / "audit_log.json"
    fake_path.write_text(json.dumps({
        "protected": {"attempts": [
            {"agent_id": "agent_honest_0", "agent_class": "honest", "score": 0.8,
             "routing_decision": "ROUTE", "flags": [], "status": "order_created", "amount_inr": 100.0},
            {"agent_id": "agent_sybil_0", "agent_class": "sybil", "score": 0.0,
             "routing_decision": "QUARANTINE", "flags": ["SYBIL_RISK_HIGH"], "status": "blocked", "amount_inr": 100.0},
        ]}
    }))
    monkeypatch.setitem(reports_module.REPORT_FILES, "naive-vs-protected", fake_path)

    async with _client() as c:
        resp = await c.get("/reports/agents")

    body = resp.json()
    assert len(body["agents"]) == 2
    assert body["agents"][1]["agent_id"] == "agent_sybil_0"
    assert body["agents"][1]["status"] == "blocked"


@pytest.mark.asyncio
async def test_trust_check_never_creates_order_or_reports_outcome():
    gate = FakeGate(score=0.42, routing_decision="ROUTE_WITH_CAUTION", flags=["COLD_START"])
    app.state.gate = gate

    async with _client() as c:
        resp = await c.get("/agents/agent_honest_0/trust-check")

    body = resp.json()
    assert resp.status_code == 200
    assert body["agent_id"] == "agent_honest_0"
    assert body["score"] == 0.42
    assert body["routing_decision"] == "ROUTE_WITH_CAUTION"
    assert "razorpay_order_id" not in body  # no order concept at all in this response
    assert len(gate.check_calls) == 1
