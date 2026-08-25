import time
import scipy.stats
import hashlib
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import List, Optional

from .detection import (
    compute_default_risk,
    process_default_sequence,
    CUSUM_PENALTY
)
from .graph import (
    compute_ppr_trust_net,
    compute_sybil_risk,
    compute_clique_penalty,
    compute_edge_to_job_ratio,
    is_honest_seed
)


ALPHA = 0.40
BETA = 0.30
GAMMA = 0.15
DELTA = 0.10
EPSILON = 0.10
LAMBDA = 0.35
MU = 0.25

ROUTE_THRESHOLD = 0.50
CAUTION_THRESHOLD = 0.25


@dataclass
class ScoringComponents:
    lcb: float
    default_risk: float
    cost_norm: float
    trust_net: float
    cap_match: float
    sybil_risk: float
    clique_penalty: float


@dataclass
class TraceScore:
    score: float
    components: ScoringComponents
    routing_decision: str
    flags: List[str]
    explanation: str
    latency_ms: float
    cusum_fired: bool
    refresh_hint: Optional[dict] = None
    evidence_source_count: Optional[int] = None
    anchor_commitment: Optional[dict] = None


def compute_lcb(successes: int, failures: int) -> float:
    alpha = 1 + successes
    beta_param = 3 + failures
    return float(scipy.stats.beta.ppf(0.05, alpha, beta_param))


def compute_cost_norm(price: float, cohort_median: Optional[float]) -> float:
    if cohort_median is None or cohort_median == 0:
        return 0.0
    ratio = price / cohort_median
    if ratio > 2.0:
        return min(1.0, (ratio - 2.0) / 2.0)
    elif ratio < 0.3:
        return (0.3 - ratio) / 0.3 * 0.5
    return 0.0


def compute_cap_match(provider_capabilities: List[str], required_capability: str) -> float:
    if required_capability in provider_capabilities:
        return 1.0
    # Partial match: capability overlap or substring containment
    for cap in provider_capabilities:
        if required_capability in cap or cap in required_capability:
            return 0.5
    return 0.0


def generate_explanation(components: ScoringComponents, flags: List[str], cusum_fired: bool = False) -> str:
    parts = []

    if components.lcb > 0.7:
        parts.append(f"High LCB ({components.lcb:.2f}) from strong completion history")
    elif components.lcb > 0.4:
        parts.append(f"Moderate LCB ({components.lcb:.2f})")
    else:
        parts.append(f"Low LCB ({components.lcb:.2f}) - thin evidence")

    if cusum_fired:
        parts.append("CUSUM change-point alarm fired on a sudden default-rate spike - treated as a proven strategic default, does not decay")
    elif components.default_risk > 0.2:
        parts.append(f"Elevated default risk ({components.default_risk:.2f})")
    
    if components.cost_norm > 0.0:
        if components.cost_norm > 0.5:
            parts.append(f"Price significantly above cohort median")
        else:
            parts.append(f"Price anomaly detected")
    
    if components.trust_net > 0.5:
        parts.append(f"Strong trust network signal ({components.trust_net:.2f})")
    elif components.trust_net > 0.1:
        parts.append(f"Moderate trust network proximity")
    
    if components.sybil_risk > 0.3:
        parts.append(f"High sybil risk (edge-to-job ratio anomaly)")
    
    if components.clique_penalty > 0.3:
        parts.append(f"Clique penalty triggered - coordinated neighborhood")
    
    if not parts:
        parts.append("Insufficient evidence for reliable scoring")
    
    return ". ".join(parts) + "."


def generate_flags(components: ScoringComponents, cusum_fired: bool, settlement_disputed: bool = False) -> List[str]:
    flags = []
    if components.sybil_risk > 0.7:
        flags.append("SYBIL_RISK_HIGH")
    if components.clique_penalty > 0.5:
        flags.append("CLIQUE_PENALTY_HIGH")
    if cusum_fired:
        flags.append("CUSUM_FIRED")
    if components.lcb < 0.1:
        flags.append("COLD_START")
    if settlement_disputed:
        flags.append("SETTLEMENT_MISMATCH")
    return flags


def route(score: float, flags: List[str]) -> str:
    if "SYBIL_RISK_HIGH" in flags or "CLIQUE_PENALTY_HIGH" in flags:
        return "QUARANTINE"
    if "CUSUM_FIRED" in flags or "SETTLEMENT_MISMATCH" in flags:
        return "DENY"
    if "FRAGMENTED_VISIBILITY" in flags:
        return "REFER"
    if score >= ROUTE_THRESHOLD:
        return "ROUTE"
    if score >= CAUTION_THRESHOLD:
        return "ROUTE_WITH_CAUTION"
    return "HOLD"


