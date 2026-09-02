"""
End-to-end Buildathon demo: naive merchant vs. TRACE-protected merchant,
against the exact same simulated marketplace (honest agents, a strategic
defector, and a Sybil ring).

Run from the Trace-API repo root:

    python -m buildathon.demo.demo_runner

What it does:
  1. Boots an isolated local TRACE API (api.main:app) against a throwaway
     SQLite DB -- the real scoring engine, not a reimplementation, but
     never touching the production database.
  2. Seeds a synthetic marketplace history through TRACE's real
     /v1/events endpoint, then triggers the same graph-processing step
     the production Celery worker runs (api/worker.py's _process_graph).
  3. Runs every agent's purchase attempt against a "naive" merchant
     (TRACE_ENFORCE=false -- score is computed but never blocks).
  4. Runs the identical attempts again against a "protected" merchant
     (TRACE_ENFORCE=true).
  5. Prints a before/after summary and writes buildathon/demo/audit_log.json.

Nothing here touches the production DigitalOcean deployment or the main
checkout's uncommitted work -- everything lives in this isolated process
tree and an isolated SQLite file under buildathon/local_trace/.
"""
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

DEMO_DIR = Path(__file__).resolve().parent
BUILDATHON_DIR = DEMO_DIR.parent
TRACE_API_ROOT = BUILDATHON_DIR if (BUILDATHON_DIR / "api").exists() else BUILDATHON_DIR.parent

TRACE_PORT = 8099
MERCHANT_PORT = 8100
TRACE_BASE_URL = f"http://127.0.0.1:{TRACE_PORT}"
MERCHANT_BASE_URL = f"http://127.0.0.1:{MERCHANT_PORT}"


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
    pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{BUILDATHON_DIR}{os.pathsep}{BUILDATHON_DIR.parent}{os.pathsep}{pythonpath}"
    log_file = open(DEMO_DIR / f"{log_label}.log", "w")
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", module_target, "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(TRACE_API_ROOT),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )


async def _run_pass(merchant_proc_env: dict, population, label: str):
    from ..attack_sim.run_attack import run_purchase_attempts

    proc = _start_uvicorn("buildathon.merchant.app:app", MERCHANT_PORT, merchant_proc_env, f"merchant_{label}")
    try:
        _wait_for_health(f"{MERCHANT_BASE_URL}/health", f"merchant ({label})")
        results = await run_purchase_attempts(MERCHANT_BASE_URL, population)
        return results
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def _summarize(label: str, results) -> dict:
    # "orders_created", not "captured" -- a Razorpay order was created, not
    # settled. No buyer completes checkout in this demo, so no money
    # actually moves; this counts capital that *would* have been exposed,
    # not capital confirmed paid out. See buildathon/README.md.
    orders_created = [r for r in results if r.status in ("order_created", "order_creation_failed")]
    blocked = [r for r in results if r.status == "blocked"]
    fraud_orders_created = [r for r in orders_created if r.agent_class in ("sybil", "defector")]
    return {
        "label": label,
        "total_attempts": len(results),
        "orders_created": len(orders_created),
        "blocked": len(blocked),
        "fraud_amount_at_risk_inr": sum(r.amount_inr for r in fraud_orders_created),
        "fraud_agents_with_orders_created": [r.agent_id for r in fraud_orders_created],
    }


def _print_table(results, title: str) -> None:
    print(f"\n--- {title} ---")
    print(f"{'agent_id':<18} {'class':<9} {'status':<22} {'decision':<20} {'score':>6}  flags")
    for r in results:
        print(f"{r.agent_id:<18} {r.agent_class:<9} {r.status:<22} {r.routing_decision:<20} {r.score:>6.2f}  {','.join(r.flags) or '-'}")


