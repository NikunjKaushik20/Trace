import hashlib
import logging
import secrets
import jwt
from jwt import PyJWKClient
from fastapi import HTTPException, Security, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from .database import get_db, Developer, APIKey, BillingTransaction
from .config import settings

logger = logging.getLogger("trace.auth")

ALGORITHM = "HS256"
API_CALL_COST = 0.005  # $0.005 per API call

security = HTTPBearer()
api_key_security = HTTPBearer(auto_error=False)

# JWKS client for Supabase's new JWT signing keys (cached automatically)
# Supabase serves JWKS at /auth/v1/.well-known/jwks.json (ES256)
_supabase_base = settings.supabase_url.rstrip("/") if settings.supabase_url else ""
if not _supabase_base or not _supabase_base.startswith("http"):
    _supabase_base = "https://uvdtorvdcphslzgraktm.supabase.co"
_jwks_url = f"{_supabase_base}/auth/v1/.well-known/jwks.json"
jwks_client = PyJWKClient(_jwks_url, cache_keys=True, lifespan=3600)

# Scope definitions: what each scope allows
SCOPE_PERMISSIONS = {
    "full_access": {"read", "write", "charge", "admin"},
    "read_only": {"read"},
    "billing": {"read", "charge"},
}

# Endpoint-to-required-permission mapping
ENDPOINT_PERMISSIONS = {
    "GET": "read",
    "POST": "write",  # default for POST; billing endpoints override
}


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()

def generate_api_key(is_test: bool = False) -> tuple[str, str]:
    """Returns (raw_key, hashed_key)"""
    prefix = "sk_test_" if is_test else "sk_live_"
    raw_key = f"{prefix}{secrets.token_urlsafe(32)}"
    return raw_key, hash_api_key(raw_key)

async def get_current_developer(
    credentials: HTTPAuthorizationCredentials = Security(security),
    db: AsyncSession = Depends(get_db)
) -> Developer:
    token = credentials.credentials
    try:
        # Check the token's algorithm header
        header = jwt.get_unverified_header(token)
        alg = header.get("alg", "HS256")
        
        if alg != "HS256":
            # New Supabase JWT signing keys (EdDSA/RS256) — verify via JWKS
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token, signing_key.key, algorithms=[alg], audience="authenticated"
            )
        else:
            # Legacy HS256 secret
            payload = jwt.decode(
                token, settings.supabase_jwt_secret, algorithms=["HS256"], audience="authenticated"
            )
        
        user_id: str = payload.get("sub")
        email: str = payload.get("email")
        
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")
    except jwt.PyJWTError as e:
        logger.error(f"JWT decode failed: {type(e).__name__}: {e}")
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")
    
    # Upsert developer (since they sign up via Supabase directly)
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    
    result = await db.execute(select(Developer).filter(Developer.id == user_id))
    developer = result.scalars().first()
    
    if developer is None and email:
        # ID not found — check if email already exists (e.g. after Supabase key migration)
        email_result = await db.execute(select(Developer).filter(Developer.email == email))
        existing = email_result.scalars().first()
        if existing:
            # Same email, new Supabase user ID — update via raw SQL (can't change PK in ORM safely)
            try:
                await db.execute(
                    text("UPDATE developers SET id = :new_id WHERE email = :email"),
                    {"new_id": user_id, "email": email}
                )
                await db.commit()
            except Exception:
                await db.rollback()
            # Re-fetch with new ID
            result = await db.execute(select(Developer).filter(Developer.id == user_id))
            developer = result.scalars().first()
    
    if developer is None:
        try:
            developer = Developer(id=user_id, email=email or f"{user_id}@placeholder.com")
            db.add(developer)
            await db.commit()
            await db.refresh(developer)
        except IntegrityError:
            # Race condition: another request already created this developer
            await db.rollback()
            result = await db.execute(select(Developer).filter(Developer.id == user_id))
            developer = result.scalars().first()
            if developer is None and email:
                email_result = await db.execute(select(Developer).filter(Developer.email == email))
                developer = email_result.scalars().first()
        except Exception as e:
            await db.rollback()
            logger.error(f"Developer upsert failed: {e}")
            raise HTTPException(status_code=500, detail="Account initialization error")
    
    if developer is None:
        raise HTTPException(status_code=500, detail="Failed to initialize developer account")
        
    return developer

