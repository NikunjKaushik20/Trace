import asyncio
from functools import partial
from fastapi import APIRouter, Depends, Request

from ..models import BenchmarkRequest, BenchmarkResponse, BenchmarkResult
from ..simulation import run_simulation
from ..auth import verify_api_key, Developer
from ..rate_limit import limiter, RATE_LIMIT_BENCHMARK


router = APIRouter()


@router.post("/benchmark", response_model=BenchmarkResponse)
@limiter.limit(RATE_LIMIT_BENCHMARK)
async def run_benchmark(request: Request, benchmark_req: BenchmarkRequest, dev: Developer = Depends(verify_api_key)):
    # Run CPU-heavy simulation in a thread pool to avoid blocking the event loop
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        partial(
            run_simulation,
            scenario=benchmark_req.scenario,
            n_agents=benchmark_req.n_agents,
            adversary_ratio=benchmark_req.adversary_ratio,
            n_rounds=benchmark_req.n_rounds,
            n_jobs_per_round=benchmark_req.n_jobs_per_round,
            seed=benchmark_req.seed,
        )
    )

    return BenchmarkResponse(
        scenario=result["scenario"],
        results={
            k: BenchmarkResult(
                mean_fraud_usdc=v["mean_fraud_usdc"],
                malicious_routing_rate=v["malicious_routing_rate"],
                seeds=v["seeds"],
            )
            for k, v in result["results"].items()
        },
        fraud_reduction_vs_behavioral=result["fraud_reduction_vs_behavioral"],
        fraud_reduction_vs_eigentrust=result["fraud_reduction_vs_eigentrust"],
    )

