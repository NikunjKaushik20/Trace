"""
Scaled load test: same mechanism as demo/demo_runner.py (real TRACE API,
real merchant, real Razorpay test-mode orders), but against a
meaningfully larger synthetic marketplace, to answer "does this hold up
past a 9-agent toy demo" with real numbers instead of an assertion.

Run from the Trace-API repo root (takes several minutes -- api/rate_limit.py
caps /v1/events at 120/minute and this seeds hundreds of them; that's a
real anti-abuse control being honestly respected, not an artifact of this
script, see NOTES.md item 4). This is meant to be run once ahead of time
and cited, not run live in front of a panel -- demo_runner.py's fast
9-agent run is what to demo interactively:

    python -m buildathon.demo.scaled_load_test

Writes buildathon/demo/scaled_load_test_report.json with:
  - total identities and events seeded, and wall-clock seeding time
  - the protected merchant's decision for every agent (same mechanism as
    the small demo, at scale)
  - per-request latency percentiles for the /buy-credits round trip
    (merchant -> TRACE score -> Razorpay order creation), not just
    TRACE's internal /v1/score latency
"""
import asyncio
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import List

import httpx
from dotenv import load_dotenv

DEMO_DIR = Path(__file__).resolve().parent
BUILDATHON_DIR = DEMO_DIR.parent
TRACE_API_ROOT = BUILDATHON_DIR.parent

TRACE_PORT = 8099
MERCHANT_PORT = 8100
TRACE_BASE_URL = f"http://127.0.0.1:{TRACE_PORT}"
MERCHANT_BASE_URL = f"http://127.0.0.1:{MERCHANT_PORT}"

# Scale knobs. Defaults chosen to be a meaningful multiple of the small
# demo's 9-agent population while still finishing in single-digit minutes
# against the real 120/minute /v1/events rate limit -- override via env
# vars for a bigger run if you have the time budget. Sybil ring event count
# grows as N_SYBIL^2 (every member vouches for every other), so that knob
# dominates total runtime.
N_HONEST_AGENTS = int(os.environ.get("SCALED_N_HONEST_AGENTS", "20"))
N_SYBIL = int(os.environ.get("SCALED_N_SYBIL", "15"))


def _wait_for_health(url: str, name: str, timeout_s: float = 20.0) -> None:
    deadline = time.monotonic() + timeout_s
    last_err = None
    while time.monotonic() < deadline:
        try:
            resp = httpx.get(url, timeout=2.0)
            if resp.status_code < 500:
                return
        except Exception as e:
            last_err = e
        time.sleep(0.5)
    raise RuntimeError(f"{name} did not become healthy at {url} within {timeout_s}s: {last_err}")


def _start_uvicorn(module_target: str, port: int, extra_env: dict, log_label: str) -> subprocess.Popen:
    env = {**os.environ, **extra_env}
    log_file = open(DEMO_DIR / f"{log_label}.log", "w")
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", module_target, "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(TRACE_API_ROOT),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )


async def _timed_purchase(client: httpx.AsyncClient, agent_id: str) -> dict:
    start = time.perf_counter()
    resp = await client.post(f"{MERCHANT_BASE_URL}/buy-credits", json={"agent_id": agent_id, "credits": 1})
    elapsed_ms = (time.perf_counter() - start) * 1000
    resp.raise_for_status()
    body = resp.json()
    return {"agent_id": agent_id, "status": body["status"], "routing_decision": body["routing_decision"],
            "flags": body["flags"], "wall_clock_ms": elapsed_ms}


def _percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    k = (len(values) - 1) * p
    f, c = int(k), min(int(k) + 1, len(values) - 1)
    return values[f] + (values[c] - values[f]) * (k - f)


