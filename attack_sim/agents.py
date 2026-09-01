"""
Synthetic marketplace population for the Buildathon demo, and the history
seeding that gives TRACE's real detectors something to catch.

Four agent classes, matching the paper's evaluated adversary types:

  - Honest agents: a normal completed-job history spread across a few
    distinct buyers -> low edge-to-job ratio, high LCB, no flags.
  - A Sybil ring: identities that mutually vouch for each other (each is
    both a `buyer_id` and a `provider_id`) but have almost no real
    completed jobs -> high edge-to-job ratio (api/graph.py's sybil-risk
    signal) and, once the trust graph is processed, high clustering
    (api/graph.py's clique-penalty signal).
  - A strategic defector: builds an honest-looking history, then suddenly
    defects (a burst of failures) -> should trip CUSUM-based default-risk
    detection. It doesn't, live, because of a persistence bug we found --
    see NOTES.md. We still replay its failure sequence through the same
    detector logic (api/detection.py) directly to show the math is right.

All graph edges are built through the real `/v1/events` endpoint (not by
writing to the DB directly), so this exercises the actual production
code path, just against an isolated local database.
"""
import itertools
from dataclasses import dataclass, field
from typing import List

from ..merchant.trace_gate import TraceGate
from ..local_trace.db_setup import SeededAccounts

N_HONEST_AGENTS = 3
HONEST_JOBS_PER_AGENT = 32  # >=30 completed jobs qualifies as a PPR honest-seed node
HONEST_FAILURE_EVERY = 16  # 1-in-N jobs fails, keeps failure rate under the 10% honest-seed bar

DEFECTOR_HONEST_JOBS = 32
DEFECTOR_FAILURE_BURST = 8

# Kept deliberately small: api/rate_limit.py caps /v1/events at 120/minute,
# and TraceGate retries on 429 with a fixed backoff (see merchant/trace_gate.py)
# rather than this script trying to out-clever a real rate limit.

_job_counter = itertools.count()


def _job_id(tag: str) -> str:
    return f"seed_{tag}_{next(_job_counter)}"


@dataclass
class Population:
    honest_agent_ids: List[str] = field(default_factory=list)
    sybil_agent_ids: List[str] = field(default_factory=list)
    defector_agent_id: str = "agent_defector_0"
    defector_outcome_sequence: List[int] = field(default_factory=list)  # 0=success, 1=failure, in order reported


async def seed_history(gate: TraceGate, seeded: SeededAccounts, n_honest_agents: int = N_HONEST_AGENTS) -> Population:
    """n_honest_agents defaults to the module constant (unchanged behavior
    for the normal fast demo); demo/scaled_load_test.py passes a larger
    value. The Sybil ring size already follows len(seeded.sybil_identities)
    with no change needed here -- see local_trace/db_setup.py's
    seed_accounts(n_sybil_identities=...)."""
    population = Population(
        honest_agent_ids=[f"agent_honest_{i}" for i in range(n_honest_agents)],
        sybil_agent_ids=list(seeded.sybil_identities),
    )

    # --- Honest agents: real, diverse purchase history ---
    for agent_id in population.honest_agent_ids:
        buyers = itertools.cycle(seeded.honest_buyer_ids[:3])
        for i in range(HONEST_JOBS_PER_AGENT):
            success = (i % HONEST_FAILURE_EVERY != 0) or i == 0
            await gate.report_outcome(
                agent_id=agent_id,
                buyer_id=next(buyers),
                job_id=_job_id(agent_id),
                success=success,
                price_inr=50.0,
            )

    # --- Strategic defector: honest track record, then sudden defection ---
    buyers = itertools.cycle(seeded.honest_buyer_ids[:2])
    for _ in range(DEFECTOR_HONEST_JOBS):
        await gate.report_outcome(
            agent_id=population.defector_agent_id,
            buyer_id=next(buyers),
            job_id=_job_id(population.defector_agent_id),
            success=True,
            price_inr=50.0,
        )
        population.defector_outcome_sequence.append(0)
    for _ in range(DEFECTOR_FAILURE_BURST):
        await gate.report_outcome(
            agent_id=population.defector_agent_id,
            buyer_id=next(buyers),
            job_id=_job_id(population.defector_agent_id),
            success=False,
            price_inr=50.0,
        )
        population.defector_outcome_sequence.append(1)

    # --- Sybil ring: dense mutual endorsement, thin real history ---
    # One real-looking purchase each (via an honest buyer), then every
    # other ring member "vouches" for it via a *failed* job -- lots of
    # edges, almost no completed jobs, matching a ring whose endorsements
    # are fake but whose real transactions fail or get disputed.
    honest_buyer = seeded.honest_buyer_ids[0]
    for agent_id in population.sybil_agent_ids:
        await gate.report_outcome(
            agent_id=agent_id, buyer_id=honest_buyer,
            job_id=_job_id(agent_id), success=True, price_inr=50.0,
        )
        for peer_id in population.sybil_agent_ids:
            if peer_id == agent_id:
                continue
            await gate.report_outcome(
                agent_id=agent_id, buyer_id=peer_id,
                job_id=_job_id(f"{peer_id}_to_{agent_id}"), success=False, price_inr=50.0,
            )

    return population


async def process_graph_scores() -> None:
    """Recompute PageRank/clustering for the freshly-seeded trust graph.

    In production this runs on a Celery beat schedule (api/worker.py's
    module-level comment: "every 5-10 seconds"). For a one-shot local demo
    we just await the same underlying async function directly -- no Redis
    or Celery worker required.
    """
    from api.worker import _process_graph
    await _process_graph()
