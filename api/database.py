import os
import logging
from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, DateTime, Text, UniqueConstraint, Index, text, JSON
from datetime import datetime, timezone

# ─── DATABASE URL RESOLUTION ───────────────────────────────────────────────────
# Priority: DATABASE_URL env var → SQLite fallback
# Handles: leading/trailing whitespace, empty strings, missing env var
_raw_db_url = os.getenv("DATABASE_URL", "").strip()
DATABASE_URL = _raw_db_url if _raw_db_url else "sqlite+aiosqlite:///./trace.db"

# Log which DB backend we're using (mask credentials)
if _raw_db_url:
    _safe = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL[:30]
    print(f"[database] Using DATABASE_URL from env -> ...@{_safe}")
else:
    print("[database] WARNING: DATABASE_URL not set or empty, falling back to SQLite")

# Convert postgres:// or postgresql:// to postgresql+asyncpg://
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)

print(f"[database] Final driver: {DATABASE_URL.split('://')[0]}")

# ─── ENGINE CONFIGURATION ──────────────────────────────────────────────────────
engine_kwargs = {"echo": False}
if "postgresql" in DATABASE_URL:
    engine_kwargs["pool_size"] = 20
    engine_kwargs["max_overflow"] = 0

if os.environ.get("TESTING"):
    from sqlalchemy.pool import NullPool
    engine_kwargs["poolclass"] = NullPool
    engine_kwargs.pop("pool_size", None)
    engine_kwargs.pop("max_overflow", None)

engine = create_async_engine(DATABASE_URL, **engine_kwargs)
AsyncSessionLocal = sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()


class Developer(Base):
    __tablename__ = "developers"

    # In Supabase Auth, user IDs are UUIDs. We'll store it as a string to match Supabase's auth.users id.
    id = Column(String, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    plan = Column(String, default="free")
    balance_usdc = Column(Float, default=0.0)
    webhook_url = Column(String, nullable=True)
    notification_email = Column(String, nullable=True)
    
    api_keys = relationship("APIKey", back_populates="developer")
    transactions = relationship("BillingTransaction", back_populates="developer")
    audit_events = relationship("AuditEvent", back_populates="developer")


class APIKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    developer_id = Column(String, ForeignKey("developers.id"), nullable=False)
    key_prefix = Column(String, index=True, nullable=False)  # First 8 chars
    hashed_key = Column(String, unique=True, index=True, nullable=False)
    is_active = Column(Boolean, default=True)
    is_test = Column(Boolean, default=False)
    scope = Column(String, default="full_access") # e.g. read_only, billing, full_access
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    developer = relationship("Developer", back_populates="api_keys")


class BillingTransaction(Base):
    """Audit trail for every balance change (charge or top-up)."""
    __tablename__ = "billing_transactions"

    id = Column(Integer, primary_key=True, index=True)
    developer_id = Column(String, ForeignKey("developers.id"), nullable=False)
    amount_usdc = Column(Float, nullable=False)  # negative for charges, positive for top-ups
    balance_after = Column(Float, nullable=False)
    transaction_type = Column(String, nullable=False)  # "api_call", "top_up", "refund"
    endpoint = Column(String, nullable=True)  # e.g., "/v1/score"
    provider_id = Column(String, nullable=True)  # which provider was scored
    razorpay_payment_id = Column(String, unique=True, nullable=True)  # for webhook idempotency
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    developer = relationship("Developer", back_populates="transactions")


class UsageLog(Base):
    """Audit trail for API usage (Days 1-3 traction pilot)."""
    __tablename__ = "usage_logs"

    id = Column(Integer, primary_key=True, index=True)
    developer_id = Column(String, ForeignKey("developers.id"), nullable=False)
    api_key_id = Column(Integer, ForeignKey("api_keys.id"), nullable=False)
    endpoint = Column(String, nullable=False)
    provider_id = Column(String, nullable=True)
    routing_decision = Column(String, nullable=True)
    score = Column(Float, nullable=True)
    latency_ms = Column(Float, nullable=True)
    flags = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))



class AuditEvent(Base):
    """User-facing audit log: key generated, key revoked, login, failed attempts, settings changes."""
    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True, index=True)
    developer_id = Column(String, ForeignKey("developers.id"), nullable=False)
    event_type = Column(String, nullable=False)  # "key_created", "key_revoked", "key_rotated", "login", "login_failed", "settings_updated", "checkout"
    description = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    developer = relationship("Developer", back_populates="audit_events")


class ProviderRecord(Base):
    """Persistent provider history — survives restarts."""
    __tablename__ = "provider_records"

    id = Column(Integer, primary_key=True, index=True)
    provider_id = Column(String, unique=True, index=True, nullable=False)
    completed_jobs = Column(Integer, default=0)
    failed_jobs = Column(Integer, default=0)
    total_jobs = Column(Integer, default=0)
    cusum_state = Column(Float, default=0.0)
    ema_default_rate = Column(Float, default=0.0)
    # update_cusum() (api/detection.py) resets cusum_state to 0.0 in the same
    # call where it detects a fire, so cusum_state alone can never be read back
    # as "fired" after the fact. These two columns persist the fired signal
    # itself, independent of the accumulator's reset. Sticky/non-decaying by
    # design (see api/scorer.py) -- once true, stays true.
    cusum_fired_ever = Column(Boolean, nullable=False, default=False)
    cusum_last_fired_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class TrustEdge(Base):
    """Persistent trust graph edges — survives restarts."""
    __tablename__ = "trust_edges"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(String, index=True, nullable=False)  # buyer
    target_id = Column(String, index=True, nullable=False)  # provider
    weight = Column(Integer, default=1)  # number of successful interactions
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("source_id", "target_id", name="uq_trust_edge"),
    )


