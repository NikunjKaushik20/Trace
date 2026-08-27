"""JWKS key management for TRACE trust signals."""

import os
import json
import base64
from datetime import datetime, timezone
from typing import Optional
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import load_pem_private_key, load_pem_public_key

# Key storage paths
KEY_DIR = os.getenv("TRACE_KEY_DIR", "/app/keys")
PRIVATE_KEY_PATH = os.path.join(KEY_DIR, "trust_signing_private.pem")
PUBLIC_KEY_PATH = os.path.join(KEY_DIR, "trust_signing_public.pem")
KID = os.getenv("TRACE_KID", "trace-trust-v1")


def generate_rsa_keypair() -> tuple[bytes, bytes]:
    """Generate RSA keypair for trust signal signing."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    
    return private_pem, public_pem


def ensure_keys_exist() -> None:
    """Generate and store RSA keypair if not exists."""
    os.makedirs(KEY_DIR, exist_ok=True)
    
    if not os.path.exists(PRIVATE_KEY_PATH) or not os.path.exists(PUBLIC_KEY_PATH):
        private_pem, public_pem = generate_rsa_keypair()
        
        with open(PRIVATE_KEY_PATH, "wb") as f:
            f.write(private_pem)
        
        with open(PUBLIC_KEY_PATH, "wb") as f:
            f.write(public_pem)
        
        os.chmod(PRIVATE_KEY_PATH, 0o600)


def load_private_key():
    """Load the private key for signing."""
    ensure_keys_exist()
    with open(PRIVATE_KEY_PATH, "rb") as f:
        return load_pem_private_key(f.read(), password=None)


def load_public_key():
    """Load the public key for verification."""
    ensure_keys_exist()
    with open(PUBLIC_KEY_PATH, "rb") as f:
        return load_pem_public_key(f.read())


def public_key_to_jwk(public_key, kid: str = KID) -> dict:
    """Convert RSA public key to JWK format."""
    numbers = public_key.public_numbers()
    
    def int_to_base64url(value: int) -> str:
        """Convert integer to base64url encoding."""
        byte_length = (value.bit_length() + 7) // 8
        return base64.urlsafe_b64encode(value.to_bytes(byte_length, "big")).decode().rstrip("=")
    
    return {
        "kty": "RSA",
        "use": "sig",
        "kid": kid,
        "alg": "RS256",
        "n": int_to_base64url(numbers.n),
        "e": int_to_base64url(numbers.e),
    }


def get_jwks() -> dict:
    """Get JWKS document."""
    public_key = load_public_key()
    return {
        "keys": [public_key_to_jwk(public_key)]
    }


def sign_payload(payload: dict) -> str:
    """Sign a payload and return base64url-encoded signature."""
    private_key = load_private_key()
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    
    signature = private_key.sign(
        payload_bytes,
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    
    return base64.urlsafe_b64encode(signature).decode().rstrip("=")


def verify_signature(payload: dict, signature_b64url: str) -> bool:
    """Verify a signature against payload."""
    try:
        public_key = load_public_key()
        payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        
        # Add padding if needed
        signature_b64 = signature_b64url + "=" * (-len(signature_b64url) % 4)
        signature = base64.urlsafe_b64decode(signature_b64)
        
        public_key.verify(
            signature,
            payload_bytes,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return True
    except Exception:
        return False