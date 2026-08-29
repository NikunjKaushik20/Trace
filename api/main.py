import os
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import score, batch, benchmark, health, events, portal, agents, jobs, internal_agents, reviews, policies, payments, graph, webhooks
from .trust.router import router as trust_router
from .trust.keys import get_jwks
from .database import init_db
from .state import state_manager
from .rate_limit import limiter, rate_limit_exceeded_handler
from .middleware import RequestIDMiddleware, SecurityHeadersMiddleware, RequestTimeoutMiddleware, setup_logging
from .metrics import MetricsMiddleware, metrics_endpoint

from slowapi.errors import RateLimitExceeded


# Setup structured logging
setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    # Ensure trust signing keys exist
    from .trust.keys import ensure_keys_exist
    ensure_keys_exist()
    yield
    # Shutdown


app = FastAPI(
    title="TRACE API",
    description="Trust Routing with Adversarial Coordination Evidence — a graph-aware trust scoring API for A2A agent marketplaces.",
    version="1.0.0",
    lifespan=lifespan,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# Security headers middleware
app.add_middleware(SecurityHeadersMiddleware)

# Request timeout middleware
app.add_middleware(RequestTimeoutMiddleware)

# Request ID middleware (must be added before other middleware)
app.add_middleware(RequestIDMiddleware)

# Metrics middleware
app.add_middleware(MetricsMiddleware)

@app.get("/", include_in_schema=False)
async def root():
    return {"status": "ok", "message": "TRACE API is running"}

# JWKS endpoint for trust signal verification
@app.get("/.well-known/jwks.json", include_in_schema=False)
async def jwks():
    return get_jwks()


# Prometheus metrics endpoint
app.add_api_route("/metrics", metrics_endpoint, methods=["GET"], include_in_schema=False)


# CORS — configurable origins, no wildcard + credentials combo
ALLOWED_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,http://localhost:3001,http://localhost:8000,http://127.0.0.1:8000,https://trace-api-ixv6o.ondigitalocean.app"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(score.router, prefix="/v1")
app.include_router(batch.router, prefix="/v1")
app.include_router(benchmark.router, prefix="/v1")
app.include_router(events.router, prefix="/v1")
app.include_router(webhooks.router, prefix="/v1", tags=["Webhooks"])
app.include_router(portal.router, prefix="/portal", tags=["Portal"])
app.include_router(agents.router, prefix="/v1", tags=["Agents"])
app.include_router(jobs.router, prefix="/v1", tags=["Jobs"])
app.include_router(reviews.router, prefix="/v1", tags=["Reviews"])
app.include_router(policies.router, prefix="/v1", tags=["Policies"])
app.include_router(payments.router, prefix="/v1", tags=["Payments"])
app.include_router(graph.router, prefix="/v1", tags=["Graph"])
app.include_router(internal_agents.router, prefix="/internal-agents", tags=["Internal Agents"])
app.include_router(health.router, prefix="")
app.include_router(trust_router, prefix="/v1", tags=["Trust"])