class EventRecord(Base):
    """Event records for deduplication and audit trail."""
    __tablename__ = "event_records"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String, unique=True, index=True, nullable=False)  # Unique job identifier
    provider_id = Column(String, index=True, nullable=False)
    buyer_id = Column(String, index=True, nullable=False)
    reporter_id = Column(String, index=True, nullable=False)  # API key owner who reported
    capability = Column(String, nullable=True)
    price_usdc = Column(Float, nullable=True)
    success = Column(Boolean, nullable=False)
    # Which payment rail settled this job: 'usdc' (x402) | 'lightning'.
    # price_usdc is denominated in whichever rail this says, not literally USDC.
    rail = Column(String, nullable=False, default="usdc")
    # Facilitator-verified settlement proof (e.g. x402 tx hash). Null until
    # a settlement webhook matches this job_id.
    settlement_proof = Column(String, nullable=True)
    # 'self_reported' (default, developer-reported only) |
    # 'facilitator_verified' (settlement webhook confirmed the same outcome) |
    # 'disputed' (settlement webhook contradicted the reported outcome)
    verification_status = Column(String, nullable=False, default="self_reported")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class GraphScore(Base):
    """Pre-computed graph metrics for O(1) reads by the API workers."""
    __tablename__ = "graph_scores"

    id = Column(Integer, primary_key=True, index=True)
    provider_id = Column(String, unique=True, index=True, nullable=False)
    pagerank = Column(Float, default=0.0)
    clustering = Column(Float, default=0.0)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class Agent(Base):
    __tablename__ = "agents"

    id = Column(String, primary_key=True, index=True)
    owner_developer_id = Column(String, ForeignKey("developers.id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    capabilities = Column(JSON, default=list)
    endpoint_url = Column(String, nullable=True)
    wallet_address = Column(String, nullable=True)  # EVM address, x402 rail
    lightning_address = Column(String, nullable=True)  # LUD-16 address, lightning rail
    pricing_usdc = Column(Float, default=0.0)
    status = Column(String, default="pending")
    is_test_agent = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True, index=True)
    buyer_id = Column(String, ForeignKey("developers.id"), nullable=False)
    task_type = Column(String, nullable=False)
    budget_usdc = Column(Float, nullable=False)
    status = Column(String, default="posted")
    assigned_agent_id = Column(String, ForeignKey("agents.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime(timezone=True), nullable=True)


class JobEvent(Base):
    __tablename__ = "job_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String, ForeignKey("jobs.id"), nullable=False)
    status_from = Column(String, nullable=True)
    status_to = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ReviewTask(Base):
    """Manual review queue items for fraud ops."""
    __tablename__ = "review_tasks"

    id = Column(Integer, primary_key=True, index=True)
    entity_type = Column(String, nullable=False) # 'job', 'provider', 'payment'
    entity_id = Column(String, nullable=False)
    risk_level = Column(String, nullable=False) # 'HIGH', 'MEDIUM', 'LOW'
    reason = Column(String, nullable=False)
    recommended_action = Column(String, nullable=True)
    status = Column(String, default="PENDING") # 'PENDING', 'RESOLVED'
    assigned_reviewer = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    resolved_at = Column(DateTime(timezone=True), nullable=True)


class RulePolicy(Base):
    """Marketplace trust rules and policies."""
    __tablename__ = "rule_policies"

    id = Column(Integer, primary_key=True, index=True)
    rule_type = Column(String, nullable=False) # e.g. 'routing', 'quarantine', 'payment'
    condition = Column(String, nullable=False) # e.g. 'score < 0.35'
    action = Column(String, nullable=False) # e.g. 'HOLD'
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


async def init_db():
    """Create tables if they don't exist. Safe for concurrent workers."""
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            
            # Migrate existing TIMESTAMP columns to TIMESTAMPTZ (PostgreSQL only)
            if "postgresql" in str(engine.url):
                await conn.execute(text("""
                    DO $$
                    DECLARE
                        r RECORD;
                    BEGIN
                        FOR r IN
                            SELECT table_name, column_name
                            FROM information_schema.columns
                            WHERE table_schema = 'public'
                              AND data_type = 'timestamp without time zone'
                              AND column_name IN ('created_at', 'updated_at')
                        LOOP
                            EXECUTE format('ALTER TABLE %I ALTER COLUMN %I TYPE timestamptz USING %I AT TIME ZONE ''UTC''',
                                           r.table_name, r.column_name, r.column_name);
                        END LOOP;
                        
                        -- Add plan column if missing
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns 
                            WHERE table_name='developers' AND column_name='plan'
                        ) THEN
                            ALTER TABLE developers ADD COLUMN plan VARCHAR DEFAULT 'free';
                        END IF;
                    END $$;
                """))
                
        print("[database] Tables created/verified successfully")
    except Exception as e:
        # Race condition: another worker already created the tables
        if "already exists" in str(e):
            print("[database] Tables already exist (concurrent worker), continuing")
        else:
            print(f"[database] ERROR during init_db: {e}")
            raise


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
