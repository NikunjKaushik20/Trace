"""
Isolated local database + account seeding for the Buildathon demo.

Boots a throwaway SQLite database and Developer/APIKey rows for TRACE's
real FastAPI app (api.main:app) -- entirely separate from the production
database the live deployment uses. Nothing here touches production data.

Why this exists: TRACE's /v1/events endpoint deliberately restricts
`buyer_id` to the authenticated developer's own identity or one of their
own API key prefixes (api/routers/events.py, "prevents trust graph
poisoning by spoofing events from other buyers"). To build a graph with
several distinct "buyer" identities -- required to demonstrate the
Sybil-ring / clique detector at all, since a single-buyer graph can never
produce an edge-to-job ratio worth flagging -- we provision several API
keys under ONE demo developer account up front and use their key_prefix
values as buyer_ids. See ../NOTES.md for the full rationale and a bug we
found in the CUSUM persistence path while building this.
"""
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

BUILDATHON_DIR = Path(__file__).resolve().parent
DEMO_DB_PATH = BUILDATHON_DIR / "buildathon_demo.db"
DEMO_DATABASE_URL = f"sqlite+aiosqlite:///{DEMO_DB_PATH.as_posix()}"

N_HONEST_BUYERS = 5
N_SYBIL_IDENTITIES = 5

MERCHANT_KEY_PREFIX = "merchant_demo_key"


def configure_environment(trace_api_root: Path) -> None:
    """Point the TRACE app at a fresh isolated local DB before it's imported.

    Must be called before any `from api...` import happens in this process,
    since api/database.py reads DATABASE_URL at import time.
    """
    if DEMO_DB_PATH.exists():
        DEMO_DB_PATH.unlink()
    os.environ["DATABASE_URL"] = DEMO_DATABASE_URL
    os.environ.setdefault("TESTING", "1")
    # api/database.py does `load_dotenv()` relative to CWD; the real
    # Trace-API .env (Supabase/Razorpay-billing settings, unused by the
    # endpoints this demo calls) lives at the repo root.
    os.chdir(trace_api_root)


@dataclass
class SeededAccounts:
    merchant_api_key: str
    honest_buyer_ids: List[str] = field(default_factory=list)
    # Sybil identities double as both buyer_id (when vouching for a peer)
    # and provider_id (when being scored) -- a literal mutual-endorsement
    # ring, matching the paper's collusion/Sybil threat model.
    sybil_identities: List[str] = field(default_factory=list)


async def seed_accounts(
    n_honest_buyers: int = N_HONEST_BUYERS,
    n_sybil_identities: int = N_SYBIL_IDENTITIES,
) -> SeededAccounts:
    """Create one demo Developer plus the API keys used as buyer identities.

    Counts are parametrized (defaulting to the module constants, so the
    normal fast demo's behavior is unchanged) so demo/scaled_load_test.py
    can seed a much larger marketplace without duplicating this function.
    """
    from api.database import init_db, AsyncSessionLocal, Developer, APIKey
    from api.auth import generate_api_key

    await init_db()

    async with AsyncSessionLocal() as session:
        dev = Developer(
            id="buildathon-demo-dev",
            email="buildathon-demo@trace.local",
            plan="free",
            balance_usdc=1000.0,
        )
        session.add(dev)

        merchant_raw, merchant_hashed = generate_api_key(is_test=True)
        session.add(APIKey(
            developer_id=dev.id,
            key_prefix=MERCHANT_KEY_PREFIX,
            hashed_key=merchant_hashed,
            is_active=True,
            is_test=True,
            scope="full_access",
        ))

        honest_buyer_ids: List[str] = []
        for i in range(n_honest_buyers):
            raw, hashed = generate_api_key(is_test=True)
            identity = f"buyer_honest_{i}"
            session.add(APIKey(
                developer_id=dev.id, key_prefix=identity, hashed_key=hashed,
                is_active=True, is_test=True, scope="full_access",
            ))
            honest_buyer_ids.append(identity)

        sybil_identities: List[str] = []
        for i in range(n_sybil_identities):
            raw, hashed = generate_api_key(is_test=True)
            identity = f"agent_sybil_{i}"
            session.add(APIKey(
                developer_id=dev.id, key_prefix=identity, hashed_key=hashed,
                is_active=True, is_test=True, scope="full_access",
            ))
            sybil_identities.append(identity)

        await session.commit()

    return SeededAccounts(
        merchant_api_key=merchant_raw,
        honest_buyer_ids=honest_buyer_ids,
        sybil_identities=sybil_identities,
    )
