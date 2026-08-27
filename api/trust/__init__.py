"""TRACE Trust Signals Module."""

from .keys import (
    get_jwks,
    sign_payload,
    verify_signature,
    load_private_key,
    load_public_key,
    ensure_keys_exist,
    KID,
)
from .models import (
    TrustSignal,
    BehavioralSignal,
    GovernanceAttestationSignal,
    TrustSignalsResponse,
    SignalType,
    BindingMethod,
)
from .router import router as trust_router

__all__ = [
    "get_jwks",
    "sign_payload",
    "verify_signature",
    "load_private_key",
    "load_public_key",
    "ensure_keys_exist",
    "KID",
    "TrustSignal",
    "BehavioralSignal",
    "GovernanceAttestationSignal",
    "TrustSignalsResponse",
    "SignalType",
    "BindingMethod",
    "trust_router",
]