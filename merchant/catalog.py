"""
Agent-readable catalog for the Buildathon merchant demo, and trust-gated
tier logic that ties TRACE's score directly to commercial terms.

Track 1 is "AI Growth & Agentic Commerce," and its example directions
include an agent-readable catalog and an upsell/cross-sell agent -- the
rest of this submission only built the safety half (trust-gating a
purchase). This is the growth half, built as a natural extension of the
same trust signal rather than a bolted-on unrelated feature: a
higher-trust agent unlocks better per-credit pricing, so investing in a
clean track record has a direct commercial payoff, not just "fewer
blocks."

Originally deliberately additive and read-only with respect to the
purchase flow -- GET /catalog and the unlocked-tier hint on
PurchaseResponse were advisory only, and did not change what /buy-credits
actually charged. That was a real gap (NOTES.md #9 documents it plainly):
a catalog whose advertised tier prices are never actually reachable
through the purchase API isn't really "commerce," it's a brochure. Tier
selection is now wired into merchant/app.py's charge path two ways: an
explicit `tier` on PurchaseRequest charges that tier's real price (gated
on the tier's own min_trust_score, checked against the score TRACE
actually returns for that priced amount, not a pre-existing one), and an
opt-in `auto_upsell` flag lets the merchant itself decide to upgrade a
smaller request to a better-value bundle when the agent's live score
qualifies -- a real upsell/cross-sell decision that changes the amount
charged, not a message. See merchant/app.py and NOTES.md #9 for exactly
how this was reconciled with the existing naive/protected comparison
(short version: the *default*, no-tier no-auto_upsell request shape is
untouched byte-for-byte, so nothing that comparison already validated
changed).
"""
from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class CatalogTier:
    name: str
    credits: int
    price_inr: float
    min_trust_score: float
    description: str

    @property
    def price_per_credit_inr(self) -> float:
        return self.price_inr / self.credits


# Prices chosen so each tier is a genuine discount over Starter's Rs 50/credit,
# and Pro's 20-credit bundle sits exactly at merchant/app.py's
# MAX_CREDITS_PER_PURCHASE default -- the growth incentive (better pricing)
# and the bounded cap (hard ceiling regardless of score) meet at the same
# number by design, not by coincidence.
CATALOG: List[CatalogTier] = [
    CatalogTier(
        name="Starter", credits=1, price_inr=50.0, min_trust_score=0.0,
        description="No trust history required.",
    ),
    CatalogTier(
        name="Plus", credits=5, price_inr=225.0, min_trust_score=0.25,
        description="10% off Starter's per-credit rate. Requires ROUTE_WITH_CAUTION or better.",
    ),
    CatalogTier(
        name="Pro", credits=20, price_inr=800.0, min_trust_score=0.50,
        description="20% off Starter's per-credit rate. Requires ROUTE.",
    ),
]


def resolve_tier(name: str) -> Optional[CatalogTier]:
    """Case-insensitive lookup by tier name, for an explicit PurchaseRequest.tier.
    Returns None for an unknown name -- merchant/app.py turns that into a 400,
    not a silent fallback to some default tier."""
    needle = name.strip().lower()
    for t in CATALOG:
        if t.name.lower() == needle:
            return t
    return None


def unlocked_tiers(score: float) -> List[CatalogTier]:
    return [t for t in CATALOG if score >= t.min_trust_score]


def best_unlocked_tier(score: float) -> Optional[CatalogTier]:
    """Highest-value tier this score currently qualifies for, or None."""
    eligible = unlocked_tiers(score)
    if not eligible:
        return None
    return max(eligible, key=lambda t: t.credits)


def next_tier_hint(score: float) -> Optional[dict]:
    """The next tier just out of reach and how much more trust it needs --
    advisory only, so an agent can see *why* a clean track record pays off
    in concrete pricing terms, not just that a trust score exists."""
    locked = [t for t in CATALOG if score < t.min_trust_score]
    if not locked:
        return None
    nxt = min(locked, key=lambda t: t.min_trust_score)
    return {
        "tier": nxt.name,
        "min_trust_score": nxt.min_trust_score,
        "score_gap": round(nxt.min_trust_score - score, 3),
        "price_per_credit_inr": nxt.price_per_credit_inr,
    }
