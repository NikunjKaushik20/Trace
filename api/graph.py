import networkx as nx
from typing import List, Set, Dict, Optional


def build_trust_graph(trust_graph_edges: List[List[str]]) -> nx.DiGraph:
    G = nx.DiGraph()
    for edge in trust_graph_edges:
        if len(edge) == 2:
            G.add_edge(edge[0], edge[1])
    return G


def compute_ppr_trust_net(
    provider_id: str,
    trust_graph_edges: List[List[str]],
    honest_seeds: List[str],
    all_providers: List[str]
) -> float:
    if not honest_seeds:
        return 0.0
    
    if provider_id in honest_seeds:
        return 1.0
    
    G = build_trust_graph(trust_graph_edges)
    
    if provider_id not in G and not any(provider_id == e[1] for e in trust_graph_edges):
        return 0.1
    
    personalization = {seed: 1.0 / len(honest_seeds) for seed in honest_seeds if seed in G.nodes()}
    
    if not personalization:
        return 0.0
    
    try:
        ppr_scores = nx.pagerank(G, alpha=0.85, personalization=personalization, max_iter=100)
        return ppr_scores.get(provider_id, 0.0)
    except Exception:
        return 0.0


def compute_clustering_coefficient(
    provider_id: str,
    trust_graph_edges: List[List[str]]
) -> float:
    G = build_trust_graph(trust_graph_edges)
    
    if provider_id not in G:
        return 0.0
    
    try:
        undirected = G.to_undirected()
        return nx.clustering(undirected, provider_id)
    except Exception:
        return 0.0


def compute_edge_to_job_ratio(
    trust_edges: List[str],
    completed_jobs: int
) -> float:
    if completed_jobs <= 0:
        return float(len(trust_edges))
    return len(trust_edges) / completed_jobs


def compute_sybil_risk(edge_to_job_ratio: float) -> float:
    if edge_to_job_ratio <= 1.0:
        return 0.0
    return min(1.0, (edge_to_job_ratio - 1.0) / 4.0)


def compute_clique_penalty(
    provider_id: str,
    trust_graph_edges: List[List[str]],
    flagged_neighbors: List[str]
) -> float:
    clustering = compute_clustering_coefficient(provider_id, trust_graph_edges)
    
    G = build_trust_graph(trust_graph_edges)
    if provider_id not in G:
        return 0.0
    
    neighbors = set(G.predecessors(provider_id)) | set(G.successors(provider_id))
    if not neighbors:
        return clustering
    
    flagged_set = set(flagged_neighbors)
    contaminated = len(neighbors & flagged_set) / len(neighbors)
    contamination_factor = 1.0 + contaminated
    
    return min(1.0, clustering * contamination_factor)


def is_honest_seed(
    provider_id: str,
    completed_jobs: int,
    failed_jobs: int
) -> bool:
    if completed_jobs < 30:
        return False
    failure_rate = failed_jobs / max(1, completed_jobs)
    return failure_rate <= 0.10