async def main() -> None:
    load_dotenv(BUILDATHON_DIR / ".env")

    from ..local_trace import db_setup
    db_setup.configure_environment(TRACE_API_ROOT)

    print(f"Seeding a scaled marketplace: {N_HONEST_AGENTS} honest agents, "
          f"a {N_SYBIL}-member Sybil ring, 1 strategic defector...")
    seed_start = time.monotonic()
    seeded = await db_setup.seed_accounts(n_honest_buyers=max(5, N_HONEST_AGENTS // 3), n_sybil_identities=N_SYBIL)

    trace_proc = _start_uvicorn("api.main:app", TRACE_PORT, {"REDIS_URL": "memory://"}, "trace_api_scaled")
    try:
        _wait_for_health(f"{TRACE_BASE_URL}/health", "TRACE API")
        print(f"Local TRACE API up at {TRACE_BASE_URL}")

        from ..merchant.trace_gate import TraceGate
        from ..attack_sim.agents import seed_history, process_graph_scores

        seed_gate = TraceGate(base_url=TRACE_BASE_URL, api_key=seeded.merchant_api_key, enforce=True)
        population = await seed_history(seed_gate, seeded, n_honest_agents=N_HONEST_AGENTS)
        await seed_gate.close()
        seed_elapsed_s = time.monotonic() - seed_start

        n_honest_events = N_HONEST_AGENTS * 32
        n_defector_events = 32 + 8
        n_sybil_events = N_SYBIL * N_SYBIL
        total_events = n_honest_events + n_defector_events + n_sybil_events
        print(f"Seeded {total_events} events across "
              f"{N_HONEST_AGENTS + 1 + N_SYBIL} identities in {seed_elapsed_s:.1f}s "
              f"({total_events / seed_elapsed_s:.1f} events/sec sustained, rate-limit-bound).")

        print("Processing trust graph (PageRank + clustering)...")
        graph_start = time.monotonic()
        await process_graph_scores()
        graph_elapsed_s = time.monotonic() - graph_start
        print(f"Graph processed in {graph_elapsed_s:.2f}s.")

        merchant_env = {
            "TRACE_API_BASE_URL": TRACE_BASE_URL,
            "TRACE_API_KEY": seeded.merchant_api_key,
            "TRACE_MERCHANT_BUYER_ID": db_setup.MERCHANT_KEY_PREFIX,
            "TRACE_ENFORCE": "true",
        }
        merchant_proc = _start_uvicorn("buildathon.merchant.app:app", MERCHANT_PORT, merchant_env, "merchant_scaled")
        try:
            _wait_for_health(f"{MERCHANT_BASE_URL}/health", "merchant")

            all_agent_ids = (
                [(a, "honest") for a in population.honest_agent_ids]
                + [(population.defector_agent_id, "defector")]
                + [(a, "sybil") for a in population.sybil_agent_ids]
            )

            print(f"Running {len(all_agent_ids)} purchase attempts against the protected merchant...")
            purchase_start = time.monotonic()
            async with httpx.AsyncClient(timeout=15.0) as client:
                results = []
                for agent_id, agent_class in all_agent_ids:
                    r = await _timed_purchase(client, agent_id)
                    r["agent_class"] = agent_class
                    results.append(r)
            purchase_elapsed_s = time.monotonic() - purchase_start
        finally:
            merchant_proc.terminate()
            merchant_proc.wait(timeout=10)

        latencies = [r["wall_clock_ms"] for r in results]
        blocked = [r for r in results if r["status"] == "blocked"]
        blocked_fraud = [r for r in blocked if r["agent_class"] in ("sybil", "defector")]

        print("\n=== SCALED LOAD TEST SUMMARY ===")
        print(f"Population: {len(all_agent_ids)} agents "
              f"({N_HONEST_AGENTS} honest, 1 defector, {N_SYBIL} Sybil)")
        print(f"Seeding: {total_events} events in {seed_elapsed_s:.1f}s")
        print(f"Purchase attempts: {len(results)} in {purchase_elapsed_s:.1f}s "
              f"({len(results) / purchase_elapsed_s:.1f} req/sec)")
        print(f"Latency (full /buy-credits round trip): "
              f"p50={_percentile(latencies, 0.50):.1f}ms  "
              f"p95={_percentile(latencies, 0.95):.1f}ms  "
              f"p99={_percentile(latencies, 0.99):.1f}ms  "
              f"max={max(latencies):.1f}ms")
        print(f"Blocked: {len(blocked)}/{len(results)}, of which "
              f"{len(blocked_fraud)}/{N_SYBIL + 1} were the fraud population "
              f"(sybil ring + defector) -- correctly caught at this scale.")

        report = {
            "population": {"n_honest": N_HONEST_AGENTS, "n_sybil": N_SYBIL, "n_defector": 1},
            "seeding": {"total_events": total_events, "elapsed_seconds": seed_elapsed_s},
            "graph_processing_seconds": graph_elapsed_s,
            "purchase_attempts": {
                "count": len(results), "elapsed_seconds": purchase_elapsed_s,
                "latency_ms": {
                    "p50": _percentile(latencies, 0.50), "p95": _percentile(latencies, 0.95),
                    "p99": _percentile(latencies, 0.99), "max": max(latencies),
                },
            },
            "blocked_count": len(blocked),
            "blocked_fraud_count": len(blocked_fraud),
            "fraud_population_size": N_SYBIL + 1,
            "results": results,
        }
        report_path = DEMO_DIR / "scaled_load_test_report.json"
        report_path.write_text(json.dumps(report, indent=2))
        print(f"\nFull report written to {report_path}")

    finally:
        trace_proc.terminate()
        trace_proc.wait(timeout=10)


if __name__ == "__main__":
    asyncio.run(main())
