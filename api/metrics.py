"""
TRACE API — Prometheus Metrics
"""

from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response
import time

# Create custom registry to avoid conflicts
registry = CollectorRegistry()

# Request metrics
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
    registry=registry
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    registry=registry
)

# Scoring metrics
score_requests_total = Counter(
    "trace_score_requests_total",
    "Total score requests",
    ["routing_decision", "provider_id"],
    registry=registry
)

score_latency_seconds = Histogram(
    "trace_score_latency_seconds",
    "Score computation latency in seconds",
    ["provider_id"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
    registry=registry
)

score_value = Histogram(
    "trace_score_value",
    "Distribution of trust scores",
    ["provider_id"],
    buckets=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
    registry=registry
)

score_components = Gauge(
    "trace_score_components",
    "Individual score components",
    ["provider_id", "component"],
    registry=registry
)

# Event metrics
events_reported_total = Counter(
    "trace_events_reported_total",
    "Total events reported",
    ["provider_id", "success"],
    registry=registry
)

events_deduplicated_total = Counter(
    "trace_events_deduplicated_total",
    "Total events rejected as duplicates",
    ["provider_id"],
    registry=registry
)

# Trust graph metrics
trust_graph_nodes = Gauge(
    "trace_trust_graph_nodes",
    "Number of nodes in trust graph",
    registry=registry
)

trust_graph_edges = Gauge(
    "trace_trust_graph_edges",
    "Number of edges in trust graph",
    registry=registry
)

# Provider metrics
provider_count = Gauge(
    "trace_providers_total",
    "Total number of providers tracked",
    registry=registry
)

provider_jobs = Gauge(
    "trace_provider_jobs",
    "Provider job counts",
    ["provider_id", "type"],  # completed, failed, total
    registry=registry
)

# Billing metrics
api_calls_charged_total = Counter(
    "trace_api_calls_charged_total",
    "Total API calls charged",
    ["endpoint", "developer_id"],
    registry=registry
)

balance_usdc = Gauge(
    "trace_developer_balance_usdc",
    "Developer USDC balance",
    ["developer_id"],
    registry=registry
)

topups_total = Counter(
    "trace_topups_total",
    "Total top-ups",
    ["developer_id"],
    registry=registry
)

# Background worker metrics
worker_runs_total = Counter(
    "trace_worker_runs_total",
    "Total background worker runs",
    ["status"],  # success, error
    registry=registry
)

worker_duration_seconds = Histogram(
    "trace_worker_duration_seconds",
    "Background worker run duration",
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
    registry=registry
)

# Database metrics
db_queries_total = Counter(
    "trace_db_queries_total",
    "Total database queries",
    ["operation", "table"],
    registry=registry
)

db_query_duration_seconds = Histogram(
    "trace_db_query_duration_seconds",
    "Database query duration",
    ["operation", "table"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
    registry=registry
)

# Rate limit metrics
rate_limit_exceeded_total = Counter(
    "trace_rate_limit_exceeded_total",
    "Total rate limit exceeded",
    ["endpoint"],
    registry=registry
)


class MetricsMiddleware:
    """Middleware to collect HTTP metrics."""
    
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        method = scope["method"]
        path = scope["path"]
        start_time = time.perf_counter()
        
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_code = message["status"]
                duration = time.perf_counter() - start_time
                
                # Record metrics
                http_requests_total.labels(
                    method=method,
                    endpoint=path,
                    status=str(status_code)
                ).inc()
                
                http_request_duration_seconds.labels(
                    method=method,
                    endpoint=path
                ).observe(duration)
            
            await send(message)
        
        await self.app(scope, receive, send_wrapper)


def metrics_endpoint():
    """Prometheus metrics endpoint."""
    return Response(content=generate_latest(registry), media_type=CONTENT_TYPE_LATEST)


# Helper functions for recording metrics
def record_score_request(provider_id: str, routing_decision: str, score: float, components: dict, latency: float):
    """Record a score request."""
    score_requests_total.labels(
        routing_decision=routing_decision,
        provider_id=provider_id[:20]  # Truncate long IDs
    ).inc()
    
    score_latency_seconds.labels(
        provider_id=provider_id[:20]
    ).observe(latency)
    
    score_value.labels(
        provider_id=provider_id[:20]
    ).observe(score)
    
    for component, value in components.items():
        score_components.labels(
            provider_id=provider_id[:20],
            component=component
        ).set(value)


def record_event(provider_id: str, success: bool):
    """Record an event report."""
    events_reported_total.labels(
        provider_id=provider_id[:20],
        success=str(success).lower()
    ).inc()


def record_deduplicated_event(provider_id: str):
    """Record a deduplicated event."""
    events_deduplicated_total.labels(
        provider_id=provider_id[:20]
    ).inc()


def update_trust_graph_stats(nodes: int, edges: int):
    """Update trust graph statistics."""
    trust_graph_nodes.set(nodes)
    trust_graph_edges.set(edges)


def update_provider_stats(provider_id: str, completed: int, failed: int, total: int):
    """Update provider job statistics."""
    provider_jobs.labels(provider_id=provider_id[:20], type="completed").set(completed)
    provider_jobs.labels(provider_id=provider_id[:20], type="failed").set(failed)
    provider_jobs.labels(provider_id=provider_id[:20], type="total").set(total)


def set_provider_count(count: int):
    """Set total provider count."""
    provider_count.set(count)


def record_api_call(endpoint: str, developer_id: int):
    """Record an API call charge."""
    api_calls_charged_total.labels(
        endpoint=endpoint,
        developer_id=str(developer_id)
    ).inc()


def set_developer_balance(developer_id: int, balance: float):
    """Set developer balance."""
    balance_usdc.labels(developer_id=str(developer_id)).set(balance)


def record_topup(developer_id: int):
    """Record a top-up."""
    topups_total.labels(developer_id=str(developer_id)).inc()


def record_worker_run(status: str, duration: float):
    """Record a background worker run."""
    worker_runs_total.labels(status=status).inc()
    worker_duration_seconds.observe(duration)


def record_db_query(operation: str, table: str, duration: float):
    """Record a database query."""
    db_queries_total.labels(operation=operation, table=table).inc()
    db_query_duration_seconds.labels(operation=operation, table=table).observe(duration)


def record_rate_limit_exceeded(endpoint: str):
    """Record a rate limit exceeded event."""
    rate_limit_exceeded_total.labels(endpoint=endpoint).inc()