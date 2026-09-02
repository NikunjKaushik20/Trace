"""
ASGI-level tests for buildathon/merchant/app.py's /buy-credits endpoint.
Previously only TraceGate and MerchantRazorpayClient were unit-tested in
isolation (test_trace_gate.py, test_razorpay_client.py); nothing exercised
the actual FastAPI route -- the bounded caps, the honest status vocabulary,
idempotency, and the would_allow-gated outcome-reporting loop.

httpx.ASGITransport does not trigger FastAPI's lifespan (confirmed against
the root repo's tests/test_api.py, which relies on the same fact), so
app.state.gate/app.state.razorpay -- and the state lifespan() would normally
set up (idempotency cache, velocity tracker) -- are set directly to
lightweight fakes here. No real env vars, network, or Razorpay/TRACE
processes needed.

Run from the Trace-API repo root:
    pytest buildathon/tests/test_merchant_app.py -v
"""
import asyncio
import time
from typing import Dict, List, Optional

import httpx
import pytest

from buildathon.merchant.app import (
    app,
    MAX_CREDITS_PER_PURCHASE,
    MAX_ROLLING_AMOUNT_INR_PER_AGENT,
    MERCHANT_BUYER_ID,
    PRICE_PER_CREDIT_INR,
)
from buildathon.merchant.trace_gate import GateResult
from buildathon.merchant.webhooks import captured_payments


class FakeGate:
    def __init__(self, would_allow=True, allowed=True, enforced=True,
                 routing_decision="ROUTE", score=0.8, flags=None, explanation="ok",
                 score_overrides: Optional[Dict[float, dict]] = None):
        self.would_allow = would_allow
        self.allowed = allowed
        self.enforced = enforced
        self.routing_decision = routing_decision
        self.score = score
        self.flags = flags or []
        self.explanation = explanation
        # Keyed by price_inr -- lets a test give a *second* gate.check() call
        # (e.g. the auto-upsell re-score at a bundle's price) a different
        # result than the first, without needing a stateful fake. Empty by
        # default, so every pre-existing test (all single-call, fixed
        # score/decision) is unaffected.
        self.score_overrides = score_overrides or {}
        self.check_calls: List[tuple] = []
        self.report_calls: List[dict] = []

    async def check(self, agent_id, capability, price_inr) -> GateResult:
        self.check_calls.append((agent_id, capability, price_inr))
        o = self.score_overrides.get(price_inr, {})
        return GateResult(
            allowed=o.get("allowed", self.allowed),
            would_allow=o.get("would_allow", self.would_allow),
            routing_decision=o.get("routing_decision", self.routing_decision),
            score=o.get("score", self.score),
            flags=o.get("flags", self.flags),
            explanation=o.get("explanation", self.explanation),
            components={},
            latency_ms=1.0,
            enforced=o.get("enforced", self.enforced),
        )

    async def report_outcome(self, **kwargs) -> None:
        self.report_calls.append(kwargs)


class FakeRazorpay:
    def __init__(self, fail: bool = False, key_id: str = "rzp_test_fake123", verify_result: bool = True):
        self.fail = fail
        self.key_id = key_id
        self.verify_result = verify_result
        self.create_calls: List[dict] = []
        self.verify_calls: List[tuple] = []

    def create_order(self, amount_inr_rupees: float, receipt: str, notes: dict) -> dict:
        self.create_calls.append({"amount_inr_rupees": amount_inr_rupees, "receipt": receipt, "notes": notes})
        if self.fail:
            raise RuntimeError("simulated Razorpay failure")
        return {"id": f"order_test_{receipt}"}

    def verify_payment_signature(self, razorpay_order_id, razorpay_payment_id, razorpay_signature) -> bool:
        self.verify_calls.append((razorpay_order_id, razorpay_payment_id, razorpay_signature))
        return self.verify_result


