"""
Merchant backend for the Buildathon demo -- a small seller of "GPU
inference credits" that AI buyer agents purchase from autonomously.

Represents the Track 1 scenario: a merchant that wants to be transactable
by AI buyers end to end, gated by TRACE so it doesn't get drained by a
coordinated Sybil ring. Every purchase attempt is scored by the real TRACE
API (api.main:app, run locally against an isolated DB by
local_trace/db_setup.py) before a Razorpay test-mode order is created.

Run standalone:
    uvicorn buildathon.merchant.app:app --port 8100

Normally launched by demo/demo_runner.py, which also starts the TRACE
server and drives the attack simulation against this app.
"""
import asyncio
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Dict, List, Literal, Optional, Tuple

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import catalog
from ..agent.web import router as agent_router
from .razorpay_client import MerchantRazorpayClient
from .reports import router as reports_router
from .trace_gate import GateResult, TraceGate
from .webhooks import CapturedPayment, captured_payments
from .webhooks import router as razorpay_webhooks_router

# Frontend dev server origins only -- this merchant API has no browser
# session/cookie auth to protect, so a permissive local-dev CORS list is
# not a security concern the way it would be on the core api/ (which
# already restricts its own CORS_ORIGINS for exactly that reason).
# Next.js's dev server default (frontend/README.md: localhost:3000) -- this
# was 5173 (Vite's default) left over from PRODUCT.md's earlier Vite
# decision, reversed before the frontend was ever scaffolded. A stale
# default here means a fresh checkout's frontend can't actually reach the
# merchant without someone noticing the CORS rejection and manually setting
# FRONTEND_ORIGINS -- found and fixed, not caught by any test because
# TestClient/ASGITransport calls never go through CORSMiddleware's origin
# check at all.
FRONTEND_ORIGINS = os.environ.get(
    "FRONTEND_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
).split(",")

logger = logging.getLogger("buildathon.merchant")

PRICE_PER_CREDIT_INR = float(os.environ.get("PRICE_PER_CREDIT_INR", "50"))

# Track 1's bar: "every money action explainable, bounded and gated." These
# two caps are the "bounded" half -- enforced independent of what TRACE
# scores, so a momentarily-high-trust agent still can't move unlimited
# money in one shot or in a burst. Both are single-process/in-memory, same
# documented scope as the idempotency cache below; production would back
# them with Redis or a DB table.
MAX_CREDITS_PER_PURCHASE = int(os.environ.get("MAX_CREDITS_PER_PURCHASE", "20"))
MAX_ROLLING_AMOUNT_INR_PER_AGENT = float(os.environ.get("MAX_ROLLING_AMOUNT_INR_PER_AGENT", "2000"))
VELOCITY_WINDOW_SECONDS = float(os.environ.get("VELOCITY_WINDOW_SECONDS", "300"))

# buyer_id for outcome reports the merchant makes about its own live
# purchases (see _report_outcome_best_effort). api/routers/events.py
# restricts buyer_id to the caller's own authenticated identity or one of
# its API key prefixes; local_trace/db_setup.py provisions the merchant's
# key under MERCHANT_KEY_PREFIX ("merchant_demo_key" by default), which
# this process can't derive from its raw API key, so it's passed in.
MERCHANT_BUYER_ID = os.environ.get("TRACE_MERCHANT_BUYER_ID", "merchant_demo_key")


def _enforce_from_env() -> bool:
    return os.environ.get("TRACE_ENFORCE", "true").strip().lower() not in ("0", "false", "no")


