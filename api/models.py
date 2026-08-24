from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Literal
from enum import Enum
from datetime import datetime


class RoutingDecision(str, Enum):
    ROUTE = "ROUTE"
    ROUTE_WITH_CAUTION = "ROUTE_WITH_CAUTION"
    HOLD = "HOLD"
    INVESTIGATE = "INVESTIGATE"
    QUARANTINE = "QUARANTINE"
    DENY = "DENY"
    REFER = "REFER"


class JobContext(BaseModel):
    capability: str
    price_usdc: float
    job_id: Optional[str] = None


class ProviderHistory(BaseModel):
    completed_jobs: int = 0
    failed_jobs: int = 0
    total_jobs: int = 0
    default_sequence: List[int] = Field(default_factory=list)
    cusum_state: float = 0.0
    ema_default_rate: float = 0.0
    # Sticky fired signal, independent of cusum_state's self-resetting
    # accumulator -- see api/database.py's ProviderRecord for why.
    cusum_fired_ever: bool = False
    cusum_last_fired_at: Optional[datetime] = None


class GraphContext(BaseModel):
    trust_edges: List[str] = Field(default_factory=list)
    trust_graph_edges: List[List[str]] = Field(default_factory=list)
    flagged_neighbors: List[str] = Field(default_factory=list)
    honest_seeds: List[str] = Field(default_factory=list)


class ScoringRequest(BaseModel):
    provider_id: str
    job: JobContext
    provider_capabilities: List[str] = Field(default_factory=list)
    cohort_median_price: Optional[float] = None


class EventReport(BaseModel):
    provider_id: str
    buyer_id: str  # Required - who transacted with the provider
    job_id: str    # Required - for deduplication
    capability: Optional[str] = None
    price_usdc: Optional[float] = None
    success: bool
    # Which payment rail settled this job. Defaults to "usdc" so existing
    # integrators who don't send this field see no change in behavior.
    # price_usdc still holds the reported price regardless of rail -- for a
    # lightning-rail job that's the sats amount, not a literal USDC amount;
    # the field name is legacy and kept for backward compatibility rather
    # than implying a currency.
    rail: Literal["usdc", "lightning"] = "usdc"


class EventReportResponse(BaseModel):
    status: str
    processed_at: str


class SettlementWebhookPayload(BaseModel):
    """
    Facilitator-side settlement confirmation. Sent by the payment rail
    (e.g. an x402 facilitator), not the integrating developer's app —
    this is what makes verification_status='facilitator_verified' mean
    something instead of just being another self-report.
    """
    job_id: str
    provider_id: str
    buyer_id: str
    price_usdc: Optional[float] = None
    settled: bool  # did settlement actually complete on the rail
    settlement_proof: str  # tx hash / facilitator receipt id
    facilitator: str = "x402"


class SettlementWebhookResponse(BaseModel):
    status: str
    verification_status: str


class LightningSettlementWebhookPayload(BaseModel):
    """
    Lightning-rail settlement confirmation. Unlike the x402 facilitator
    webhook, there's no third-party facilitator here to sign a claim -- the
    proof is the payment preimage itself. A preimage is only knowable once
    the invoice has actually been paid (that's the hash-lock the Lightning
    protocol is built on), so verifying sha256(preimage) == the invoice's
    payment_hash is independent cryptographic proof of settlement, checked
    server-side in api/lightning.py rather than trusted from a signature.
    """
    job_id: str
    provider_id: str
    buyer_id: str
    bolt11_invoice: str  # the original invoice the provider issued
    preimage: str        # hex-encoded 32-byte payment preimage

class BatchScoringRequest(BaseModel):
    providers: List[ScoringRequest] = Field(default_factory=list)

    @field_validator('providers')
    @classmethod
    def max_providers(cls, v):
        if len(v) > 100:
            raise ValueError('Maximum 100 providers per batch request')
        return v


class ScoringComponents(BaseModel):
    lcb: float
    default_risk: float
    cost_norm: float
    trust_net: float
    cap_match: float
    sybil_risk: float
    clique_penalty: float