@pytest.fixture(autouse=True)
def _reset_app_state():
    """lifespan() normally sets these up; ASGITransport skips lifespan, and
    they're mutable module-level state on a singleton FastAPI app, so every
    test needs a clean slate."""
    app.state.idempotency_cache = {}
    app.state.idempotency_locks = {}
    app.state.idempotency_lock_creation_lock = asyncio.Lock()
    app.state.velocity_tracker = {}
    app.state.agent_locks = {}
    app.state.agent_lock_creation_lock = asyncio.Lock()
    captured_payments.clear()
    yield


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_order_created_status_and_job_id_matches_receipt():
    gate = FakeGate(would_allow=True, allowed=True)
    razorpay = FakeRazorpay()
    app.state.gate = gate
    app.state.razorpay = razorpay

    async with _client() as c:
        resp = await c.post("/buy-credits", json={"agent_id": "agent_honest", "credits": 2})

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "order_created"
    assert body["status"] not in ("captured", "captured_no_order")  # old, dishonest vocabulary
    assert body["razorpay_order_id"] == f"order_test_{body['job_id']}"
    assert razorpay.create_calls[0]["receipt"] == body["job_id"]


@pytest.mark.asyncio
async def test_blocked_purchase_never_creates_order_or_reports():
    gate = FakeGate(would_allow=False, allowed=False, routing_decision="QUARANTINE")
    razorpay = FakeRazorpay()
    app.state.gate = gate
    app.state.razorpay = razorpay

    async with _client() as c:
        resp = await c.post("/buy-credits", json={"agent_id": "agent_sybil", "credits": 2})

    body = resp.json()
    assert body["status"] == "blocked"
    assert body["razorpay_order_id"] is None
    assert razorpay.create_calls == []
    assert gate.report_calls == []


@pytest.mark.asyncio
async def test_order_creation_failure_does_not_report_outcome():
    """TRACE approved (would_allow=True), but Razorpay itself failed -- a
    gateway failure isn't a signal about the agent, so it must never be
    reported as a false negative against them."""
    gate = FakeGate(would_allow=True, allowed=True)
    razorpay = FakeRazorpay(fail=True)
    app.state.gate = gate
    app.state.razorpay = razorpay

    async with _client() as c:
        resp = await c.post("/buy-credits", json={"agent_id": "agent_honest", "credits": 2})

    body = resp.json()
    assert body["status"] == "order_creation_failed"
    assert gate.report_calls == []


@pytest.mark.asyncio
async def test_naive_mode_bypass_does_not_report_outcome():
    """allowed=True but would_allow=False is exactly TraceGate's naive-mode
    bypass (enforce=False lets a purchase through TRACE actually denied).
    Regression test for the double-counting hazard: if the merchant reported
    this as a genuine success, a fraud agent's naive-pass purchase would
    corrupt that agent's own history before a later protected-pass
    comparison ever runs."""
    gate = FakeGate(would_allow=False, allowed=True, enforced=False, routing_decision="QUARANTINE")
    razorpay = FakeRazorpay()
    app.state.gate = gate
    app.state.razorpay = razorpay

    async with _client() as c:
        resp = await c.post("/buy-credits", json={"agent_id": "agent_sybil", "credits": 2})

    body = resp.json()
    assert body["status"] == "order_created"  # naive mode: order still created
    assert razorpay.create_calls  # order really was created
    assert gate.report_calls == []  # but never reported as a genuine outcome


@pytest.mark.asyncio
async def test_report_outcome_uses_merchant_identity_and_matching_job_id():
    gate = FakeGate(would_allow=True, allowed=True)
    razorpay = FakeRazorpay()
    app.state.gate = gate
    app.state.razorpay = razorpay

    async with _client() as c:
        resp = await c.post("/buy-credits", json={"agent_id": "agent_honest", "credits": 1})

    body = resp.json()
    assert len(gate.report_calls) == 1
    call = gate.report_calls[0]
    assert call["agent_id"] == "agent_honest"
    assert call["job_id"] == body["job_id"]
    assert call["success"] is True
    assert call["buyer_id"] == MERCHANT_BUYER_ID