# Caller-level gate, separate from TRACE's per-agent trust gate. Before this,
# /buy-credits and /agents/{agent_id}/trust-check had no access control at
# all: anyone who could reach the process could create real Razorpay
# test-mode orders or claim any agent_id, and TRACE's score for that agent_id
# is exactly as trustworthy as the caller's claim to *be* that agent_id --
# which is to say, not verified at all. This closes the first half of that
# gap (who may call this API) but explicitly not the second (proving the
# caller genuinely is the agent_id in the request body -- that needs
# per-agent cryptographic identity, e.g. signed requests, which is a real
# design task, not a config flag, and is out of scope for this pass).
#
# Read from the environment per-request rather than cached at import time
# (same reason _enforce_from_env() is a function, not a module constant) so
# tests can toggle it via monkeypatch without reimporting the module. Empty/
# unset keeps the endpoint open -- the correct default for local dev and the
# existing test suite, but NOT what a real deployment or a recorded pitch
# demo should ship with; see .env.example and NOTES.md.
def _merchant_api_keys_from_env() -> set:
    raw = os.environ.get("BUILDATHON_MERCHANT_API_KEYS", "")
    return {k.strip() for k in raw.split(",") if k.strip()}


def _require_caller_auth(authorization: Optional[str] = Header(default=None)) -> Optional[str]:
    """Returns the caller's validated key (or None if the gate is off), so
    route handlers can pass it to _require_agent_scope below -- previously
    this only ever raised-or-passed with no return value used, since
    nothing needed to know *which* key it was."""
    valid_keys = _merchant_api_keys_from_env()
    if not valid_keys:
        return None
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token in Authorization header.")
    token = authorization[len("Bearer "):].strip()
    if token not in valid_keys:
        raise HTTPException(status_code=401, detail="Invalid merchant API key.")
    return token


# Narrows *which* agent_id(s) a given API key may act as -- on top of, not
# instead of, _require_caller_auth's who-may-call-at-all check. Still not
# the identity-binding fix NOTES.md #13 says is out of scope: this proves
# the caller holds a credential that was, out of band, configured to be
# allowed to claim a given agent_id. It does not cryptographically prove
# the caller *is* that agent_id -- that needs per-agent signed requests,
# which nothing here attempts. What it does do: a leaked or shared key can
# be configured to only ever transact as the agent_id(s) it was actually
# issued for, instead of any agent_id in the marketplace, which is a real
# (if partial) narrowing of the blast radius of exactly the gap #13 named.
#
# Format: "key1=agent_a,agent_b;key2=agent_c". A key with no entry here is
# unscoped (may act as any agent_id) -- same open-by-default posture as
# _merchant_api_keys_from_env itself, so existing keys/tests are unaffected
# unless this is explicitly configured.
def _merchant_api_key_scopes_from_env() -> Dict[str, set]:
    raw = os.environ.get("BUILDATHON_MERCHANT_API_KEY_AGENT_SCOPES", "")
    scopes: Dict[str, set] = {}
    for entry in raw.split(";"):
        entry = entry.strip()
        if not entry or "=" not in entry:
            continue
        key, agents = entry.split("=", 1)
        key = key.strip()
        agent_set = {a.strip() for a in agents.split(",") if a.strip()}
        if key and agent_set:
            scopes[key] = agent_set
    return scopes


