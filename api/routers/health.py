from fastapi import APIRouter
from sqlalchemy import text
import os

from ..models import HealthResponse
from ..state import state_manager
from ..database import AsyncSessionLocal


router = APIRouter()


@router.get("/health", response_model=None)
async def health_check():
    # Check database connectivity
    db_ok = False
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
            db_ok = True
    except Exception:
        pass

    # Get trust graph stats
    try:
        stats = await state_manager.get_stats()
    except Exception:
        stats = {}

    # Overall status: ok if DB is healthy (worker might not have run yet in tests)
    # We consider "ok" if DB is connected, worker status is informational
    status = "ok" if db_ok else "degraded"

    db_url = os.environ.get("DATABASE_URL", "Not Set")
    db_host = db_url.split("@")[-1].split(":")[0] if "@" in db_url else "unknown"

    return {
        "status": status,
        "version": "1.0.0",
        "database": "connected" if db_ok else "unreachable",
        "db_host": db_host,
        "trust_graph": stats,
    }