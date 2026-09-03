// Real captured evidence from actual runs of buildathon/demo/demo_runner.py,
// buildathon/demo/scaled_load_test.py, and buildathon/demo/benchmark_report.py.
// Not live-fetched (those scripts run separately, take minutes, and touch
// real Razorpay test-mode orders) — but every value here is a real result,
// not a placeholder. See buildathon/demo/*.json for the captured source.

export type Attempt = {
  agentId: string;
  agentClass: "honest" | "defector" | "sybil";
  status: "order_created" | "blocked";
  decision: string;
  score: number;
  flags: string[];
  explanation: string;
};

export const PROTECTED_RUN: Attempt[] = [
  {
    agentId: "agent_honest_0",
    agentClass: "honest",
    status: "order_created",
    decision: "ROUTE_WITH_CAUTION",
    score: 0.35,
    flags: [],
    explanation: "High LCB (0.80) from strong completion history. Moderate trust network proximity.",
  },
  {
    agentId: "agent_honest_1",
    agentClass: "honest",
    status: "order_created",
    decision: "ROUTE_WITH_CAUTION",
    score: 0.35,
    flags: [],
    explanation: "High LCB (0.80) from strong completion history. Moderate trust network proximity.",
  },
  {
    agentId: "agent_honest_2",
    agentClass: "honest",
    status: "order_created",
    decision: "ROUTE_WITH_CAUTION",
    score: 0.35,
    flags: [],
    explanation: "High LCB (0.80) from strong completion history. Moderate trust network proximity.",
  },
  {
    agentId: "agent_defector_0",
    agentClass: "defector",
    status: "blocked",
    decision: "DENY",
    score: 0.0,
    flags: ["CUSUM_FIRED"],
    explanation:
      "Moderate LCB (0.64). CUSUM change-point alarm fired on a sudden default-rate spike - treated as a proven strategic default, does not decay.",
  },
  ...Array.from({ length: 5 }, (_, i) => ({
    agentId: `agent_sybil_${i}`,
    agentClass: "sybil" as const,
    status: "blocked" as const,
    decision: "QUARANTINE",
    score: 0.0,
    flags: ["SYBIL_RISK_HIGH", "CLIQUE_PENALTY_HIGH", "COLD_START", "FRAGMENTED_VISIBILITY"],
    explanation:
      "Low LCB (0.05) - thin evidence. Elevated default risk (0.76). High sybil risk (edge-to-job ratio anomaly). Clique penalty triggered - coordinated neighborhood.",
  })),
];

export const NAIVE_VS_PROTECTED = {
  naive: { totalAttempts: 9, ordersCreated: 9, blocked: 0, fraudAtRiskInr: 600 },
  protected: { totalAttempts: 9, ordersCreated: 3, blocked: 6, fraudAtRiskInr: 0 },
};

export const BENCHMARKS = [
  { scenario: "sybil_cluster", label: "Sybil cluster", behavioral: 53, eigentrust: 74, tie: false },
  { scenario: "collusion_ring", label: "Collusion ring", behavioral: 5, eigentrust: 32, tie: false },
  { scenario: "game_theoretic", label: "Game-theoretic", behavioral: 14, eigentrust: 69, tie: false },
  { scenario: "strategic_default", label: "Strategic default", behavioral: 0, eigentrust: 0, tie: true },
];

export const SCALED_RUN = {
  honestAgents: 20,
  sybilAgents: 15,
  defectorAgents: 1,
  totalEvents: 905,
  seedingSeconds: 442.1,
  purchaseAttempts: 36,
  purchaseElapsedSeconds: 6.8,
  latencyMs: { p50: 209.6, p95: 292.0, p99: 616.2, max: 758.3 },
  falsePositives: 0,
  honestAgentsCleared: 20,
  fraudCaught: 16,
  fraudPopulation: 16,
};

export const CATALOG = [
  {
    name: "Starter",
    credits: 1,
    priceInr: 50,
    minTrustScore: 0,
    requirement: "no history required",
  },
  {
    name: "Plus",
    credits: 5,
    priceInr: 225,
    minTrustScore: 0.25,
    requirement: "score ≥ 0.25 (ROUTE_WITH_CAUTION or better)",
  },
  {
    name: "Pro",
    credits: 20,
    priceInr: 800,
    minTrustScore: 0.5,
    requirement: "score ≥ 0.50 (ROUTE)",
  },
];

// Real weight constants from api/scorer.py's compute_trace_score() —
// raw = ALPHA*lcb - BETA*default_risk - GAMMA*cost_norm + DELTA*trust_net
//     + EPSILON*cap_match - LAMBDA*sybil_risk - MU*clique_penalty
// This is the formula's structure (how much each signal counts), not one
// decision's computed values — PurchaseResponse doesn't expose the raw
// per-component numbers, only the final score, so a specific-decision
// breakdown isn't real data we have. This is.
export const SIGNAL_COMPONENTS = [
  { key: "lcb", symbol: "α", label: "Confidence bound (LCB)", weight: 0.40, direction: "positive" as const },
  { key: "default_risk", symbol: "β", label: "Default risk (EMA + CUSUM)", weight: 0.30, direction: "negative" as const },
  { key: "sybil_risk", symbol: "λ", label: "Sybil risk (edge-to-job)", weight: 0.35, direction: "negative" as const },
  { key: "clique_penalty", symbol: "μ", label: "Clique penalty", weight: 0.25, direction: "negative" as const },
  { key: "cost_norm", symbol: "γ", label: "Price anomaly", weight: 0.15, direction: "negative" as const },
  { key: "trust_net", symbol: "δ", label: "Graph trust (PPR)", weight: 0.10, direction: "positive" as const },
  { key: "cap_match", symbol: "ε", label: "Capability match", weight: 0.10, direction: "positive" as const },
];