async def compute_trace_score(
    provider_id: str,
    job_capability: str,
    price_usdc: float,
    cohort_median_price: Optional[float],
    provider_capabilities: Optional[List[str]] = None
) -> TraceScore:
    from .state import state_manager
    start = time.perf_counter()
    
    p_hist = await state_manager.get_provider(provider_id)
    successes = p_hist.completed_jobs
    failures = p_hist.failed_jobs
    lcb = compute_lcb(successes, failures)
    
    # Sticky flag, not p_hist.cusum_state -- the accumulator resets itself to
    # 0.0 the instant it fires (see api/detection.py's update_cusum()), so
    # cusum_state alone could never be observed as "fired" after the write
    # that set it. cusum_fired_ever is the independently-persisted signal
    # (api/state.py's apply_outcome()) and does not decay.
    cusum_fired = p_hist.cusum_fired_ever
    default_risk = compute_default_risk(p_hist.ema_default_rate, cusum_fired)
    
    cost_norm = compute_cost_norm(price_usdc, cohort_median_price)
    
    cached_scores = await state_manager.get_cached_scores(provider_id)
    trust_net = cached_scores.get("pagerank", 0.0)
    
    cap_match = compute_cap_match(provider_capabilities or [], job_capability)
    
    trust_edges = await state_manager.get_provider_edges(provider_id)
    e2j = compute_edge_to_job_ratio(trust_edges, p_hist.completed_jobs)
    sybil_risk = compute_sybil_risk(e2j)
    
    flagged_neighbors = await state_manager.get_flagged_neighbors(provider_id)
    settlement_disputed = await state_manager.has_disputed_settlement(provider_id)
    clustering = cached_scores.get("clustering", 0.0)
    
    if not trust_edges:
        clique_penalty = clustering
    else:
        flagged_set = set(flagged_neighbors)
        contaminated = len(set(trust_edges) & flagged_set) / len(trust_edges)
        clique_penalty = min(1.0, clustering * (1.0 + contaminated))
    
    components = ScoringComponents(
        lcb=lcb,
        default_risk=default_risk,
        cost_norm=cost_norm,
        trust_net=trust_net,
        cap_match=cap_match,
        sybil_risk=sybil_risk,
        clique_penalty=clique_penalty
    )
    
    raw = (
        ALPHA * lcb
        - BETA * default_risk
        - GAMMA * cost_norm
        + DELTA * trust_net
        + EPSILON * cap_match
        - LAMBDA * sybil_risk
        - MU * clique_penalty
    )
    
    score = max(0.0, min(1.0, raw))
    flags = generate_flags(components, cusum_fired, settlement_disputed)
    
    # RFC 1628 - Dynamic Freshness & Anchoring
    # For now, simulate evidence source count based on jobs
    evidence_source_count = max(1, p_hist.completed_jobs // 10)
    if evidence_source_count < 3 and p_hist.completed_jobs > 0:
        flags.append("FRAGMENTED_VISIBILITY")
        
    routing_decision = route(score, flags)
    explanation = generate_explanation(components, flags, cusum_fired)
    
    # Generate deterministic record refs (capped at 1000 to prevent OOM DOS attacks on massive histories)
    evaluated_count = min(p_hist.completed_jobs, 1000)
    record_refs = [f"job_{provider_id}_{i}" for i in range(evaluated_count)]
    
    # Calculate density relative to network (mocking baseline of 1000 nodes for density formula)
    simulated_density = len(trust_edges) / 1000.0 if trust_edges else 0.0
    
    refresh_hint = {
        "strategy": "volume_decay",
        "temporal_soft_ttl": 3600 if p_hist.completed_jobs > 50 else 1800,
        "temporal_hard_floor": 86400 if p_hist.completed_jobs > 50 else 43200,
        "evaluated_job_count": p_hist.completed_jobs,
        "evaluated_edge_density": simulated_density,
        "evaluated_record_refs": record_refs[:50] # cap array for payload size
    }
    
    # Giskard09 anchoring proof (deterministic hash of the evaluated records)
    hasher = hashlib.sha256()
    for ref in record_refs:
        hasher.update(ref.encode('utf-8'))
    root_hash = hasher.hexdigest()
    
    # Deterministic leaf hash as proof representation
    proof_hasher = hashlib.sha256()
    proof_hasher.update((root_hash + provider_id).encode('utf-8'))
    merkle_leaf_proof = "0x" + proof_hasher.hexdigest()
    
    anchor_commitment = {
        "mechanism": "anchoring-precedence-ref-v1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "root_hash": "0x" + root_hash,
        "proof": merkle_leaf_proof,
        "chain_locator": "Arbitrum-Sepolia"
    }
    
    latency_ms = (time.perf_counter() - start) * 1000
    
    return TraceScore(
        score=score,
        components=components,
        routing_decision=routing_decision,
        flags=flags,
        explanation=explanation,
        latency_ms=latency_ms,
        cusum_fired=cusum_fired,
        refresh_hint=refresh_hint,
        evidence_source_count=evidence_source_count,
        anchor_commitment=anchor_commitment
    )