import random
import math
import numpy as np
import networkx as nx
from typing import List, Dict, Any, Tuple, Optional

from .scorer import compute_trace_score
from .detection import process_default_sequence, update_ema_default_rate, update_cusum
from .graph import build_trust_graph, is_honest_seed


JOB_PRICE_USDC = 0.05
BUYER_IDS = [f"buyer_{i}" for i in range(5)]


class SimAgent:
    def __init__(self, agent_id: str, is_adversary: bool, capabilities: List[str], scenario: str, **kwargs):
        self.id = agent_id
        self.is_adversary = is_adversary
        self.capabilities = capabilities
        self.scenario = scenario
        # Attack-specific state
        self.ring_group = kwargs.get("ring_group", None)
        self.sybil_group = kwargs.get("sybil_group", None)
        self.default_prob = kwargs.get("default_prob", 0.05 if not is_adversary else 0.3)
        self.jobs_served = 0  # For sybil-cluster
        self.score_threshold = kwargs.get("score_threshold", 0.75)


def behavioral_score(completed_jobs: int, total_jobs: int) -> float:
    if total_jobs == 0:
        return 0.5
    return completed_jobs / total_jobs


def eigentrust_scores(trust_graph_edges: List[List[str]], all_ids: List[str], honest_seeds: List[str]) -> Dict[str, float]:
    if not all_ids:
        return {}

    G = nx.DiGraph()
    for node in all_ids:
        G.add_node(node)

    for edge in trust_graph_edges:
        if len(edge) == 2 and edge[0] in G and edge[1] in G:
            if G.has_edge(edge[0], edge[1]):
                G[edge[0]][edge[1]]["weight"] = G[edge[0]][edge[1]].get("weight", 0.0) + 1.0
            else:
                G.add_edge(edge[0], edge[1], weight=1.0)

    if len(G.nodes) == 0:
        return {nid: 1.0 / len(all_ids) for nid in all_ids}

    # Normalize outgoing edges per node
    C = nx.DiGraph()
    for node in G.nodes():
        C.add_node(node)

    for u in G.nodes():
        out_edges = list(G.out_edges(u, data=True))
        total_weight = sum(d.get("weight", 1.0) for _, _, d in out_edges)
        for _, v, d in out_edges:
            if total_weight > 0:
                w = d.get("weight", 1.0) / total_weight
            else:
                w = 1.0 / len(G.nodes())
            if C.has_edge(u, v):
                C[u][v]["weight"] += w
            else:
                C.add_edge(u, v, weight=w)

    # Pre-trust: uniform over honest seeds, or uniform over all if none
    if honest_seeds:
        pre_trust = {nid: 0.0 for nid in all_ids}
        valid_seeds = [s for s in honest_seeds if s in pre_trust]
        if valid_seeds:
            for seed in valid_seeds:
                pre_trust[seed] = 1.0 / len(valid_seeds)
        else:
            pre_trust = {nid: 1.0 / len(all_ids) for nid in all_ids}
    else:
        pre_trust = {nid: 1.0 / len(all_ids) for nid in all_ids}

    # Power iteration: t^(k+1) = C^T * t^(k) with teleportation
    n = len(all_ids)
    id_to_idx = {nid: i for i, nid in enumerate(all_ids)}

    # Build transition matrix C^T
    CT = np.zeros((n, n))
    for u, v, d in C.edges(data=True):
        if u in id_to_idx and v in id_to_idx:
            CT[id_to_idx[u], id_to_idx[v]] = d.get("weight", 0.0)

    t = np.array([pre_trust.get(nid, 0.0) for nid in all_ids])
    t = t / t.sum() if t.sum() > 0 else np.ones(n) / n

    teleport = np.array([pre_trust.get(nid, 0.0) for nid in all_ids])
    if teleport.sum() == 0:
        teleport = np.ones(n) / n

    alpha = 0.15  # teleport probability

    for _ in range(100):
        t_new = (1 - alpha) * (CT @ t) + alpha * teleport
        if np.linalg.norm(t_new - t, 1) < 0.001:
            break
        t = t_new
        t = t / t.sum() if t.sum() > 0 else t

    return {nid: float(t[i]) for i, nid in enumerate(all_ids)}