class RefreshHint(BaseModel):
    strategy: str = "volume_decay"
    temporal_soft_ttl: int
    temporal_hard_floor: int
    evaluated_job_count: int
    evaluated_edge_density: float
    evaluated_record_refs: List[str] = Field(default_factory=list)


class AnchorCommitment(BaseModel):
    mechanism: str = "anchoring-precedence-ref-v1"
    timestamp: str
    root_hash: str
    proof: str
    chain_locator: str


class TraceScoreResponse(BaseModel):
    provider_id: str
    score: float
    routing_decision: RoutingDecision
    components: ScoringComponents
    refresh_hint: Optional[RefreshHint] = None
    evidence_source_count: Optional[int] = None
    anchor_commitment: Optional[AnchorCommitment] = None
    flags: List[str]
    explanation: str
    latency_ms: float
    version: str = "1.0.0"


class BatchScoreResponse(BaseModel):
    results: List[TraceScoreResponse]


class BenchmarkRequest(BaseModel):
    scenario: Literal["collusion_ring", "sybil_cluster", "strategic_default", "game_theoretic"]
    n_agents: int = Field(default=100, ge=10, le=500)
    adversary_ratio: float = Field(default=0.30, ge=0.10, le=0.50)
    n_rounds: int = Field(default=60, ge=10, le=200)
    n_jobs_per_round: int = Field(default=5, ge=1, le=20)
    seed: int = 42


class BenchmarkResult(BaseModel):
    mean_fraud_usdc: float
    malicious_routing_rate: float
    seeds: List[dict]


class BenchmarkResponse(BaseModel):
    scenario: str
    results: dict
    fraud_reduction_vs_behavioral: str
    fraud_reduction_vs_eigentrust: str


class HealthResponse(BaseModel):
    status: str
    version: str = "1.0.0"


class AgentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    capabilities: List[str] = Field(default_factory=list)
    endpoint_url: str
    wallet_address: Optional[str] = None    # EVM address, x402 rail
    lightning_address: Optional[str] = None  # LUD-16 address, lightning rail
    pricing_usdc: float = 0.0

class AgentResponse(BaseModel):
    id: str
    owner_developer_id: str
    name: str
    description: Optional[str] = None
    capabilities: List[str]
    endpoint_url: Optional[str] = None
    wallet_address: Optional[str] = None
    lightning_address: Optional[str] = None
    pricing_usdc: float
    status: str
    is_test_agent: bool
    created_at: datetime

class JobCreate(BaseModel):
    task_type: str
    budget_usdc: float

class JobResponse(BaseModel):
    id: str
    buyer_id: str
    task_type: str
    budget_usdc: float
    status: str
    assigned_agent_id: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

class JobEventResponse(BaseModel):
    id: int
    job_id: str
    status_from: Optional[str] = None
    status_to: str
    created_at: datetime

class ReviewTaskResponse(BaseModel):
    id: int
    entity_type: str
    entity_id: str
    risk_level: str
    reason: str
    recommended_action: Optional[str] = None
    status: str
    assigned_reviewer: Optional[str] = None
    created_at: datetime
    resolved_at: Optional[datetime] = None

class RulePolicyCreate(BaseModel):
    rule_type: str
    condition: str
    action: str

class RulePolicyResponse(BaseModel):
    id: int
    rule_type: str
    condition: str
    action: str
    is_active: bool
    created_at: datetime

class PaymentResponse(BaseModel):
    id: int
    developer_id: str
    amount_usdc: float
    balance_after: float
    transaction_type: str
    endpoint: Optional[str] = None
    provider_id: Optional[str] = None
    created_at: datetime

class GraphNode(BaseModel):
    id: str
    group: int
    name: str
    score: float

class GraphEdge(BaseModel):
    source: str
    target: str
    value: int

class GraphResponse(BaseModel):
    nodes: List[GraphNode]
    edges: List[GraphEdge]