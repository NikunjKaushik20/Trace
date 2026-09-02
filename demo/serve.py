"""
Seeds the same synthetic marketplace demo_runner.py does, then leaves the
TRACE API and merchant running persistently (until Ctrl+C) instead of
tearing them down after one comparison pass -- what the frontend actually
needs, since it's meant to be clicked through interactively, not run once
and exit.

Run from the Trace-API repo root:

    python -m buildathon.demo.serve

Then, in another terminal:

    cd buildathon/frontend && npm run dev

The frontend's live pages (Try It Live, Pricing's trust check) call this
instance directly; its batched-report pages read whatever
demo/audit_log.json, demo/benchmark_report.json, and
demo/scaled_load_test_report.json already exist on disk from a prior
demo_runner.py / scaled_load_test.py run -- run those first if you want
fresh numbers behind the Compare, Outcomes, and Marketplace pages.
"""
import asyncio
import os
import signal
import sys
from pathlib import Path

from dotenv import load_dotenv

from .demo_runner import (
    BUILDATHON_DIR,
    TRACE_API_ROOT,
    TRACE_BASE_URL,
    TRACE_PORT,
    MERCHANT_BASE_URL,
    MERCHANT_PORT,
    _start_uvicorn,
    _wait_for_health,
)

DEMO_DIR = Path(__file__).resolve().parent


async def main() -> None:
    load_dotenv(BUILDATHON_DIR / ".env")

    from ..local_trace import db_setup
    db_setup.configure_environment(TRACE_API_ROOT)

    print("Seeding isolated local TRACE database and demo accounts...")
    seeded = await db_setup.seed_accounts()

    trace_proc = _start_uvicorn("api.main:app", TRACE_PORT, {"REDIS_URL": "memory://"}, "trace_api_serve")
    try:
        _wait_for_health(f"{TRACE_BASE_URL}/health", "TRACE API")
        print(f"TRACE API up at {TRACE_BASE_URL}")

        from ..merchant.trace_gate import TraceGate
        from ..attack_sim.agents import seed_history, process_graph_scores

        seed_gate = TraceGate(base_url=TRACE_BASE_URL, api_key=seeded.merchant_api_key, enforce=True)
        print("Seeding marketplace history (honest agents, a defector, a Sybil ring)...")
        await seed_history(seed_gate, seeded)
        await seed_gate.close()

        print("Processing trust graph...")
        await process_graph_scores()

        merchant_env = {
            "TRACE_API_BASE_URL": TRACE_BASE_URL,
            "TRACE_API_KEY": seeded.merchant_api_key,
            "TRACE_MERCHANT_BUYER_ID": db_setup.MERCHANT_KEY_PREFIX,
            "TRACE_ENFORCE": "true",
            # Lets the frontend's /agent page drive a live buyer session
            # against this instance (merchant/../agent/web.py). Absent -> the
            # page stays on its captured transcripts.
            "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY", ""),
        }
        merchant_proc = _start_uvicorn("buildathon.merchant.app:app", MERCHANT_PORT, merchant_env, "merchant_serve")
        try:
            _wait_for_health(f"{MERCHANT_BASE_URL}/health", "merchant")
            print(f"Merchant API up at {MERCHANT_BASE_URL}")
            print("\nBoth services are running. Start the frontend with:")
            print("    cd buildathon/frontend && npm run dev")
            print("\nCtrl+C to stop both.\n")

            stop = asyncio.Event()
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                try:
                    loop.add_signal_handler(sig, stop.set)
                except NotImplementedError:
                    pass  # Windows: rely on KeyboardInterrupt instead
            try:
                await stop.wait()
            except KeyboardInterrupt:
                pass
        finally:
            merchant_proc.terminate()
            merchant_proc.wait(timeout=10)
    finally:
        trace_proc.terminate()
        trace_proc.wait(timeout=10)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