async def verify_api_key(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Security(api_key_security),
    db: AsyncSession = Depends(get_db)
):
    dev, _ = await verify_api_key_with_context(request, credentials, db)
    return dev

async def verify_api_key_with_context(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Security(api_key_security),
    db: AsyncSession = Depends(get_db)
):
    """
    Verify API key, enforce scope permissions, and atomically charge the developer.
    Returns (developer, api_key).
    """
    raw_key = request.headers.get("TRACE_API_KEY")
    if not raw_key:
        if not credentials:
            raise HTTPException(status_code=401, detail="Missing API Key in TRACE_API_KEY header or Bearer token")
        raw_key = credentials.credentials
    
    hashed = hash_api_key(raw_key)
    
    result = await db.execute(
        select(APIKey).filter(APIKey.hashed_key == hashed, APIKey.is_active == True)
    )
    api_key = result.scalars().first()
    
    if not api_key:
        raise HTTPException(status_code=401, detail="Invalid API Key")

    # Enforce scope permissions
    scope_perms = SCOPE_PERMISSIONS.get(api_key.scope, set())
    required_perm = ENDPOINT_PERMISSIONS.get(request.method, "write")
    if required_perm not in scope_perms:
        raise HTTPException(
            status_code=403,
            detail=f"API key scope '{api_key.scope}' does not allow '{required_perm}' operations"
        )
        
    dev_result = await db.execute(
        select(Developer).filter(Developer.id == api_key.developer_id).with_for_update()
    )
    developer = dev_result.scalars().first()
    
    if not developer:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    
    charge_amount = API_CALL_COST
    if developer.balance_usdc < charge_amount and not api_key.is_test:
        raise HTTPException(status_code=402, detail="Insufficient balance. Please top up your account.")
        
    if not api_key.is_test:
        developer.balance_usdc -= charge_amount
        txn = BillingTransaction(
            developer_id=developer.id,
            amount_usdc=-charge_amount,
            balance_after=developer.balance_usdc,
            transaction_type="api_call",
            endpoint=request.url.path,
        )
        db.add(txn)
        
    await db.commit()
    return developer, api_key


async def verify_api_key_batch(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Security(api_key_security),
    db: AsyncSession = Depends(get_db)
):
    """
    Verify API key for batch endpoints. Returns (developer, api_key) tuple
    so the batch endpoint can charge per-item.
    """
    raw_key = request.headers.get("TRACE_API_KEY")
    if not raw_key:
        if not credentials:
            raise HTTPException(status_code=401, detail="Missing API Key in TRACE_API_KEY header or Bearer token")
        raw_key = credentials.credentials
    
    hashed = hash_api_key(raw_key)
    
    result = await db.execute(
        select(APIKey).filter(APIKey.hashed_key == hashed, APIKey.is_active == True)
    )
    api_key = result.scalars().first()
    
    if not api_key:
        raise HTTPException(status_code=401, detail="Invalid API Key")

    # Enforce scope permissions
    scope_perms = SCOPE_PERMISSIONS.get(api_key.scope, set())
    if "write" not in scope_perms:
        raise HTTPException(
            status_code=403,
            detail=f"API key scope '{api_key.scope}' does not allow write operations"
        )
        
    dev_result = await db.execute(
        select(Developer).filter(Developer.id == api_key.developer_id).with_for_update()
    )
    developer = dev_result.scalars().first()
    
    if not developer:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    
    return developer, api_key