async def main() -> None:
    load_dotenv(BUILDATHON_DIR / ".env")

    from ..local_trace import db_setup
    db_setup.configure_environment(TRACE_API_ROOT)

    print("Seeding isolated local TRACE database and demo accounts...")
    seeded = await db_setup.seed_accounts()

    # Force the rate limiter onto in-memory storage for this isolated local
    # instance -- the real .env points at a production Redis (Upstash) that
    # this demo has no business touching, and shouldn't need network access
    # to run at all.
    trace_proc = _start_uvicorn("api.main:app", TRACE_PORT, {"REDIS_URL": "memory://"}, "trace_api")
    try:
        _wait_for_health(f"{TRACE_BASE_URL}/health", "TRACE API")
        print(f"Local TRACE API up at {TRACE_BASE_URL}")

        from ..merchant.trace_gate import TraceGate
        from ..attack_sim.agents import seed_history, process_graph_scores

        seed_gate = TraceGate(base_url=TRACE_BASE_URL, api_key=seeded.merchant_api_key, enforce=True)
        print("Seeding marketplace history (honest agents, a defector, a Sybil ring)...")
        population = await seed_history(seed_gate, seeded)
        await seed_gate.close()

        print("Processing trust graph (PageRank + clustering, same as the production worker)...")
        await process_graph_scores()

        merchant_common_env = {
            "TRACE_API_BASE_URL": TRACE_BASE_URL,
            "TRACE_API_KEY": seeded.merchant_api_key,
            # The merchant's own live purchases now report their outcome
            # back to TRACE (buy_credits() -> report_outcome), which
            # requires a buyer_id api/routers/events.py will accept as this
            # developer's own identity -- db_setup.py provisions the
            # merchant's key under this exact key_prefix.
            "TRACE_MERCHANT_BUYER_ID": db_setup.MERCHANT_KEY_PREFIX,
        }

        print("\n=== PASS 1: naive merchant (TRACE_ENFORCE=false) ===")
        naive_results = await _run_pass({**merchant_common_env, "TRACE_ENFORCE": "false"}, population, "naive")
        _print_table(naive_results, "Naive merchant -- every score computed, nothing blocked")

        print("\n=== PASS 2: TRACE-protected merchant (TRACE_ENFORCE=true) ===")
        protected_results = await _run_pass({**merchant_common_env, "TRACE_ENFORCE": "true"}, population, "protected")
        _print_table(protected_results, "Protected merchant -- non-ALLOW decisions are blocked")

        naive_summary = _summarize("naive", naive_results)
        protected_summary = _summarize("protected", protected_results)

        print("\n=== SUMMARY ===")
        print(f"Naive:     {naive_summary['orders_created']}/{naive_summary['total_attempts']} orders created, "
              f"Rs {naive_summary['fraud_amount_at_risk_inr']:.0f} in orders created for sybil/defector agents")
        print(f"Protected: {protected_summary['orders_created']}/{protected_summary['total_attempts']} orders created, "
              f"Rs {protected_summary['fraud_amount_at_risk_inr']:.0f} in orders created for sybil/defector agents")
        saved = naive_summary["fraud_amount_at_risk_inr"] - protected_summary["fraud_amount_at_risk_inr"]
        print(f"TRACE prevented Rs {saved:.0f} of order-creation exposure to the Sybil ring / defector in this run.")

        print("\n=== CUSUM replay cross-check ===")
        from api.detection import process_default_sequence
        ema, cusum_state, cusum_fired = process_default_sequence(population.defector_outcome_sequence, 0.0, 0.0)
        print(f"Replaying the defector's {len(population.defector_outcome_sequence)}-event outcome sequence "
              f"through api/detection.py directly: cusum_fired={cusum_fired}, final ema_default_rate={ema:.2f}")
        defector_live = next(r for r in protected_results if r.agent_class == "defector")
        live_cusum_fired = "CUSUM_FIRED" in defector_live.flags
        print(f"Live protected-pass score for the same defector: CUSUM_FIRED={live_cusum_fired}, "
              f"routing_decision={defector_live.routing_decision} "
              f"({'matches the replay -- the persistence fix landed' if live_cusum_fired == cusum_fired else 'MISMATCH -- see NOTES.md'})")

        print("\nRunning existing api/simulation.py benchmark harness against TRACE-vs-baseline scenarios...")
        from .benchmark_report import run_benchmark_report, summarize, write_report
        benchmark_results = await run_benchmark_report(TRACE_BASE_URL, seeded.merchant_api_key)
        print(summarize(benchmark_results))
        benchmark_path = DEMO_DIR / "benchmark_report.json"
        write_report(benchmark_results, benchmark_path)
        print(f"Benchmark report written to {benchmark_path}")

        audit = {
            "naive": {"summary": naive_summary, "attempts": [r.as_dict() for r in naive_results]},
            "protected": {"summary": protected_summary, "attempts": [r.as_dict() for r in protected_results]},
            "cusum_replay": {"cusum_fired": cusum_fired, "final_ema_default_rate": ema},
            "benchmark_vs_baselines": benchmark_results,
        }
        audit_path = DEMO_DIR / "audit_log.json"
        audit_path.write_text(json.dumps(audit, indent=2))
        print(f"\nFull audit trail written to {audit_path}")

    finally:
        trace_proc.terminate()
        trace_proc.wait(timeout=10)


if __name__ == "__main__":
    asyncio.run(main())
