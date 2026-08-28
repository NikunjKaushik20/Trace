import asyncio
import logging
from celery import Celery
import networkx as nx
from sqlalchemy.future import select

from .config import settings
from .database import AsyncSessionLocal, ProviderRecord, TrustEdge, GraphScore, engine
from .graph import is_honest_seed

logger = logging.getLogger("trace.worker")

celery_app = Celery(
    "trace_worker",
    broker=settings.celery_broker_url,
    backend=settings.redis_url
)

async def _process_graph():
    logger.info("Starting graph processing cycle...")
    
    async with AsyncSessionLocal() as session:
        # Instead of fetching ALL records into memory, we process in chunks if we had to, 
        # but for graph algorithms we often need the whole graph in memory. 
        # A true scalable approach would use a graph DB or incremental algorithms.
        # For now, we apply limits to avoid complete OOMs, and warn if graph is too large.
        
        MAX_NODES = 100000
        
        # 1. Fetch Providers (Limit applied for safety)
        result = await session.execute(select(ProviderRecord).limit(MAX_NODES))
        providers = result.scalars().all()
        
        honest_seeds = [
            p.provider_id for p in providers 
            if is_honest_seed(p.provider_id, p.completed_jobs, p.failed_jobs)
        ]
        
        # 2. Fetch trust edges
        edges_result = await session.execute(select(TrustEdge).limit(MAX_NODES * 10))
        edges = edges_result.scalars().all()
        
        graph = nx.DiGraph()
        for edge in edges:
            graph.add_edge(edge.source_id, edge.target_id, weight=edge.weight)
            
        for p in providers:
            if p.provider_id not in graph:
                graph.add_node(p.provider_id)
        
        if len(graph.nodes) > 0:
            # 3. Compute PageRank
            personalization = {}
            if honest_seeds:
                valid_seeds = [s for s in honest_seeds if s in graph.nodes()]
                if valid_seeds:
                    personalization = {seed: 1.0 / len(valid_seeds) for seed in valid_seeds}
            
            try:
                pageranks = nx.pagerank(
                    graph, 
                    alpha=0.85, 
                    personalization=personalization if personalization else None, 
                    max_iter=100
                )
            except Exception as e:
                logger.error(f"PageRank error: {e}")
                pageranks = {}
                
            # 4. Compute Clustering
            try:
                undirected = graph.to_undirected()
                clusterings = nx.clustering(undirected)
            except Exception as e:
                logger.error(f"Clustering error: {e}")
                clusterings = {}
                
            # 5. Upsert into GraphScore
            is_postgres = "postgres" in engine.url.drivername
            
            for node in graph.nodes():
                pr = pageranks.get(node, 0.0)
                cl = clusterings.get(node, 0.0)
                
                stmt_kwargs = dict(
                    provider_id=node,
                    pagerank=pr,
                    clustering=cl
                )
                
                if is_postgres:
                    from sqlalchemy.dialects.postgresql import insert as pg_insert
                    stmt = pg_insert(GraphScore).values(**stmt_kwargs)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=['provider_id'],
                        set_=dict(pagerank=pr, clustering=cl)
                    )
                    await session.execute(stmt)
                else:
                    # SQLite fallback
                    from sqlalchemy import update
                    exists = await session.execute(select(GraphScore).filter_by(provider_id=node))
                    if exists.scalars().first():
                        await session.execute(
                            update(GraphScore)
                            .where(GraphScore.provider_id == node)
                            .values(pagerank=pr, clustering=cl)
                        )
                    else:
                        session.add(GraphScore(**stmt_kwargs))
            
            await session.commit()
            
    logger.info(f"Processed graph with {len(graph.nodes)} nodes")


@celery_app.task
def process_graph():
    """Celery task to run the graph processing loop."""
    asyncio.run(_process_graph())

# Note: In production, configure celery beat to run process_graph every 5-10 seconds
