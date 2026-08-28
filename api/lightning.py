import hashlib
from dataclasses import dataclass
from typing import Optional

from bolt11 import decode as bolt11_decode, Bolt11Exception


@dataclass
class LightningVerificationResult:
    valid: bool
    payment_hash: Optional[str] = None
    amount_sats: Optional[int] = None
    reason: Optional[str] = None


def verify_lightning_settlement(bolt11_invoice: str, preimage_hex: str) -> LightningVerificationResult:
    """
    Independently verify a Lightning settlement claim with no third party
    involved: decode the BOLT11 invoice to recover its payment_hash and
    invoiced amount, then check that the caller-submitted preimage actually
    hashes to that payment_hash. Preimages only become knowable after a real
    payment settles (that's the hash-lock at the core of the Lightning
    protocol), so a match is cryptographic proof the invoice was paid --
    comparable in strength to x402's facilitator-signed webhook, but without
    needing a shared secret or a trusted third party to vouch for it.
    """
    try:
        invoice = bolt11_decode(bolt11_invoice)
    except Bolt11Exception as e:
        return LightningVerificationResult(valid=False, reason=f"invalid bolt11 invoice: {e}")
    except Exception as e:
        return LightningVerificationResult(valid=False, reason=f"invoice decode error: {e}")

    try:
        preimage_bytes = bytes.fromhex(preimage_hex.strip())
    except ValueError:
        return LightningVerificationResult(valid=False, reason="preimage is not valid hex")

    if len(preimage_bytes) != 32:
        return LightningVerificationResult(
            valid=False, reason=f"preimage must be 32 bytes, got {len(preimage_bytes)}"
        )

    computed_hash = hashlib.sha256(preimage_bytes).hexdigest()

    if computed_hash != invoice.payment_hash:
        return LightningVerificationResult(
            valid=False,
            payment_hash=invoice.payment_hash,
            reason="preimage does not match invoice payment_hash",
        )

    amount_sats = invoice.amount_msat.sat if invoice.amount_msat is not None else None

    return LightningVerificationResult(
        valid=True,
        payment_hash=invoice.payment_hash,
        amount_sats=amount_sats,
    )