def _require_agent_scope(caller_key: Optional[str], agent_id: str) -> None:
    if caller_key is None:  # auth gate itself is off -- nothing to scope
        return
    scopes = _merchant_api_key_scopes_from_env()
    allowed = scopes.get(caller_key)
    if allowed is not None and agent_id not in allowed:
        raise HTTPException(
            status_code=403,
            detail=f"This API key is not scoped to act as agent_id '{agent_id}'.",
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.gate = TraceGate(
        base_url=os.environ["TRACE_API_BASE_URL"],
        api_key=os.environ["TRACE_API_KEY"],
        enforce=_enforce_from_env(),
    )
    try:
        app.state.razorpay = MerchantRazorpayClient()
    except Exception as e:
        logger.warning(f"Razorpay client unavailable ({e}); orders will be simulated, not created.")
        app.state.razorpay = None

    # Idempotency cache (Gap 6): a caller-supplied idempotency_key replays
    # the exact prior response instead of re-scoring/re-charging/re-
    # reporting. Per-key lock so two concurrent identical requests can't
    # both slip past the cache check. In-memory only -- lost on restart;
    # see _report_outcome_best_effort for the DB-backed second line of
    # defense against that specific case.
    app.state.idempotency_cache: Dict[str, "PurchaseResponse"] = {}
    app.state.idempotency_locks: Dict[str, asyncio.Lock] = {}
    app.state.idempotency_lock_creation_lock = asyncio.Lock()

    # Velocity tracker for the rolling per-agent cap (Gap 1): list of
    # (monotonic_timestamp, amount_inr) per agent_id, pruned to the window
    # on each check. Only amounts that actually became a real order
    # (status == "order_created") are recorded -- a blocked or
    # gateway-failed attempt never moved money, so it shouldn't count
    # against future exposure. Guarded by a per-agent lock (below) so the
    # check-then-record isn't itself a race between two concurrent
    # purchases for the same agent.
    app.state.velocity_tracker: Dict[str, List[Tuple[float, float]]] = {}
    app.state.agent_locks: Dict[str, asyncio.Lock] = {}
    app.state.agent_lock_creation_lock = asyncio.Lock()

    yield
    await app.state.gate.close()


app = FastAPI(title="Buildathon Demo Merchant", lifespan=lifespan)
app.include_router(razorpay_webhooks_router)
app.include_router(reports_router)
app.include_router(agent_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class PurchaseRequest(BaseModel):
    agent_id: str
    credits: int = 1
    # Optional, caller-supplied. When set, a retried request with the same
    # key replays the original response instead of creating a second order
    # or double-reporting the outcome to TRACE.
    idempotency_key: Optional[str] = None
    # Optional catalog tier name (see GET /catalog). When set, this purchase
    # is *for* that tier: its credit count and price replace `credits` /
    # the flat per-credit rate entirely, and the tier's own min_trust_score
    # is enforced against the real score TRACE returns for that priced
    # amount. An unknown name is a 400, not a silent fallback.
    tier: Optional[str] = None
    # Opt-in real upsell/cross-sell decision (see catalog.py, NOTES.md #9).
    # Ignored if `tier` is set. When true and no `tier` is given, the
    # merchant may substitute a better-value catalog bundle for the
    # requested flat-rate purchase if the agent's live trust score
    # qualifies -- and if it does, that bundle's price is what actually
    # gets charged, not the original flat-rate amount. Off by default so
    # every existing caller's behavior (and every regression test written
    # before this existed) is unaffected.
    auto_upsell: bool = False


class PurchaseResponse(BaseModel):
    # "order_created": a Razorpay test-mode order was created (this is
    #   order *creation*, not payment *capture* -- no buyer has completed
    #   checkout at this point, so no money has actually moved yet).
    # "order_creation_failed": TRACE approved the purchase but the
    #   Razorpay-side order creation itself failed (bad credentials,
    #   network blip, etc.) -- a payment-gateway failure, not a signal
    #   about the agent, so it is never reported back to TRACE.
    # "blocked": TRACE denied the purchase; nothing was attempted.
    status: Literal["order_created", "order_creation_failed", "blocked"]
    agent_id: str
    amount_inr: float
    routing_decision: str
    would_allow: bool
    enforced: bool
    score: float
    flags: list
    explanation: str
    # Per-component breakdown behind `score` (lcb, default_risk, cost_norm,
    # trust_net, cap_match, sybil_risk, clique_penalty) -- passed through
    # from TRACE's real /v1/score response so a UI can show *why*, not just
    # *what*.
    components: dict = {}
    razorpay_order_id: str | None = None
    # Links this purchase's Razorpay receipt and (when reported) its
    # /v1/events job_id -- the same value is used for both.
    job_id: str
    latency_ms: float
    # Growth surface (see catalog.py): the best catalog tier this agent's
    # *current* score already qualifies for, and a hint about the next one
    # -- advisory only, always reflects the score this response carries,
    # independent of what actually got charged this purchase.
    unlocked_tier: Optional[str] = None
    next_tier_hint: Optional[dict] = None
    # What this specific purchase actually did, price-wise (see
    # PurchaseRequest.tier / .auto_upsell). requested_tier is set whenever
    # the caller asked for a named tier, whether or not it was granted;
    # applied_tier is set only when a tier's price is what was actually
    # charged (explicit and granted, or auto-upsold). upsell_applied is
    # true only for the auto_upsell case -- an explicit tier request that
    # succeeds is not "upsold," it's just what was asked for.
    requested_tier: Optional[str] = None
    applied_tier: Optional[str] = None
    upsell_applied: bool = False
    upsell_note: Optional[str] = None


class CatalogTierResponse(BaseModel):
    name: str
    credits: int
    price_inr: float
    price_per_credit_inr: float
    min_trust_score: float
    description: str


class CatalogResponse(BaseModel):
    tiers: List[CatalogTierResponse]


class RazorpayConfigResponse(BaseModel):
    # key_id is the public half of the credential pair -- Razorpay's own
    # Checkout.js integration guide has the browser hold this (only
    # key_secret is a secret). None when the merchant's Razorpay client
    # failed to initialize (see lifespan()'s try/except) -- a frontend
    # should treat that as "checkout isn't available," not retry-forever.
    key_id: Optional[str] = None
    enabled: bool = False


class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class VerifyPaymentResponse(BaseModel):
    verified: bool
    captured: bool
    razorpay_order_id: str
    razorpay_payment_id: str


async def _get_idempotency_lock(key: str) -> asyncio.Lock:
    async with app.state.idempotency_lock_creation_lock:
        lock = app.state.idempotency_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            app.state.idempotency_locks[key] = lock
        return lock


async def _get_agent_lock(agent_id: str) -> asyncio.Lock:
    async with app.state.agent_lock_creation_lock:
        lock = app.state.agent_locks.get(agent_id)
        if lock is None:
            lock = asyncio.Lock()
            app.state.agent_locks[agent_id] = lock
        return lock


def _velocity_window_total(agent_id: str) -> float:
    """Prunes the rolling window and returns this agent's total within it.
    Split out from _check_velocity_cap so the auto-upsell path (below) can
    ask "would this push the agent over?" for a candidate amount without
    raising -- an upgrade attempt that would blow the cap should fall back
    to the original, already-valid purchase, not turn a legal request into
    a 429."""
    now = time.monotonic()
    window_start = now - VELOCITY_WINDOW_SECONDS
    history = [(ts, amt) for ts, amt in app.state.velocity_tracker.get(agent_id, []) if ts >= window_start]
    app.state.velocity_tracker[agent_id] = history
    return sum(amt for _, amt in history)


def _check_velocity_cap(agent_id: str, amount_inr: float) -> None:
    """Raises 429 if this purchase would push the agent's rolling window
    total over the cap. Checked before gate.check() so a request that will
    fail on this cap never spends a /v1/score round-trip, and so the cap is
    structurally independent of the trust score, not folded into it."""
    current_total = _velocity_window_total(agent_id)
    if current_total + amount_inr > MAX_ROLLING_AMOUNT_INR_PER_AGENT:
        raise HTTPException(
            status_code=429,
            detail=(
                f"agent '{agent_id}' would exceed the rolling purchase cap of "
                f"Rs {MAX_ROLLING_AMOUNT_INR_PER_AGENT:.0f} per {VELOCITY_WINDOW_SECONDS:.0f}s "
                f"(Rs {current_total:.0f} already in window, this request adds Rs {amount_inr:.0f}) -- "
                "independent of trust score."
            ),
        )


def _record_velocity(agent_id: str, amount_inr: float) -> None:
    app.state.velocity_tracker.setdefault(agent_id, []).append((time.monotonic(), amount_inr))


async def _report_outcome_best_effort(gate: TraceGate, agent_id: str, job_id: str, amount_inr: float) -> None:
    try:
        await gate.report_outcome(
            agent_id=agent_id,
            buyer_id=MERCHANT_BUYER_ID,
            job_id=job_id,
            success=True,
            capability="buy_credits",
            price_inr=amount_inr,
        )
    except httpx.HTTPStatusError as e:
        if e.response is not None and e.response.status_code == 409:
            # Already reported. This happens if the merchant process
            # restarted and lost its in-memory idempotency cache, then saw
            # the same idempotency_key (-> same job_id) again -- TRACE's own
            # EventRecord.job_id uniqueness is the second line of defense,
            # and a duplicate report here is a no-op, not a failure.
            logger.info(f"Outcome for job_id={job_id} already reported (409) -- treating as no-op.")
        else:
            raise


async def _process_purchase(
    req: PurchaseRequest,
    credits: int,
    amount_inr: float,
    requested_tier: Optional[catalog.CatalogTier],
) -> PurchaseResponse:
    # Per-agent lock spans the velocity check through the eventual record
    # (Gap 1) -- without it, two truly concurrent purchases for the same
    # agent (different idempotency keys, or none at all) could both read
    # the rolling total before either records theirs, each individually
    # passing the cap while jointly exceeding it. This does not serialize
    # unrelated agents' purchases against each other, only repeat purchases
    # by the same agent_id.
    agent_lock = await _get_agent_lock(req.agent_id)
    async with agent_lock:
        # Checked against the *initial* amount (flat-rate ask, or the
        # explicit tier's price) before spending a /v1/score round-trip --
        # same optimization as before. An auto-upsell that later raises the
        # amount gets its own, non-raising check below, since a courtesy
        # upgrade attempt must never be the reason a request that would
        # otherwise have succeeded gets rejected.
        _check_velocity_cap(req.agent_id, amount_inr)

        job_id = req.idempotency_key or f"buy-{req.agent_id}-{uuid.uuid4().hex[:8]}"

        gate: TraceGate = app.state.gate
        result: GateResult = await gate.check(req.agent_id, "buy_credits", amount_inr)

        applied_tier: Optional[catalog.CatalogTier] = None
        upsell_applied = False
        upsell_note: Optional[str] = None
        final_credits, final_amount_inr, final_result = credits, amount_inr, result

        if requested_tier is not None:
            # Explicit tier purchase: the catalog's own min_trust_score is
            # enforced as an extra, merchant-side gate on top of TRACE's
            # routing decision -- same "bounded, not just gated" principle
            # as the credit/velocity caps, scoped to this one tier's
            # advertised requirement rather than a flat ceiling. Checked
            # against the score TRACE actually returned for *this* priced
            # amount, not some earlier/cheaper quote.
            if result.score >= requested_tier.min_trust_score:
                applied_tier = requested_tier
            # else: applied_tier stays None -- `tier_gate_ok` below turns
            # that into a blocked status with an explanation, even if
            # TRACE's own routing_decision would otherwise have allowed it.
        elif req.auto_upsell:
            candidate = catalog.best_unlocked_tier(result.score)
            if (
                candidate is not None
                and candidate.credits > credits
                and candidate.credits <= MAX_CREDITS_PER_PURCHASE
                and candidate.price_per_credit_inr < PRICE_PER_CREDIT_INR
                and _velocity_window_total(req.agent_id) + candidate.price_inr <= MAX_ROLLING_AMOUNT_INR_PER_AGENT
            ):
                # Re-score at the amount this upgrade would actually
                # charge -- price feeds TRACE's own cost_norm term, so the
                # score that qualified the agent for `candidate` at the
                # original (cheaper) amount is not necessarily the score
                # at the upgraded one. The upgraded amount is what would
                # really be charged, so it's what has to be scored and
                # gated for real -- the same "charge only what was
                # actually scored" invariant every other purchase here
                # follows.
                upgraded_result: GateResult = await gate.check(req.agent_id, "buy_credits", candidate.price_inr)
                if upgraded_result.allowed and upgraded_result.score >= candidate.min_trust_score:
                    final_credits = candidate.credits
                    final_amount_inr = candidate.price_inr
                    final_result = upgraded_result
                    applied_tier = candidate
                    upsell_applied = True
                    upsell_note = (
                        f"Auto-upgraded from {credits} credit(s) at the flat rate "
                        f"(Rs {PRICE_PER_CREDIT_INR:.2f}/credit) to the {candidate.name} "
                        f"{candidate.credits}-credit bundle (Rs {candidate.price_per_credit_inr:.2f}/credit, "
                        f"Rs {candidate.price_inr:.2f} total) based on a trust score of {result.score:.2f}."
                    )
                # else: the upgrade attempt itself didn't clear TRACE's
                # gate or the tier's own threshold at the higher price --
                # fall through with final_* still pointing at the original,
                # already-valid baseline purchase. An optional courtesy
                # upgrade must never sink a purchase that would otherwise
                # have gone through.

        result = final_result
        credits, amount_inr = final_credits, final_amount_inr
        tier_gate_ok = requested_tier is None or applied_tier is not None

        order_id = None
        status: Literal["order_created", "order_creation_failed", "blocked"] = "blocked"
        if result.allowed and tier_gate_ok:
            status = "order_created"
            if app.state.razorpay is not None:
                try:
                    order = app.state.razorpay.create_order(
                        amount_inr_rupees=amount_inr,
                        receipt=job_id,
                        notes={"agent_id": req.agent_id, "credits": str(credits)},
                    )
                    order_id = order["id"]
                except Exception as e:
                    # TRACE's decision stands regardless of the payment
                    # gateway's availability -- a Razorpay-side failure (bad
                    # credentials, network blip, etc.) shouldn't take the
                    # merchant down or mask an otherwise-correct trust
                    # decision.
                    logger.error(f"Razorpay order creation failed for {req.agent_id}: {e}")
                    status = "order_creation_failed"

        if status == "order_created":
            _record_velocity(req.agent_id, amount_inr)

            # Close the loop: report this purchase's outcome back to TRACE
            # so real activity feeds future trust decisions, the same way
            # the synthetic seeder's history does. Gated on would_allow
            # (the genuine trust judgment), NOT on `allowed` or the enforce
            # flag -- in naive mode (enforce=False) `allowed` is always
            # True even for a Sybil/defector agent TRACE actually denied,
            # and reporting a fabricated success for them would corrupt
            # that agent's own future history before a later "protected"
            # comparison ever runs. Gating on would_allow also happens to
            # be exactly correct for real (non-demo) use, since
            # TRACE_ENFORCE=true means would_allow == allowed always.
            if result.would_allow:
                await _report_outcome_best_effort(gate, req.agent_id, job_id, amount_inr)

    best_tier = catalog.best_unlocked_tier(result.score)

    explanation = result.explanation
    flags = list(result.flags)
    if requested_tier is not None and applied_tier is None:
        explanation = (
            f"{explanation} Requested the '{requested_tier.name}' tier, which requires a trust "
            f"score >= {requested_tier.min_trust_score:.2f} (current: {result.score:.2f})."
        )
        flags.append("TIER_MIN_SCORE_NOT_MET")

    return PurchaseResponse(
        status=status,
        agent_id=req.agent_id,
        amount_inr=amount_inr,
        routing_decision=result.routing_decision,
        would_allow=result.would_allow,
        enforced=result.enforced,
        score=result.score,
        flags=flags,
        explanation=explanation,
        components=result.components,
        razorpay_order_id=order_id,
        job_id=job_id,
        latency_ms=result.latency_ms,
        unlocked_tier=best_tier.name if best_tier else None,
        next_tier_hint=catalog.next_tier_hint(result.score),
        requested_tier=requested_tier.name if requested_tier else None,
        applied_tier=applied_tier.name if applied_tier else None,
        upsell_applied=upsell_applied,
        upsell_note=upsell_note,
    )


def _resolve_initial_terms(req: PurchaseRequest) -> Tuple[int, float, Optional[catalog.CatalogTier]]:
    """What this purchase is *for*, before any score is known. An explicit
    tier is fully resolved here -- credits/amount come from the catalog,
    not from req.credits, and an unknown name is a 400. An auto_upsell
    request starts from the flat-rate terms the caller actually asked for;
    the possible upgrade is decided later in _process_purchase, once a real
    score exists to justify it."""
    if req.tier:
        tier = catalog.resolve_tier(req.tier)
        if tier is None:
            raise HTTPException(status_code=400, detail=f"Unknown catalog tier '{req.tier}'. See GET /catalog.")
        return tier.credits, tier.price_inr, tier
    return req.credits, req.credits * PRICE_PER_CREDIT_INR, None


@app.post("/buy-credits", response_model=PurchaseResponse)
async def buy_credits(req: PurchaseRequest, caller_key: Optional[str] = Depends(_require_caller_auth)) -> PurchaseResponse:
    _require_agent_scope(caller_key, req.agent_id)

    credits, amount_inr, requested_tier = _resolve_initial_terms(req)

    if credits <= 0:
        raise HTTPException(status_code=400, detail="credits must be positive")
    if credits > MAX_CREDITS_PER_PURCHASE:
        raise HTTPException(
            status_code=400,
            detail=(
                f"credits ({credits}) exceeds the per-purchase cap of "
                f"{MAX_CREDITS_PER_PURCHASE}, independent of trust score."
            ),
        )

    if not req.idempotency_key:
        return await _process_purchase(req, credits, amount_inr, requested_tier)

    lock = await _get_idempotency_lock(req.idempotency_key)
    async with lock:
        cached = app.state.idempotency_cache.get(req.idempotency_key)
        if cached is not None:
            return cached
        response = await _process_purchase(req, credits, amount_inr, requested_tier)
        # Only cache responses that actually reflect a TRACE decision. A cap
        # rejection (400/429) is client-side validation against a
        # time-varying rolling window, not a TRACE decision -- caching it
        # would permanently stick a legitimately-retryable request (e.g.
        # after the velocity window clears) replaying a stale rejection. Cap
        # rejections raise before this point, so nothing extra to exclude
        # here.
        app.state.idempotency_cache[req.idempotency_key] = response
        return response


class TrustCheckResponse(BaseModel):
    agent_id: str
    score: float
    routing_decision: str
    flags: list
    explanation: str
    components: dict = {}
    unlocked_tier: Optional[str] = None
    next_tier_hint: Optional[dict] = None


@app.get("/agents/{agent_id}/trust-check", response_model=TrustCheckResponse)
async def trust_check(agent_id: str, caller_key: Optional[str] = Depends(_require_caller_auth)) -> TrustCheckResponse:
    """Live score lookup with no side effects -- calls the same
    gate.check() /buy-credits uses, but never creates an order or reports
    an outcome. Lets the pricing page show a real tier-progress readout for
    any agent without requiring an actual purchase."""
    _require_agent_scope(caller_key, agent_id)
    gate: TraceGate = app.state.gate
    result = await gate.check(agent_id, "buy_credits", PRICE_PER_CREDIT_INR)
    best_tier = catalog.best_unlocked_tier(result.score)
    return TrustCheckResponse(
        agent_id=agent_id,
        score=result.score,
        routing_decision=result.routing_decision,
        flags=result.flags,
        explanation=result.explanation,
        components=result.components,
        unlocked_tier=best_tier.name if best_tier else None,
        next_tier_hint=catalog.next_tier_hint(result.score),
    )


@app.get("/catalog", response_model=CatalogResponse)
async def get_catalog() -> CatalogResponse:
    """Agent-readable catalog (Track 1 example direction). Static and
    unauthenticated -- an AI buyer agent can fetch this before ever calling
    /buy-credits to see what's purchasable and what trust score each tier
    requires, entirely machine-parseable JSON."""
    return CatalogResponse(
        tiers=[
            CatalogTierResponse(
                name=t.name,
                credits=t.credits,
                price_inr=t.price_inr,
                price_per_credit_inr=t.price_per_credit_inr,
                min_trust_score=t.min_trust_score,
                description=t.description,
            )
            for t in catalog.CATALOG
        ]
    )


@app.get("/razorpay-config", response_model=RazorpayConfigResponse)
async def razorpay_config() -> RazorpayConfigResponse:
    """What a frontend needs to open Razorpay Checkout.js after a
    /buy-credits order_created response: the public key_id. No auth --
    key_id is meant to be public (Razorpay's own integration docs put it
    directly in client-side JS); the amount/order_id it gets paired with
    always comes from a /buy-credits response TRACE already scored."""
    razorpay_client = app.state.razorpay
    if razorpay_client is None:
        return RazorpayConfigResponse(key_id=None, enabled=False)
    return RazorpayConfigResponse(key_id=razorpay_client.key_id, enabled=True)


@app.post("/verify-payment", response_model=VerifyPaymentResponse)
async def verify_payment(req: VerifyPaymentRequest) -> VerifyPaymentResponse:
    """Called by the frontend from Razorpay Checkout.js's `handler`
    callback right after a buyer completes a test-mode payment. Verifies
    the signature server-side (see razorpay_client.verify_payment_signature's
    docstring for why, and how this relates to /webhooks/razorpay) before
    trusting it, then records the capture into the same `captured_payments`
    store the webhook writes to -- so GET /orders/{id}/capture-status
    reflects a payment the instant Checkout.js reports it, without needing
    a public ngrok URL for a local demo. An unverified signature is
    recorded as nothing: better an honest "not shown as captured" than a
    forged one."""
    razorpay_client = app.state.razorpay
    if razorpay_client is None:
        raise HTTPException(status_code=503, detail="Razorpay is not configured on this deployment.")

    verified = razorpay_client.verify_payment_signature(
        req.razorpay_order_id, req.razorpay_payment_id, req.razorpay_signature
    )
    if not verified:
        logger.warning(
            f"Razorpay payment signature verification FAILED for order {req.razorpay_order_id} "
            f"/ payment {req.razorpay_payment_id} -- not recorded as captured."
        )
        return VerifyPaymentResponse(
            verified=False,
            captured=False,
            razorpay_order_id=req.razorpay_order_id,
            razorpay_payment_id=req.razorpay_payment_id,
        )

    captured_payments[req.razorpay_order_id] = CapturedPayment(
        razorpay_order_id=req.razorpay_order_id,
        razorpay_payment_id=req.razorpay_payment_id,
        event="payment.captured",
        amount_paise=0,  # not known here; the webhook path fills this in when it runs
    )
    logger.info(
        f"Razorpay payment verified client-side: order {req.razorpay_order_id}, "
        f"payment {req.razorpay_payment_id}"
    )
    return VerifyPaymentResponse(
        verified=True,
        captured=True,
        razorpay_order_id=req.razorpay_order_id,
        razorpay_payment_id=req.razorpay_payment_id,
    )


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "enforce": _enforce_from_env(),
        "price_per_credit_inr": PRICE_PER_CREDIT_INR,
        "max_credits_per_purchase": MAX_CREDITS_PER_PURCHASE,
        "max_rolling_amount_inr_per_agent": MAX_ROLLING_AMOUNT_INR_PER_AGENT,
        "velocity_window_seconds": VELOCITY_WINDOW_SECONDS,
        # False on a fresh checkout / local dev -- see _require_caller_auth's
        # docstring. Surfaced here so this gap is visible at a glance rather
        # than only discoverable by reading source.
        "caller_auth_configured": bool(_merchant_api_keys_from_env()),
        # True only if at least one configured key is further narrowed to
        # specific agent_id(s) -- see _require_agent_scope's docstring for
        # exactly what this does and doesn't prove.
        "agent_scoped_keys_configured": bool(_merchant_api_key_scopes_from_env()),
    }
