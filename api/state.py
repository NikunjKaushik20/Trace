import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
from sqlalchemy.future import select
from sqlalchemy import update as sql_update
from sqlalchemy.exc import IntegrityError

from .models import ProviderHistory
from .database import AsyncSessionLocal, ProviderRecord, TrustEdge, GraphScore, EventRecord

logger = logging.getLogger(__name__)


class TraceState:
    """
    Stateless data access layer.
    All state is stored in PostgreSQL to ensure horizontal scalability.
    """

    async def get_provider(self, provider_id: str) -> ProviderHistory:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ProviderRecord).filter(ProviderRecord.provider_id == provider_id)
            )
            rec = result.scalars().first()
            if rec:
                return ProviderHistory(
                    completed_jobs=rec.completed_jobs,
                    failed_jobs=rec.failed_jobs,
                    total_jobs=rec.total_jobs,
                    cusum_state=rec.cusum_state,
                    ema_default_rate=rec.ema_default_rate,
                    cusum_fired_ever=rec.cusum_fired_ever,
                    cusum_last_fired_at=rec.cusum_last_fired_at,
                )
            return ProviderHistory()

    async def update_provider(
        self, provider_id: str, success: bool, cusum_state: float, ema_rate: float,
        cusum_fired: bool = False,
    ):
        """
        Concurrency note: this used to be a plain read-then-write
        (SELECT ... then mutate the Python object then commit), later
        "fixed" with .with_for_update() to match api/auth.py's balance-
        charging pattern -- but that fix was empirically wrong: SQLite
        (used in tests and the buildathon demo) doesn't honor row locks at
        all, so .with_for_update() silently compiles to a no-op there and
        the same lost-update race reproduced under concurrent load
        (confirmed directly: 10 concurrent first-events for one provider_id
        landed as few as 5). The actual fix is to never read-modify-write in
        Python at all -- do the increment as a single atomic SQL statement
        (col = col + 1), which is safe under concurrency on both SQLite and
        Postgres without depending on row-level locking semantics either
        backend may or may not honor.
        """
        try:
            now = datetime.now(timezone.utc)
            values = {
                "total_jobs": ProviderRecord.total_jobs + 1,
                "completed_jobs": ProviderRecord.completed_jobs + (1 if success else 0),
                "failed_jobs": ProviderRecord.failed_jobs + (0 if success else 1),
                "cusum_state": cusum_state,
                "ema_default_rate": ema_rate,
            }
            if cusum_fired:
                values["cusum_fired_ever"] = True
                values["cusum_last_fired_at"] = now

            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    sql_update(ProviderRecord)
                    .where(ProviderRecord.provider_id == provider_id)
                    .values(**values)
                )

                if result.rowcount and result.rowcount > 0:
                    await session.commit()
                    return

                # No existing row -- try to create it. Two concurrent
                # first-events for the same brand-new provider_id can both
                # reach here (a burst of brand-new identities appearing at
                # once is exactly the Sybil-ring scenario this system exists
                # to catch, not a rare edge case). provider_id is unique, so
                # the loser's INSERT raises IntegrityError.
                record = ProviderRecord(
                    provider_id=provider_id,
                    completed_jobs=1 if success else 0,
                    failed_jobs=0 if success else 1,
                    total_jobs=1,
                    cusum_state=cusum_state,
                    ema_default_rate=ema_rate,
                    cusum_fired_ever=cusum_fired,
                    cusum_last_fired_at=now if cusum_fired else None,
                )
                session.add(record)
                try:
                    await session.commit()
                except IntegrityError:
                    # Lost the create race -- the row now exists (the
                    # winner's INSERT). Roll back and retry as the same
                    # atomic UPDATE above against the row that just landed;
                    # this correctly folds our increment on top of theirs.
                    await session.rollback()
                    await session.execute(
                        sql_update(ProviderRecord)
                        .where(ProviderRecord.provider_id == provider_id)
                        .values(**values)
                    )
                    await session.commit()
        except Exception as e:
            logger.error(f"Failed to persist provider {provider_id}: {e}")

    async def apply_outcome(self, provider_id: str, success: bool):
        """
        Shared outcome-application path for both self-reported events
        (/v1/events) and facilitator-verified settlement webhooks
        (/v1/webhooks/x402). Kept as one function so the two call sites
        can't drift out of sync on how EMA/CUSUM state gets updated.
        """
        from .detection import update_ema_default_rate, update_cusum

        p_hist = await self.get_provider(provider_id)
        flag = 0 if success else 1
        new_ema = update_ema_default_rate(flag, p_hist.ema_default_rate)
        cusum_res = update_cusum(flag, p_hist.cusum_state)

        await self.update_provider(
            provider_id=provider_id,
            success=success,
            cusum_state=cusum_res.state,
            ema_rate=new_ema,
            cusum_fired=cusum_res.fired,
        )

    async def has_disputed_settlement(self, provider_id: str) -> bool:
        """
        True if a facilitator settlement webhook ever contradicted a
        self-reported outcome for this provider — i.e. they were caught
        misreporting a job outcome against verified rail settlement.
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(EventRecord.id)
                .filter(
                    EventRecord.provider_id == provider_id,
                    EventRecord.verification_status == "disputed",
                )
                .limit(1)
            )
            return result.scalars().first() is not None

    async def add_trust_edge(self, buyer_id: str, provider_id: str):
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(TrustEdge).filter(
                        TrustEdge.source_id == buyer_id,
                        TrustEdge.target_id == provider_id,
                    )
                )
                edge = result.scalars().first()

                if edge:
                    edge.weight += 1
                else:
                    edge = TrustEdge(source_id=buyer_id, target_id=provider_id, weight=1)
                    session.add(edge)

                await session.commit()
        except Exception as e:
            logger.error(f"Failed to persist trust edge {buyer_id} -> {provider_id}: {e}")

    async def get_cached_scores(self, provider_id: str) -> Dict[str, float]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(GraphScore).filter(GraphScore.provider_id == provider_id)
            )
            score = result.scalars().first()
            if score:
                return {"pagerank": score.pagerank, "clustering": score.clustering}
            return {"pagerank": 0.0, "clustering": 0.0}

    async def get_provider_edges(self, provider_id: str) -> List[str]:
        """Returns list of buyers who trust this provider."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(TrustEdge.source_id).filter(TrustEdge.target_id == provider_id)
            )
            return list(result.scalars().all())

    async def get_flagged_neighbors(self, provider_id: str) -> List[str]:
        """Check the 1-hop neighborhood for flagged agents (Sybil/CUSUM)."""
        async with AsyncSessionLocal() as session:
            # 1. Get neighbors (both inbound and outbound)
            in_res = await session.execute(select(TrustEdge.source_id).filter(TrustEdge.target_id == provider_id))
            out_res = await session.execute(select(TrustEdge.target_id).filter(TrustEdge.source_id == provider_id))
            
            neighbors = set(in_res.scalars().all()) | set(out_res.scalars().all())
            if not neighbors:
                return []
            
            # 2. Get their records to check for flags
            result = await session.execute(
                select(ProviderRecord).filter(ProviderRecord.provider_id.in_(neighbors))
            )
            flagged = []
            for p in result.scalars().all():
                # We do a simplified Edge-to-Job check. In the real system the background worker
                # would compute E2J for every node, but here we approximate it for neighbors.
                e2j = len(neighbors) / max(1, p.completed_jobs) # approx
                if p.cusum_fired_ever or e2j > 3.0:
                    flagged.append(p.provider_id)
                    
            return flagged

    async def get_stats(self) -> dict:
        """Return state statistics for health checks."""
        async with AsyncSessionLocal() as session:
            from sqlalchemy import func
            p_count = await session.execute(select(func.count(ProviderRecord.id)))
            e_count = await session.execute(select(func.count(TrustEdge.id)))
            return {
                "providers": p_count.scalar() or 0,
                "trust_edges": e_count.scalar() or 0,
                "warm_started": True,
            }


# Global singleton for stateless access
state_manager = TraceState()