def create_agents(scenario: str, n_agents: int, adversary_ratio: float, seed: int) -> List[SimAgent]:
    random.seed(seed)
    np.random.seed(seed)

    n_adversaries = int(n_agents * adversary_ratio)
    n_honest = n_agents - n_adversaries

    agents = []
    cap_pool = ["summarize", "translate", "code", "image_gen", "search"]

    for i in range(n_honest):
        agents.append(SimAgent(
            f"0xhonest_{i}", False,
            ["summarize", "translate", "code"],
            scenario,
            default_prob=0.05
        ))

    if scenario == "strategic_default":
        for i in range(n_adversaries):
            dp = random.uniform(0.15, 0.45)
            agents.append(SimAgent(f"0xadv_{i}", True, ["summarize"], scenario, default_prob=dp))

    elif scenario == "collusion_ring":
        ring_size = random.randint(4, 8)
        n_rings = max(1, n_adversaries // ring_size)
        idx = 0
        for r in range(n_rings):
            for _ in range(ring_size):
                if idx >= n_adversaries:
                    break
                agents.append(SimAgent(f"0xadv_{idx}", True, ["summarize"], scenario, ring_group=r, default_prob=0.60))
                idx += 1
        for i in range(idx, n_adversaries):
            agents.append(SimAgent(f"0xadv_{i}", True, ["summarize"], scenario, default_prob=random.uniform(0.15, 0.45)))

    elif scenario == "sybil_cluster":
        n_masters = max(1, n_adversaries // 3)
        idx = 0
        group_id = 0
        for m in range(n_masters):
            n_sybils = random.randint(2, 4)
            for _ in range(n_sybils):
                if idx >= n_adversaries:
                    break
                agents.append(SimAgent(f"0xadv_{idx}", True, ["summarize"], scenario, sybil_group=group_id, default_prob=1.0))
                idx += 1
            group_id += 1
        for i in range(idx, n_adversaries):
            agents.append(SimAgent(f"0xadv_{i}", True, ["summarize"], scenario, default_prob=random.uniform(0.15, 0.45)))

    elif scenario == "game_theoretic":
        for i in range(n_adversaries):
            agents.append(SimAgent(f"0xadv_{i}", True, ["summarize"], scenario, default_prob=0.70, score_threshold=0.75))

    return agents


def get_initial_edges(agents: List[SimAgent]) -> List[List[str]]:
    edges = []
    for a in agents:
        if a.ring_group is not None:
            for b in agents:
                if b.id != a.id and b.ring_group == a.ring_group:
                    edges.append([a.id, b.id])
        if a.sybil_group is not None:
            for b in agents:
                if b.id != a.id and b.sybil_group == a.sybil_group:
                    edges.append([a.id, b.id])
    return edges


def init_provider_state(agents: List[SimAgent]) -> Dict[str, Dict]:
    return {
        a.id: {
            "completed_jobs": 0,
            "failed_jobs": 0,
            "total_jobs": 0,
            "default_sequence": [],
            "cusum_state": 0.0,
            "ema_default_rate": 0.0,
            "cusum_fired": False,
        }
        for a in agents
    }


def get_honest_seeds(state: Dict[str, Dict], agents: List[SimAgent]) -> List[str]:
    seeds = []
    for a in agents:
        if a.is_adversary:
            continue
        ps = state[a.id]
        if ps["completed_jobs"] >= 30:
            fr = ps["failed_jobs"] / max(1, ps["total_jobs"])
            if fr <= 0.10:
                seeds.append(a.id)
    return seeds


def get_flagged_neighbors(provider_id: str, graph_edges: List[List[str]], state: Dict[str, Dict]) -> List[str]:
    neighbors = set()
    for e in graph_edges:
        if e[0] == provider_id:
            neighbors.add(e[1])
        if e[1] == provider_id:
            neighbors.add(e[0])
    flagged = []
    for nid in neighbors:
        if nid not in state:
            continue
        ps = state[nid]
        e2j = len(neighbors) / max(1, ps["completed_jobs"])
        if ps.get("cusum_fired", False) or e2j > 3.0:
            flagged.append(nid)
    return flagged


def compute_trace_score_for_simulation(
    agent: SimAgent,
    state: Dict[str, Dict],
    all_agents: List[SimAgent],
    graph_edges: List[List[str]],
    honest_seeds: List[str],
) -> float:
    from .scorer import (
        compute_lcb, compute_default_risk, compute_cost_norm,
        compute_cap_match, ALPHA, BETA, GAMMA, DELTA, EPSILON, LAMBDA, MU
    )
    from .graph import compute_ppr_trust_net, compute_edge_to_job_ratio, compute_sybil_risk, compute_clique_penalty
    
    ps = state[agent.id]
    flagged = get_flagged_neighbors(agent.id, graph_edges, state)
    
    successes = ps["completed_jobs"]
    failures = ps["failed_jobs"]
    lcb = compute_lcb(successes, failures)
    
    cusum_fired = ps.get("cusum_fired", False)
    default_risk = compute_default_risk(ps["ema_default_rate"], cusum_fired)
    
    cost_norm = compute_cost_norm(JOB_PRICE_USDC, JOB_PRICE_USDC)
    
    all_providers = set()
    for edge in graph_edges:
        all_providers.add(edge[0])
        all_providers.add(edge[1])
    all_providers.add(agent.id)
    all_providers.update(honest_seeds)
    
    trust_net = compute_ppr_trust_net(
        agent.id, graph_edges, honest_seeds, list(all_providers)
    )
    
    cap_match = compute_cap_match(agent.capabilities or [], "summarize")
    
    trust_edges = [e[1] for e in graph_edges if e[0] == agent.id]
    e2j = compute_edge_to_job_ratio(trust_edges, successes)
    sybil_risk = compute_sybil_risk(e2j)
    
    clique_penalty = compute_clique_penalty(agent.id, graph_edges, flagged)
    
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
    return score


def determine_outcome(
    agent: SimAgent,
    round_num: int,
    policy_scores: Optional[Dict[str, float]] = None,
) -> bool:
    """Returns True if the provider defaults (malicious outcome)."""
    if not agent.is_adversary:
        return random.random() < 0.05

    if agent.scenario == "strategic_default":
        return random.random() < agent.default_prob

    if agent.scenario == "collusion_ring":
        if agent.ring_group is not None:
            # Build-up phase (rounds 0-19): always succeed
            if round_num < 20:
                return False
            # Exploitation phase: 60% default
            return random.random() < 0.60
        return random.random() < agent.default_prob

    if agent.scenario == "sybil_cluster":
        if agent.sybil_group is not None:
            agent.jobs_served += 1
            return agent.jobs_served > 10
        return random.random() < agent.default_prob

    if agent.scenario == "game_theoretic":
        if policy_scores is None or agent.id not in policy_scores:
            return random.random() < 0.30
        score = policy_scores[agent.id]
        all_scores = list(policy_scores.values())
        if not all_scores:
            return random.random() < 0.30
        percentile = sum(1 for s in all_scores if s <= score) / len(all_scores)
        if percentile >= 0.75:
            return random.random() < 0.70
        return False

    return random.random() < 0.30


def select_provider_weighted(agents: List[SimAgent], scores: Dict[str, float], temperature: float = 5.0) -> SimAgent:
    """
    Score-weighted random selection (softmax).
    
    In a real marketplace, the routing layer prefers higher-scored agents
    but doesn't send every single job to the same provider. Temperature
    controls exploration: higher = more uniform, lower = more greedy.
    """
    score_vals = np.array([scores.get(a.id, 0.0) for a in agents])
    # Shift to avoid overflow in exp
    score_vals = score_vals - score_vals.max()
    weights = np.exp(score_vals * temperature)
    total = weights.sum()
    if total <= 0:
        return random.choice(agents)
    probs = weights / total
    idx = np.random.choice(len(agents), p=probs)
    return agents[idx]


def run_policy_simulation(
    agents: List[SimAgent],
    policy: str,
    scenario: str,
    n_rounds: int,
    n_jobs_per_round: int,
    seed: int,
) -> Dict[str, Any]:
    random.seed(seed)
    np.random.seed(seed)

    state = init_provider_state(agents)
    graph_edges = list(get_initial_edges(agents))

    total_fraud = 0.0
    malicious_routes = 0
    total_routes = 0

    all_ids = [a.id for a in agents] + BUYER_IDS

    for round_num in range(n_rounds):
        # Pre-compute honest seeds once per round
        honest_seeds = get_honest_seeds(state, agents)

        # Pre-compute policy scores once per round (for GT adversary + selection)
        policy_scores = {}

        if policy == "trace":
            for a in agents:
                policy_scores[a.id] = compute_trace_score_for_simulation(
                    a, state, agents, graph_edges, honest_seeds
                )
        elif policy == "behavioral":
            for a in agents:
                ps = state[a.id]
                policy_scores[a.id] = behavioral_score(ps["completed_jobs"], ps["total_jobs"])
        elif policy == "eigentrust":
            e_scores = eigentrust_scores(graph_edges, all_ids, honest_seeds)
            for a in agents:
                policy_scores[a.id] = e_scores.get(a.id, 0.0)

        for _ in range(n_jobs_per_round):
            # Select provider using score-weighted random selection
            selected = select_provider_weighted(agents, policy_scores)

            # Determine outcome
            if scenario == "game_theoretic" and selected.is_adversary:
                # Refresh scores every 5 rounds for GT adversary
                if round_num % 5 == 0:
                    if policy == "trace":
                        for a in agents:
                            policy_scores[a.id] = compute_trace_score_for_simulation(
                                a, state, agents, graph_edges, honest_seeds
                            )
                    elif policy == "behavioral":
                        for a in agents:
                            ps = state[a.id]
                            policy_scores[a.id] = behavioral_score(ps["completed_jobs"], ps["total_jobs"])
                    elif policy == "eigentrust":
                        e_scores = eigentrust_scores(graph_edges, all_ids, honest_seeds)
                        for a in agents:
                            policy_scores[a.id] = e_scores.get(a.id, 0.0)
                is_malicious = determine_outcome(selected, round_num, policy_scores)
            else:
                is_malicious = determine_outcome(selected, round_num)

            total_routes += 1
            if is_malicious:
                total_fraud += JOB_PRICE_USDC
                malicious_routes += 1

            # Update state
            ps = state[selected.id]
            ps["total_jobs"] += 1
            if is_malicious:
                ps["failed_jobs"] += 1
                ps["default_sequence"].append(1)
            else:
                ps["completed_jobs"] += 1
                ps["default_sequence"].append(0)
                # Add trust edge from a random buyer to provider
                buyer = random.choice(BUYER_IDS)
                graph_edges.append([buyer, selected.id])

            # Update EMA / CUSUM incrementally (not used for scoring, but for internal state tracking)
            ps["ema_default_rate"] = update_ema_default_rate(1 if is_malicious else 0, ps["ema_default_rate"])
            cusum_res = update_cusum(1 if is_malicious else 0, ps["cusum_state"])
            ps["cusum_state"] = cusum_res.state
            if cusum_res.fired:
                ps["cusum_fired"] = True

    n_jobs_total = n_rounds * n_jobs_per_round
    return {
        "mean_fraud_usdc": round(total_fraud / max(1, n_jobs_total), 4),
        "malicious_routing_rate": round(malicious_routes / max(1, total_routes), 3),
        "seeds": [],
    }


def run_simulation(
    scenario: str,
    n_agents: int,
    adversary_ratio: float,
    n_rounds: int,
    n_jobs_per_round: int,
    seed: int,
) -> Dict[str, Any]:
    agents = create_agents(scenario, n_agents, adversary_ratio, seed)

    trace_result = run_policy_simulation(agents, "trace", scenario, n_rounds, n_jobs_per_round, seed)
    behavioral_result = run_policy_simulation(agents, "behavioral", scenario, n_rounds, n_jobs_per_round, seed)
    eigentrust_result = run_policy_simulation(agents, "eigentrust", scenario, n_rounds, n_jobs_per_round, seed)

    def reduction(pct):
        if pct >= 0:
            return f"{int(pct * 100)}%"
        return f"{int(pct * 100)}%"

    trace_fraud = trace_result["mean_fraud_usdc"]
    behavioral_fraud = behavioral_result["mean_fraud_usdc"]
    eigentrust_fraud = eigentrust_result["mean_fraud_usdc"]

    fraud_reduction_vs_behavioral = "0%"
    if behavioral_fraud > 0 and trace_fraud < behavioral_fraud:
        fraud_reduction_vs_behavioral = f"{int((1 - trace_fraud / behavioral_fraud) * 100)}%"

    fraud_reduction_vs_eigentrust = "0%"
    if eigentrust_fraud > 0 and trace_fraud < eigentrust_fraud:
        fraud_reduction_vs_eigentrust = f"{int((1 - trace_fraud / eigentrust_fraud) * 100)}%"

    return {
        "scenario": scenario,
        "results": {
            # Was "trace_no_bandit" -- inherited from the CIKM'26 paper's
            # policy name for its greedy-argmax, Thompson-sampling-disabled
            # variant. That name never matched what this simulation does:
            # select_provider_weighted() (below) is score-weighted random
            # (softmax) selection, applied identically to all three arms
            # here -- trace, behavioral, and eigentrust differ only in how
            # policy_scores is computed, not in how a provider is picked
            # from those scores. There is no bandit/no-bandit distinction
            # anywhere in this simulation, so "no_bandit" was never an
            # accurate qualifier for any of the three. Renamed to match its
            # siblings' plain naming (behavioral_only, eigentrust) instead
            # of implying a policy variant this code doesn't implement.
            "trace": trace_result,
            "behavioral_only": behavioral_result,
            "eigentrust": eigentrust_result,
        },
        "fraud_reduction_vs_behavioral": fraud_reduction_vs_behavioral,
        "fraud_reduction_vs_eigentrust": fraud_reduction_vs_eigentrust,
    }
