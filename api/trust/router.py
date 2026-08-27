"""TRACE Trust Signals API endpoints."""

import os
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Depends, Request
from typing import Optional

from ..trust.keys import get_jwks, sign_payload, load_private_key, KID
from ..trust.models import (
    TrustSignalsResponse,
    BehavioralSignal,
    GovernanceAttestationSignal,
    Binding,
    BindingMethod,
    ProviderInfo,
    SignalType,
)
from ..scorer import compute_trace_score
from ..state import state_manager
from ..auth import verify_api_key, Developer

# Public JWKS URL for trust signal verification — used in signed payloads so
# external verifiers can fetch the signing key.  Configurable via env var so it
# stays correct across deployments.
_public_base = os.getenv(
    "TRACE_PUBLIC_URL",
    "https://trace-api-ixv6o.ondigitalocean.app/api"
).rstrip("/")
JWKS_URL = f"{_public_base}/v1/trust/.well-known/jwks.json"

router = APIRouter(prefix="/trust", tags=["trust"])


@router.get("/.well-known/jwks.json")
async def jwks_endpoint():
    """JWKS endpoint for trust signal verification."""
    return get_jwks()


def _create_behavioral_signal(
    provider_id: str,
    trace_result,
    binding_method: BindingMethod = BindingMethod.DID_PKH,
) -> BehavioralSignal:
    """Create a behavioral trust signal from TRACE score result."""
    private_key = load_private_key()
    from ..trust.keys import public_key_to_jwk
    public_key = private_key.public_key()
    
    # Build the signal payload (without signature)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=24)
    
    signal_data = {
        "type": "behavioral",
        "binding": {
            "method": binding_method.value,
            "wallet": provider_id,
        },
        "provider": {
            "name": "trace-api",
            "jwks": JWKS_URL,
            "kid": KID,
            "sig": "",  # Will be filled after signing
        },
        "lcb": trace_result.components.lcb,
        "default_risk": trace_result.components.default_risk,
        "cost_norm": trace_result.components.cost_norm,
        "trust_net": trace_result.components.trust_net,
        "cap_match": trace_result.components.cap_match,
        "sybil_risk": trace_result.components.sybil_risk,
        "clique_penalty": trace_result.components.clique_penalty,
        "composite_score": trace_result.score,
        "routing_decision": trace_result.routing_decision,
        "attested_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": expires_at.isoformat(),
        "evidence_source_count": trace_result.evidence_source_count,
        "anchor_commitment": str(trace_result.anchor_commitment),
        "flags": trace_result.flags,
    }
    
    # Sign the signal
    signature = sign_payload(signal_data)
    signal_data["provider"]["sig"] = signature
    
    return BehavioralSignal(**signal_data)


def _create_governance_attestation_signal(
    provider_id: str,
    trace_result,
    binding_method: BindingMethod = BindingMethod.DID_PKH,
) -> GovernanceAttestationSignal:
    """Create a governance attestation signal from TRACE score."""
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=24)
    
    # Create declared scope from provider capabilities
    declared_scope = {
        "capabilities": ["score", "events", "benchmark"],
        "max_price_usdc": 100.0,
        "max_jobs_per_day": 1000,
    }
    
    # Verified scope based on actual TRACE score
    verified_scope = {
        "capabilities": ["score", "events", "benchmark"],
        "max_price_usdc": 100.0,
        "max_jobs_per_day": 1000,
        "trust_threshold_met": trace_result.routing_decision in ["ROUTE", "ROUTE_WITH_CAUTION"],
        "min_score_required": 0.35,
    }
    
    verdict = "APPROVED" if trace_result.routing_decision in ["ROUTE", "ROUTE_WITH_CAUTION"] else "REJECTED"
    
    signal_data = {
        "type": "governance_attestation",
        "binding": {
            "method": binding_method.value,
            "wallet": provider_id,
        },
        "provider": {
            "name": "trace-api",
            "jwks": JWKS_URL,
            "kid": KID,
            "sig": "",
        },
        "declared_scope": declared_scope,
        "declared_by": f"did:pkh:eip155:1:{provider_id}",
        "declared_at": datetime.now(timezone.utc).isoformat(),
        "verified_scope": verified_scope,
        "verified_by": "did:pkh:eip155:1:trace-api",
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "conditions": [] if verdict == "APPROVED" else ["score_below_threshold"],
        "attested_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
    }
    
    # Sign the signal
    signature = sign_payload(signal_data)
    signal_data["provider"]["sig"] = signature
    
    return GovernanceAttestationSignal(**signal_data)


@router.get("/signals", response_model=dict)
async def get_trust_signals(
    provider_id: str,
    include_behavioral: bool = True,
    include_governance: bool = True,
    binding_method: str = "did:pkh",
    dev: Developer = Depends(verify_api_key),
):
    """
    Get trust.signals[] for a provider.
    
    Returns A2A-compatible trust.signals[] array with behavioral and/or governance signals.
    Each signal is signed via JWKS (RS256).
    """
    # Validate binding method
    try:
        binding_enum = BindingMethod(binding_method)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid binding_method. Must be one of: {[m.value for m in BindingMethod]}"
        )
    
    # Get TRACE score for the provider
    try:
        trace_result = await compute_trace_score(
            provider_id=provider_id,
            job_capability="general",
            price_usdc=0.0,
            cohort_median_price=0.0,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Score computation failed: {str(e)}")
    
    signals = []
    
    if include_behavioral:
        behavioral_signal = _create_behavioral_signal(
            provider_id=provider_id,
            trace_result=trace_result,
            binding_method=binding_enum,
        )
        signals.append(behavioral_signal)
    
    if include_governance:
        governance_signal = _create_governance_attestation_signal(
            provider_id=provider_id,
            trace_result=trace_result,
            binding_method=binding_enum,
        )
        signals.append(governance_signal)
    
    return TrustSignalsResponse(
        signals=signals,
        issued_at=datetime.now(timezone.utc),
        issuer="did:pkh:eip155:1:trace-api",
    ).model_dump()


@router.get("/signals/{provider_id}", response_model=dict)
async def get_trust_signals_by_id(
    provider_id: str,
    include_behavioral: bool = True,
    include_governance: bool = True,
    binding_method: str = "did:pkh",
    dev: Developer = Depends(verify_api_key),
):
    """Alternative path-based endpoint for trust signals."""
    return await get_trust_signals(
        provider_id=provider_id,
        include_behavioral=include_behavioral,
        include_governance=include_governance,
        binding_method=binding_method,
        dev=dev,
    )