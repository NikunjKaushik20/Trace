"""
Unit tests for buildathon/merchant/catalog.py's trust-gated tier logic.
No network calls.

Run from the Trace-API repo root:
    pytest buildathon/tests/test_catalog.py -v
"""
from buildathon.merchant.catalog import CATALOG, best_unlocked_tier, next_tier_hint, resolve_tier


def test_catalog_is_sorted_by_ascending_min_trust_score():
    scores = [t.min_trust_score for t in CATALOG]
    assert scores == sorted(scores)


def test_catalog_tiers_are_genuine_discounts_over_starter():
    starter = next(t for t in CATALOG if t.name == "Starter")
    for t in CATALOG:
        if t.name == "Starter":
            continue
        assert t.price_per_credit_inr < starter.price_per_credit_inr


def test_zero_score_unlocks_starter_only():
    tier = best_unlocked_tier(0.0)
    assert tier is not None
    assert tier.name == "Starter"


def test_high_score_unlocks_highest_tier():
    tier = best_unlocked_tier(0.99)
    assert tier is not None
    assert tier.credits == max(t.credits for t in CATALOG)


def test_negative_score_unlocks_nothing():
    """Defensive: scores are clamped to [0, 1] by api/scorer.py, but the
    catalog logic itself shouldn't assume that -- a caller passing a raw,
    unclamped value should still get a safe answer, not unlock a tier it
    was never entitled to."""
    assert best_unlocked_tier(-1.0) is None


def test_next_tier_hint_none_when_all_unlocked():
    top_score = max(t.min_trust_score for t in CATALOG)
    assert next_tier_hint(top_score) is None


def test_next_tier_hint_reports_the_nearest_locked_tier():
    hint = next_tier_hint(0.0)
    assert hint is not None
    nearest = min((t for t in CATALOG if t.min_trust_score > 0.0), key=lambda t: t.min_trust_score)
    assert hint["tier"] == nearest.name
    assert hint["score_gap"] == round(nearest.min_trust_score - 0.0, 3)


def test_resolve_tier_is_case_insensitive():
    assert resolve_tier("plus") is CATALOG[1]
    assert resolve_tier("PLUS") is CATALOG[1]
    assert resolve_tier(" Plus ") is CATALOG[1]


def test_resolve_tier_returns_none_for_unknown_name():
    assert resolve_tier("Ultra") is None
