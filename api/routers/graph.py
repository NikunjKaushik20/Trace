from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from ..database import get_db, TrustEdge, ProviderRecord, Agent, Developer, GraphScore
from ..models import GraphResponse, GraphNode, GraphEdge

router = APIRouter()

@router.get("/graph", response_model=GraphResponse)
async def get_graph(db: AsyncSession = Depends(get_db)):
    agents_res = await db.execute(select(Agent))
    agents = agents_res.scalars().all()

    devs_res = await db.execute(select(Developer))
    devs = devs_res.scalars().all()

    # Real, persisted PageRank scores from api/worker.py's _process_graph()
    # (the same honest-seed-personalized PPR computation api/graph.py's
    # compute_ppr_trust_net() uses for live scoring, run on a schedule and
    # cached here for O(1) reads). Previously this endpoint returned a
    # hardcoded 0.98/0.24 split keyed only on is_test_agent -- a literal
    # that had nothing to do with the actual trust graph, sitting right
    # next to genuinely-computed edges. An agent with no row yet here
    # (graph processing hasn't run since it joined, or it has no trust
    # edges at all) now gets 0.0 -- an honest "not yet computed," not a
    # faked score.
    scores_res = await db.execute(select(GraphScore))
    pagerank_by_provider = {gs.provider_id: gs.pagerank for gs in scores_res.scalars().all()}

    nodes = []

    for agent in agents:
        nodes.append(GraphNode(
            id=agent.id,
            group=1,
            name=agent.name,
            score=pagerank_by_provider.get(agent.id, 0.0)
        ))

    for dev in devs:
        nodes.append(GraphNode(
            id=dev.id,
            group=2,
            name=dev.email.split("@")[0],
            score=1.0
        ))

    edges_res = await db.execute(select(TrustEdge))
    trust_edges = edges_res.scalars().all()
    
    edges = []
    for edge in trust_edges:
        edges.append(GraphEdge(
            source=edge.source_id,
            target=edge.target_id,
            value=edge.weight
        ))
        
    return GraphResponse(nodes=nodes, edges=edges)