@pytest.mark.asyncio
async def test_catalog_is_public_and_agent_readable():
    async with _client() as c:
        resp = await c.get("/catalog")

    assert resp.status_code == 200
    body = resp.json()
    names = [t["name"] for t in body["tiers"]]
    assert "Starter" in names
    for tier in body["tiers"]:
        assert tier["price_per_credit_inr"] == pytest.approx(tier["price_inr"] / tier["credits"])


@pytest.mark.asyncio
async def test_purchase_response_reports_unlocked_tier():
    """A near-perfect score should unlock the top catalog tier -- purely
    advisory, must not change amount_inr for the current purchase."""
    gate = FakeGate(would_allow=True, allowed=True, routing_decision="ROUTE", score=0.99)
    app.state.gate = gate
    app.state.razorpay = FakeRazorpay()

    async with _client() as c:
        resp = await c.post("/buy-credits", json={"agent_id": "agent_high_trust", "credits": 1})

    body = resp.json()
    assert body["unlocked_tier"] == "Pro"
    assert body["next_tier_hint"] is None
    assert body["amount_inr"] == PRICE_PER_CREDIT_INR * 1  # unaffected by the tier hint


@pytest.mark.asyncio
async def test_purchase_response_reports_next_tier_hint_for_cold_start():
    gate = FakeGate(would_allow=True, allowed=True, routing_decision="HOLD", score=0.0)
    app.state.gate = gate
    app.state.razorpay = FakeRazorpay()

    async with _client() as c:
        resp = await c.post("/buy-credits", json={"agent_id": "agent_new", "credits": 1})

    body = resp.json()
    assert body["unlocked_tier"] == "Starter"
    assert body["next_tier_hint"]["tier"] == "Plus"


@pytest.mark.asyncio
async def test_rejects_non_positive_credits():
    app.state.gate = FakeGate()
    app.state.razorpay = FakeRazorpay()

    async with _client() as c:
        resp = await c.post("/buy-credits", json={"agent_id": "agent_x", "credits": 0})

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_bounded_cap_rejects_regardless_of_score():
    """Track 1's bar: 'bounded', independent of trust score. A near-perfect
    score must not bypass the hard per-transaction ceiling."""
    gate = FakeGate(would_allow=True, allowed=True, routing_decision="ROUTE", score=0.95)
    app.state.gate = gate
    app.state.razorpay = FakeRazorpay()

    async with _client() as c:
        resp = await c.post("/buy-credits", json={
            "agent_id": "agent_high_trust",
            "credits": MAX_CREDITS_PER_PURCHASE + 1,
        })

    assert resp.status_code == 400
    assert gate.check_calls == []  # cap enforced before spending a /v1/score round trip


@pytest.mark.asyncio
async def test_velocity_cap_blocks_regardless_of_score():
    """Same 'bounded' requirement, rolling-window form: even split across
    several individually-legal purchases, a high-trust agent still can't
    exceed the per-agent velocity cap."""
    gate = FakeGate(would_allow=True, allowed=True, routing_decision="ROUTE", score=0.95)
    app.state.gate = gate
    app.state.razorpay = FakeRazorpay()

    per_purchase_amount = MAX_CREDITS_PER_PURCHASE * PRICE_PER_CREDIT_INR
    assert per_purchase_amount <= MAX_ROLLING_AMOUNT_INR_PER_AGENT, \
        "test assumes at least one max-sized purchase fits under the rolling cap"

    agent_id = "agent_high_trust_velocity"
    async with _client() as c:
        total = 0.0
        while total + per_purchase_amount <= MAX_ROLLING_AMOUNT_INR_PER_AGENT:
            r = await c.post("/buy-credits", json={"agent_id": agent_id, "credits": MAX_CREDITS_PER_PURCHASE})
            assert r.status_code == 200
            total += per_purchase_amount

        # This one tips the same agent over the rolling cap.
        r_over = await c.post("/buy-credits", json={"agent_id": agent_id, "credits": MAX_CREDITS_PER_PURCHASE})

    assert r_over.status_code == 429


