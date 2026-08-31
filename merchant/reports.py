"""
Read-only report endpoints for the frontend. Two different kinds of "real"
on purpose, and the frontend must not blur them:

1. Live: /agents/{agent_id}/trust-check calls TRACE's real /v1/score right
   now, through the same TraceGate /buy-credits uses -- no order is
   created, this is a pure read.
2. Batched: the /reports/* endpoints read JSON files that
   demo/demo_runner.py, demo/scaled_load_test.py, and
   demo/benchmark_report.py already write from real runs (real Razorpay
   orders, real TRACE scoring, real rate-limited seeding). They are not
   fabricated -- they're just not recomputed on every page load, because
   the runs that produce them take minutes. Each endpoint returns the
   file's mtime so the frontend can show when the underlying run happened
   instead of implying it's live.
"""
import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException

router = APIRouter()

DEMO_DIR = Path(__file__).resolve().parent.parent / "demo"

REPORT_FILES = {
    "naive-vs-protected": DEMO_DIR / "audit_log.json",
    "benchmark": DEMO_DIR / "benchmark_report.json",
    "scaled-load-test": DEMO_DIR / "scaled_load_test_report.json",
}


def _read_report(key: str) -> dict:
    path = REPORT_FILES[key]
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                f"No report at {path.name} yet -- this is real batch-run "
                "output, not something the API can fabricate. Run "
                "`python -m buildathon.demo.demo_runner` (or "
                "`scaled_load_test.py`) from the repo root first."
            ),
        )
    return {
        "generated_at": path.stat().st_mtime,
        "data": json.loads(path.read_text()),
    }


@router.get("/reports/naive-vs-protected")
async def get_naive_vs_protected_report():
    return _read_report("naive-vs-protected")


@router.get("/reports/benchmark")
async def get_benchmark_report():
    return _read_report("benchmark")


@router.get("/reports/scaled-load-test")
async def get_scaled_load_test_report():
    return _read_report("scaled-load-test")


@router.get("/reports/agents")
async def get_agent_directory():
    """Derives a per-agent directory from the last naive-vs-protected run's
    protected-pass attempts -- real per-attempt data (agent_id, class,
    score, flags, decision), not a separate live query, since the same
    audit log already has one row per agent from that run."""
    report = _read_report("naive-vs-protected")
    protected_attempts = report["data"].get("protected", {}).get("attempts", [])
    return {
        "generated_at": report["generated_at"],
        "agents": [
            {
                "agent_id": a["agent_id"],
                "agent_class": a["agent_class"],
                "score": a["score"],
                "routing_decision": a["routing_decision"],
                "flags": a["flags"],
                "status": a["status"],
                "amount_inr": a["amount_inr"],
            }
            for a in protected_attempts
        ],
    }
