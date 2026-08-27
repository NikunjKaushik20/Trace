"""Pydantic models for trust.signals[] specification."""

from datetime import datetime, timezone
from typing import Optional, Literal, Any
from pydantic import BaseModel, Field
from enum import Enum


class SignalType(str, Enum):
    ONCHAIN_CREDENTIALS = "onchain_credentials"
    ONCHAIN_ACTIVITY = "onchain_activity"
    VOUCH_CHAIN = "vouch_chain"
    BEHAVIORAL = "behavioral"
    GOVERNANCE_ATTESTATION = "governance_attestation"


class BindingMethod(str, Enum):
    DID_PKH = "did:pkh"
    EIP191 = "eip191"
    SERVICE_ENDPOINT = "service_endpoint"


class Binding(BaseModel):
    method: BindingMethod
    did: Optional[str] = None
    wallet: Optional[str] = None


class ProviderInfo(BaseModel):
    name: str
    jwks: str
    kid: str
    sig: str


# ============================================================
# Behavioral Signal (maps to TRACE internal components)
# ============================================================

class BehavioralSignal(BaseModel):
    type: Literal[SignalType.BEHAVIORAL] = SignalType.BEHAVIORAL
    binding: Binding
    provider: ProviderInfo
    
    # TRACE-specific behavioral metrics
    lcb: float = Field(ge=0, le=1, description="Bayesian Lower Confidence Bound on completion rate")
    default_risk: float = Field(ge=0, le=1, description="CUSUM change-point detection score")
    cost_norm: float = Field(ge=0, le=1, description="Price anomaly relative to cohort")
    trust_net: float = Field(ge=0, le=1, description="Personalized PageRank proximity to honest seeds")
    cap_match: float = Field(ge=0, le=1, description="Capability match score")
    sybil_risk: float = Field(ge=0, le=1, description="Edge-to-job ratio Sybil indicator")
    clique_penalty: float = Field(ge=0, le=1, description="Collusion ring clustering penalty")
    
    # Composite
    composite_score: float = Field(ge=0, le=1, description="Weighted composite (TRACE score)")
    routing_decision: Literal["ROUTE", "ROUTE_WITH_CAUTION", "HOLD", "INVESTIGATE"]
    
    # Metadata
    attested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime
    evidence_source_count: int = Field(ge=0)
    anchor_commitment: Optional[str] = None
    flags: list[str] = Field(default_factory=list)


# ============================================================
# Governance Attestation Signal
# ============================================================

class GovernanceAttestationSignal(BaseModel):
    type: Literal[SignalType.GOVERNANCE_ATTESTATION] = SignalType.GOVERNANCE_ATTESTATION
    binding: Binding
    provider: ProviderInfo
    
    # Declared scope (agent's claim)
    declared_scope: dict = Field(description="Agent's declared capabilities/limits")
    declared_by: str = Field(description="Agent DID")
    declared_at: datetime
    
    # Verified scope (evaluator's verdict)
    verified_scope: dict = Field(description="Evaluator's verified capabilities/limits")
    verified_by: str = Field(description="Evaluator DID")
    verified_at: datetime
    
    verdict: Literal["APPROVED", "REJECTED", "CONDITIONAL"]
    conditions: list[str] = Field(default_factory=list)
    
    # Metadata
    attested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime


# ============================================================
# Union type for all signal types
# ============================================================

TrustSignal = BehavioralSignal | GovernanceAttestationSignal


class TrustSignalsResponse(BaseModel):
    """Response for GET /trust/signals endpoint."""
    signals: list[TrustSignal]
    issued_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    issuer: str = Field(description="TRACE API issuer DID")