@pytest.mark.asyncio
async def test_velocity_cap_not_bypassed_by_concurrent_requests():
    """Regression test for a TOCTOU race: the velocity check-then-record
    used to not be atomic against itself, so concurrent purchases for the
    same agent (no shared idempotency_key) could each individually pass the
    check before any of them recorded, jointly exceeding the rolling cap."""
    gate = FakeGate(would_allow=True, allowed=True, routing_decision="ROUTE", score=0.95)
    app.state.gate = gate
    app.state.razorpay = FakeRazorpay()

    per_purchase_amount = MAX_CREDITS_PER_PURCHASE * PRICE_PER_CREDIT_INR
    n_concurrent = int(MAX_ROLLING_AMOUNT_INR_PER_AGENT // per_purchase_amount) + 2
    agent_id = "agent_race_test"

    async with _client() as c:
        responses = await asyncio.gather(*[
            c.post("/buy-credits", json={"agent_id": agent_id, "credits": MAX_CREDITS_PER_PURCHASE})
            for _ in range(n_concurrent)
        ])

    succeeded = [r for r in responses if r.status_code == 200]
    rejected = [r for r in responses if r.status_code == 429]
    assert len(succeeded) + len(rejected) == n_concurrent
    assert len(succeeded) * per_purchase_amount <= MAX_ROLLING_AMOUNT_INR_PER_AGENT
    assert len(rejected) > 0  # proves the cap was actually reached, not vacuously true


@pytest.mark.asyncio
async def test_idempotency_key_replays_response_without_double_charging():
    gate = FakeGate(would_allow=True, allowed=True)
    razorpay = FakeRazorpay()
    app.state.gate = gate
    app.state.razorpay = razorpay

    payload = {"agent_id": "agent_honest", "credits": 2, "idempotency_key": "idem-key-1"}
    async with _client() as c:
        r1 = await c.post("/buy-credits", json=payload)
        r2 = await c.post("/buy-credits", json=payload)

    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json() == r2.json()
    assert len(razorpay.create_calls) == 1
    assert len(gate.report_calls) == 1
    assert len(gate.check_calls) == 1


@pytest.mark.asyncio
async def test_buy_credits_open_when_no_api_keys_configured(monkeypatch):
    """Default posture (BUILDATHON_MERCHANT_API_KEYS unset): open, matching
    every other test in this file and local dev. Explicit regression test so
    a future change to the default can't silently lock out the rest of the
    suite without anyone noticing why."""
    monkeypatch.delenv("BUILDATHON_MERCHANT_API_KEYS", raising=False)
    app.state.gate = FakeGate(would_allow=True, allowed=True)
    app.state.razorpay = FakeRazorpay()

    async with _client() as c:
        resp = await c.post("/buy-credits", json={"agent_id": "agent_honest", "credits": 1})

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_buy_credits_rejects_missing_or_wrong_key_when_configured(monkeypatch):
    monkeypatch.setenv("BUILDATHON_MERCHANT_API_KEYS", "correct-key,another-valid-key")
    app.state.gate = FakeGate(would_allow=True, allowed=True)
    app.state.razorpay = FakeRazorpay()

    async with _client() as c:
        no_header = await c.post("/buy-credits", json={"agent_id": "agent_honest", "credits": 1})
        wrong_key = await c.post(
            "/buy-credits",
            json={"agent_id": "agent_honest", "credits": 1},
            headers={"Authorization": "Bearer not-a-valid-key"},
        )

    assert no_header.status_code == 401
    assert wrong_key.status_code == 401


@pytest.mark.asyncio
async def test_buy_credits_accepts_configured_key(monkeypatch):
    monkeypatch.setenv("BUILDATHON_MERCHANT_API_KEYS", "correct-key,another-valid-key")
    app.state.gate = FakeGate(would_allow=True, allowed=True)
    app.state.razorpay = FakeRazorpay()

    async with _client() as c:
        resp = await c.post(
            "/buy-credits",
            json={"agent_id": "agent_honest", "credits": 1},
            headers={"Authorization": "Bearer another-valid-key"},
        )

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_trust_check_also_gated_when_keys_configured(monkeypatch):
    """The caller-auth gate is meant to cover both money-adjacent endpoints,
    not just the one that spends -- an unauthenticated trust-check is still
    a free oracle over any claimed agent_id's score."""
    monkeypatch.setenv("BUILDATHON_MERCHANT_API_KEYS", "correct-key")
    app.state.gate = FakeGate(would_allow=True, allowed=True, score=0.5)

    async with _client() as c:
        no_key = await c.get("/agents/agent_honest/trust-check")
        with_key = await c.get(
            "/agents/agent_honest/trust-check", headers={"Authorization": "Bearer correct-key"}
        )

    assert no_key.status_code == 401
    assert with_key.status_code == 200


@pytest.mark.asyncio
async def test_catalog_stays_open_even_when_keys_configured(monkeypatch):
    """GET /catalog is deliberately unauthenticated -- an AI buyer agent
    needs to be able to read it before it has any credential at all. The
    caller-auth gate must not have been accidentally applied here too."""
    monkeypatch.setenv("BUILDATHON_MERCHANT_API_KEYS", "correct-key")

    async with _client() as c:
        resp = await c.get("/catalog")

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_explicit_tier_charges_tier_price_and_credits_not_flat_rate():
    """The real fix for NOTES.md #9: a tier's advertised price is now
    actually reachable through /buy-credits, not just displayed by
    /catalog."""
    gate = FakeGate(would_allow=True, allowed=True, score=0.5)  # >= Plus's 0.25
    app.state.gate = gate
    app.state.razorpay = FakeRazorpay()

    async with _client() as c:
        resp = await c.post("/buy-credits", json={"agent_id": "agent_plus", "tier": "Plus"})

    body = resp.json()
    assert resp.status_code == 200
    assert body["status"] == "order_created"
    assert body["amount_inr"] == pytest.approx(225.0)  # Plus's bundle price, not credits(1)*flat rate
    assert body["applied_tier"] == "Plus"
    assert body["requested_tier"] == "Plus"
    assert body["upsell_applied"] is False  # asked for directly, not auto-upsold
    assert gate.check_calls[0][2] == pytest.approx(225.0)  # scored at the real charged amount


@pytest.mark.asyncio
async def test_explicit_tier_blocked_when_score_below_tier_min_even_if_trace_would_route():
    """Catalog's own min_trust_score is enforced as an extra gate on top of
    TRACE's routing_decision, the same 'bounded, not just gated' principle
    as the credit/velocity caps -- a tier's advertised requirement has to
    mean something even when TRACE itself would have allowed the purchase
    at that price."""
    gate = FakeGate(would_allow=True, allowed=True, routing_decision="ROUTE", score=0.30)  # < Pro's 0.50
    app.state.gate = gate
    app.state.razorpay = FakeRazorpay()

    async with _client() as c:
        resp = await c.post("/buy-credits", json={"agent_id": "agent_low_trust", "tier": "Pro"})

    body = resp.json()
    assert body["status"] == "blocked"
    assert body["requested_tier"] == "Pro"
    assert body["applied_tier"] is None
    assert "TIER_MIN_SCORE_NOT_MET" in body["flags"]
    assert body["razorpay_order_id"] is None
    assert gate.report_calls == []


@pytest.mark.asyncio
async def test_unknown_tier_name_is_rejected():
    app.state.gate = FakeGate()
    app.state.razorpay = FakeRazorpay()

    async with _client() as c:
        resp = await c.post("/buy-credits", json={"agent_id": "agent_x", "tier": "Ultra"})

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_auto_upsell_upgrades_and_actually_changes_the_charge():
    """A real upsell/cross-sell decision: the merchant substitutes a
    better-value bundle for the requested flat-rate purchase, and that
    bundle's price is what actually gets charged -- not just a message."""
    gate = FakeGate(would_allow=True, allowed=True, routing_decision="ROUTE", score=0.6)  # unlocks Pro
    app.state.gate = gate
    app.state.razorpay = FakeRazorpay()

    async with _client() as c:
        resp = await c.post("/buy-credits", json={"agent_id": "agent_upsold", "credits": 1, "auto_upsell": True})

    body = resp.json()
    assert resp.status_code == 200
    assert body["status"] == "order_created"
    assert body["applied_tier"] == "Pro"
    assert body["requested_tier"] is None  # never explicitly asked for a tier
    assert body["upsell_applied"] is True
    assert body["amount_inr"] == pytest.approx(800.0)  # Pro's bundle price, not 1*flat rate
    assert body["upsell_note"] is not None
    # Re-scored at the real charged amount before the order was created --
    # not charged based on the first (cheaper) quote.
    assert gate.check_calls[-1][2] == pytest.approx(800.0)


@pytest.mark.asyncio
async def test_auto_upsell_does_nothing_when_no_better_tier_is_unlocked():
    """Regression guard: auto_upsell must not change behavior for an agent
    whose score doesn't clear anything beyond what was already requested."""
    gate = FakeGate(would_allow=True, allowed=True, routing_decision="HOLD", score=0.1)  # only Starter unlocked
    app.state.gate = gate
    app.state.razorpay = FakeRazorpay()

    async with _client() as c:
        resp = await c.post("/buy-credits", json={"agent_id": "agent_cold", "credits": 1, "auto_upsell": True})

    body = resp.json()
    assert body["upsell_applied"] is False
    assert body["applied_tier"] is None
    assert body["amount_inr"] == pytest.approx(PRICE_PER_CREDIT_INR * 1)
    assert len(gate.check_calls) == 1  # never spent a second round-trip on a non-upgrade


@pytest.mark.asyncio
async def test_auto_upsell_falls_back_when_the_upgrade_itself_fails_at_the_higher_price():
    """Price feeds TRACE's own cost_norm term, so a score that qualified an
    agent for a tier at a cheap quote isn't guaranteed to hold at the
    tier's real (higher) price. When the re-score at the upgrade's actual
    amount doesn't clear the tier's own bar, the courtesy upgrade must be
    discarded -- not allowed to sink a purchase that would otherwise have
    gone through at the original amount."""
    gate = FakeGate(
        would_allow=True, allowed=True, routing_decision="ROUTE", score=0.6,  # unlocks Pro at the cheap quote
        score_overrides={800.0: {"score": 0.3, "allowed": True}},  # but not at Pro's real price (min 0.50)
    )
    app.state.gate = gate
    app.state.razorpay = FakeRazorpay()

    async with _client() as c:
        resp = await c.post("/buy-credits", json={"agent_id": "agent_flaky_upgrade", "credits": 1, "auto_upsell": True})

    body = resp.json()
    assert resp.status_code == 200
    assert body["status"] == "order_created"  # the original, un-upgraded purchase still succeeds
    assert body["upsell_applied"] is False
    assert body["applied_tier"] is None
    assert body["amount_inr"] == pytest.approx(PRICE_PER_CREDIT_INR * 1)  # fell back to flat rate
    assert body["score"] == pytest.approx(0.6)  # reflects the baseline result, not the failed re-score
    assert len(gate.check_calls) == 2  # the re-score attempt really happened, it just didn't stick


@pytest.mark.asyncio
async def test_auto_upsell_never_pushes_the_agent_over_the_velocity_cap():
    """The upgrade's own incremental amount gets checked against the
    rolling cap before it's applied -- an optional courtesy upgrade must
    never be the reason a legal purchase turns into a 429."""
    gate = FakeGate(would_allow=True, allowed=True, routing_decision="ROUTE", score=0.6)  # unlocks Pro (Rs 800)
    app.state.gate = gate
    app.state.razorpay = FakeRazorpay()
    agent_id = "agent_near_cap"
    # Pre-fill the rolling window so the flat-rate ask (Rs 50) still fits
    # under the Rs 2000 cap, but Pro's bundle price (Rs 800) would not.
    app.state.velocity_tracker[agent_id] = [(time.monotonic(), 1300.0)]

    async with _client() as c:
        resp = await c.post("/buy-credits", json={"agent_id": agent_id, "credits": 1, "auto_upsell": True})

    body = resp.json()
    assert resp.status_code == 200
    assert body["status"] == "order_created"
    assert body["upsell_applied"] is False  # upgrade skipped, not attempted at a cap-busting amount
    assert body["amount_inr"] == pytest.approx(PRICE_PER_CREDIT_INR * 1)
    assert len(gate.check_calls) == 1  # never even spent the re-score round trip


@pytest.mark.asyncio
async def test_agent_scoped_key_rejects_a_different_agent_id(monkeypatch):
    monkeypatch.setenv("BUILDATHON_MERCHANT_API_KEYS", "scoped-key")
    monkeypatch.setenv("BUILDATHON_MERCHANT_API_KEY_AGENT_SCOPES", "scoped-key=agent_honest_0,agent_honest_1")
    app.state.gate = FakeGate(would_allow=True, allowed=True)
    app.state.razorpay = FakeRazorpay()

    async with _client() as c:
        resp = await c.post(
            "/buy-credits",
            json={"agent_id": "agent_defector_0", "credits": 1},
            headers={"Authorization": "Bearer scoped-key"},
        )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_agent_scoped_key_allows_its_own_agent_id(monkeypatch):
    monkeypatch.setenv("BUILDATHON_MERCHANT_API_KEYS", "scoped-key")
    monkeypatch.setenv("BUILDATHON_MERCHANT_API_KEY_AGENT_SCOPES", "scoped-key=agent_honest_0,agent_honest_1")
    app.state.gate = FakeGate(would_allow=True, allowed=True)
    app.state.razorpay = FakeRazorpay()

    async with _client() as c:
        resp = await c.post(
            "/buy-credits",
            json={"agent_id": "agent_honest_1", "credits": 1},
            headers={"Authorization": "Bearer scoped-key"},
        )

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_unscoped_key_can_still_act_as_any_agent_id(monkeypatch):
    """A key with no entry in BUILDATHON_MERCHANT_API_KEY_AGENT_SCOPES stays
    unscoped -- backward compatible with every key provisioned before this
    existed."""
    monkeypatch.setenv("BUILDATHON_MERCHANT_API_KEYS", "unscoped-key,scoped-key")
    monkeypatch.setenv("BUILDATHON_MERCHANT_API_KEY_AGENT_SCOPES", "scoped-key=agent_honest_0")
    app.state.gate = FakeGate(would_allow=True, allowed=True)
    app.state.razorpay = FakeRazorpay()

    async with _client() as c:
        resp = await c.post(
            "/buy-credits",
            json={"agent_id": "agent_anyone_at_all", "credits": 1},
            headers={"Authorization": "Bearer unscoped-key"},
        )

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_trust_check_also_enforces_agent_scope(monkeypatch):
    monkeypatch.setenv("BUILDATHON_MERCHANT_API_KEYS", "scoped-key")
    monkeypatch.setenv("BUILDATHON_MERCHANT_API_KEY_AGENT_SCOPES", "scoped-key=agent_honest_0")
    app.state.gate = FakeGate(would_allow=True, allowed=True, score=0.5)

    async with _client() as c:
        wrong_agent = await c.get(
            "/agents/agent_defector_0/trust-check", headers={"Authorization": "Bearer scoped-key"}
        )
        right_agent = await c.get(
            "/agents/agent_honest_0/trust-check", headers={"Authorization": "Bearer scoped-key"}
        )

    assert wrong_agent.status_code == 403
    assert right_agent.status_code == 200


@pytest.mark.asyncio
async def test_idempotency_does_not_cache_cap_rejections():
    """A cap rejection is time-varying client-side validation, not a TRACE
    decision -- replaying it forever under the same key would permanently
    stick a legitimately-retryable request once the rolling window clears."""
    gate = FakeGate(would_allow=True, allowed=True)
    app.state.gate = gate
    app.state.razorpay = FakeRazorpay()

    async with _client() as c:
        r1 = await c.post("/buy-credits", json={
            "agent_id": "agent_x", "credits": MAX_CREDITS_PER_PURCHASE + 1,
            "idempotency_key": "idem-key-2",
        })
        assert r1.status_code == 400

        r2 = await c.post("/buy-credits", json={
            "agent_id": "agent_x", "credits": 1,
            "idempotency_key": "idem-key-2",
        })

    assert r2.status_code == 200
    assert r2.json()["status"] == "order_created"


# ---------------------------------------------------------------------------
# GET /razorpay-config, POST /verify-payment -- the Razorpay Checkout.js
# integration (see razorpay_client.py's verify_payment_signature docstring).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_razorpay_config_exposes_public_key_when_configured():
    app.state.razorpay = FakeRazorpay(key_id="rzp_test_visible")

    async with _client() as c:
        resp = await c.get("/razorpay-config")

    assert resp.status_code == 200
    body = resp.json()
    assert body == {"key_id": "rzp_test_visible", "enabled": True}


@pytest.mark.asyncio
async def test_razorpay_config_reports_disabled_when_razorpay_unavailable():
    """Matches lifespan()'s degraded mode: app.state.razorpay is None when
    the client failed to initialize (missing/bad credentials)."""
    app.state.razorpay = None

    async with _client() as c:
        resp = await c.get("/razorpay-config")

    assert resp.status_code == 200
    assert resp.json() == {"key_id": None, "enabled": False}


@pytest.mark.asyncio
async def test_verify_payment_records_capture_on_valid_signature():
    razorpay = FakeRazorpay(verify_result=True)
    app.state.razorpay = razorpay

    async with _client() as c:
        resp = await c.post("/verify-payment", json={
            "razorpay_order_id": "order_abc",
            "razorpay_payment_id": "pay_abc",
            "razorpay_signature": "sig_abc",
        })

    assert resp.status_code == 200
    body = resp.json()
    assert body["verified"] is True
    assert body["captured"] is True
    assert razorpay.verify_calls == [("order_abc", "pay_abc", "sig_abc")]

    # And GET /orders/{id}/capture-status (webhooks.py) reflects it --
    # same store, so a frontend that already knows how to poll that
    # endpoint (for the webhook path) works unmodified for this one too.
    async with _client() as c:
        status_resp = await c.get("/orders/order_abc/capture-status")
    assert status_resp.json() == {
        "razorpay_order_id": "order_abc",
        "captured": True,
        "event": "payment.captured",
        "razorpay_payment_id": "pay_abc",
    }


@pytest.mark.asyncio
async def test_verify_payment_rejects_forged_signature_without_recording_capture():
    razorpay = FakeRazorpay(verify_result=False)
    app.state.razorpay = razorpay

    async with _client() as c:
        resp = await c.post("/verify-payment", json={
            "razorpay_order_id": "order_forged",
            "razorpay_payment_id": "pay_forged",
            "razorpay_signature": "not_actually_valid",
        })

    assert resp.status_code == 200
    body = resp.json()
    assert body["verified"] is False
    assert body["captured"] is False
    assert "order_forged" not in captured_payments


@pytest.mark.asyncio
async def test_verify_payment_503s_when_razorpay_unavailable():
    app.state.razorpay = None

    async with _client() as c:
        resp = await c.post("/verify-payment", json={
            "razorpay_order_id": "order_x",
            "razorpay_payment_id": "pay_x",
            "razorpay_signature": "sig_x",
        })

    assert resp.status_code == 503
