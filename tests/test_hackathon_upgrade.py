"""Hackathon-upgrade regression tests.

Pure-function tests for the new demand intelligence / trust / opportunity /
demo code. No live MongoDB, no live Telegram — matches the existing test style.

These guard against the most common regressions:
  - Opportunity score: high demand + high miss = high score.
  - Opportunity score: zero history = empty / score 0.
  - Opportunity score: products unrelated to the merchant's category are filtered.
  - Trust score with zero history = "New merchant" label, neutral 50/100.
  - Trust score with low history = "New merchant" label too.
  - Trust score with strong history > 80/100.
  - Freshness labels: just-confirmed vs stale inventory vs price-not-provided.
  - Bucket aggregation for heatmap privacy: two close points collapse to one bucket.
  - Explainability bullets are non-empty and human-readable.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.services import opportunity_service, trust_service
from app.services.demand_engine import bucket_lat_lng
from app.services.demo_service import _matches_scenario, DEMO_SCENARIOS


# ----------------------------------------------------------------- opportunity

def test_opportunity_score_high_demand_high_miss_gets_high_score():
    result = opportunity_service.opportunity_score(
        product="PVC elbow joint", category="hardware",
        unique_requests=14, unavailable_requests=11, available_requests=3,
        trend_ratio=1.6, average_search_distance_meters=2100,
        nearby_inventory_coverage=2, merchant_category_affinity=1.0,
        merchant_already_stocks=False,
    )
    assert result["opportunityScore"] >= 60
    assert result["recommendedQuantity"] >= 5
    assert "14 nearby customers" in result["reason"]
    assert result["trend"] == "rising"


def test_opportunity_score_zero_history_is_zero():
    result = opportunity_service.opportunity_score(
        product="Obscure widget", category="other",
        unique_requests=0, unavailable_requests=0, available_requests=0,
        trend_ratio=None, average_search_distance_meters=None,
        nearby_inventory_coverage=0, merchant_category_affinity=0.5,
        merchant_already_stocks=False,
    )
    assert result["opportunityScore"] == 0
    assert result["recommendedQuantity"] == 0
    assert "aur data chahiye" in result["reason"]


def test_opportunity_score_filters_unrelated_category():
    """A hardware product should NOT be recommended to a clothing shop."""
    result = opportunity_service.opportunity_score(
        product="PVC pipe", category="hardware",
        unique_requests=20, unavailable_requests=18, available_requests=2,
        trend_ratio=1.5, average_search_distance_meters=1500,
        nearby_inventory_coverage=0, merchant_category_affinity=0.05,
        merchant_already_stocks=False,
    )
    assert result["opportunityScore"] == 0
    assert "category se related nahi" in result["reason"]


def test_opportunity_score_filters_already_stocked():
    result = opportunity_service.opportunity_score(
        product="Teflon Tape", category="hardware",
        unique_requests=20, unavailable_requests=18, available_requests=2,
        trend_ratio=1.5, average_search_distance_meters=1500,
        nearby_inventory_coverage=0, merchant_category_affinity=1.0,
        merchant_already_stocks=True,
    )
    assert result["opportunityScore"] == 0
    assert "pehle se stock" in result["reason"]


def test_opportunity_score_low_volume_returns_empty():
    """Fewer than OPPORTUNITY_MIN_REQUESTS (3) is too thin a signal."""
    result = opportunity_service.opportunity_score(
        product="Niche thing", category="hardware",
        unique_requests=2, unavailable_requests=1, available_requests=1,
        trend_ratio=1.0, average_search_distance_meters=400,
        nearby_inventory_coverage=1, merchant_category_affinity=0.9,
        merchant_already_stocks=False,
    )
    assert result["opportunityScore"] == 0
    assert "aur data chahiye" in result["reason"]


def test_opportunity_quantity_capped_at_50():
    """A viral product shouldn't recommend an absurd quantity."""
    result = opportunity_service.opportunity_score(
        product="Viral thing", category="hardware",
        unique_requests=500, unavailable_requests=400, available_requests=100,
        trend_ratio=2.0, average_search_distance_meters=1500,
        nearby_inventory_coverage=0, merchant_category_affinity=1.0,
        merchant_already_stocks=False,
    )
    assert 5 <= result["recommendedQuantity"] <= 50


def test_sort_opportunities_drops_empty_and_sorts_desc():
    rows = [
        {"product": "A", "opportunityScore": 0, "uniqueRequests": 5},
        {"product": "B", "opportunityScore": 90, "uniqueRequests": 10},
        {"product": "C", "opportunityScore": 70, "uniqueRequests": 8},
    ]
    out = opportunity_service.sort_opportunities(rows)
    assert [r["product"] for r in out] == ["B", "C"]
    assert "A" not in [r["product"] for r in out]


# ----------------------------------------------------------------------- trust

def test_trust_score_zero_history_is_new_merchant_neutral_50():
    result = trust_service.compute_trust_score(
        notified_count=0, accepted_count=0, declined_count=0,
        completed_selections=0, response_times_seconds=[],
        is_verified=False, account_age_days=0,
    )
    assert result["isNewMerchant"] is True
    assert result["reliabilityScore"] == 50
    assert result["label"] == "New merchant"
    assert "koi response nahi" in result["reason"]


def test_trust_score_low_history_still_new_merchant():
    """Below TRUST_MIN_SAMPLE (5) we still say 'New merchant' — unfair to
    penalise a shop that just got its first few requests."""
    result = trust_service.compute_trust_score(
        notified_count=4, accepted_count=2, declined_count=1,
        completed_selections=0, response_times_seconds=[20, 35, 12],
        is_verified=False, account_age_days=2,
    )
    # answered = accepted + declined = 3 → below the 5-response threshold.
    assert result["isNewMerchant"] is True
    assert result["reliabilityScore"] == 50
    assert "3 response mili" in result["reason"]


def test_trust_score_strong_history_above_80():
    """A responsive, verified shop with many YES replies scores high."""
    result = trust_service.compute_trust_score(
        notified_count=20, accepted_count=15, declined_count=4,
        completed_selections=8, response_times_seconds=[10, 20, 25, 12, 18, 30, 22, 15],
        is_verified=True, account_age_days=200,
    )
    assert result["isNewMerchant"] is False
    assert result["reliabilityScore"] >= 80
    assert "verified shop" in result["reason"]


def test_trust_score_average_response_seconds_is_median():
    """Median (not mean) — robust to one slow outlier."""
    result = trust_service.compute_trust_score(
        notified_count=10, accepted_count=8, declined_count=2,
        completed_selections=3, response_times_seconds=[5, 8, 12, 15, 600],
        is_verified=True, account_age_days=120,
    )
    # Median of [5,8,12,15,600] = 12 (odd count, middle).
    assert result["averageResponseSeconds"] == 12


def test_trust_score_label_changes_with_score():
    high = trust_service.compute_trust_score(
        notified_count=20, accepted_count=18, declined_count=2,
        completed_selections=10, response_times_seconds=[5, 8, 10, 12, 15],
        is_verified=True, account_age_days=300,
    )
    mid = trust_service.compute_trust_score(
        notified_count=20, accepted_count=8, declined_count=12,
        completed_selections=2, response_times_seconds=[60, 120, 90, 200, 150],
        is_verified=False, account_age_days=120,
    )
    assert high["reliabilityScore"] > mid["reliabilityScore"]
    assert high["label"] != mid["label"]


# ------------------------------------------------------------------- freshness

def test_freshness_just_confirmed():
    now = datetime.now(tz=timezone.utc)
    responded = now - timedelta(seconds=30)
    result = trust_service.freshness_label(
        responded_at=responded, notified_at=now - timedelta(seconds=45),
        has_inventory_hint=False, has_price=True,
    )
    assert result["statusLabel"] == "Confirmed just now"
    assert result["priceLabel"] == "Price confirmed by merchant"


def test_freshness_minutes_ago():
    now = datetime.now(tz=timezone.utc)
    responded = now - timedelta(minutes=5)
    result = trust_service.freshness_label(
        responded_at=responded, notified_at=now - timedelta(minutes=6),
        has_inventory_hint=False, has_price=False,
    )
    assert "5 minutes ago" in result["statusLabel"]
    assert result["priceLabel"] == "Price not provided"


def test_freshness_inventory_listed_with_no_response():
    now = datetime.now(tz=timezone.utc)
    inv_updated = now - timedelta(hours=2)
    result = trust_service.freshness_label(
        responded_at=None, notified_at=None,
        has_inventory_hint=True, inventory_updated_at=inv_updated,
        has_price=True,
    )
    assert result["statusLabel"] == "Shop-listed stock"
    assert result["priceLabel"] == "Stock price (not merchant-confirmed)"


def test_freshness_stale_inventory_flagged():
    now = datetime.now(tz=timezone.utc)
    inv_updated = now - timedelta(days=10)
    result = trust_service.freshness_label(
        responded_at=None, notified_at=None,
        has_inventory_hint=True, inventory_updated_at=inv_updated,
        has_price=False,
    )
    assert "stale" in result["statusLabel"].lower() or "days ago" in result["statusLabel"]


# ------------------------------------------------------------------ heatmap

def test_bucket_collapses_nearby_points_for_privacy():
    """Two customer locations within ~50m of each other must collapse to the
    same bucket so individual customers can't be re-identified from the map."""
    p1 = bucket_lat_lng(24.07340, 75.06860, bucket_meters=300)
    p2 = bucket_lat_lng(24.07342, 75.06858, bucket_meters=300)
    assert p1 == p2, f"Points should collapse to same bucket: {p1} vs {p2}"


def test_bucket_far_apart_do_not_collapse():
    p1 = bucket_lat_lng(24.07340, 75.06860, bucket_meters=300)
    p2 = bucket_lat_lng(24.08000, 75.07000, bucket_meters=300)
    assert p1 != p2


def test_bucket_returns_rounded_4dp_for_clean_output():
    lat, lng = bucket_lat_lng(24.0734567, 75.0686123, bucket_meters=300)
    assert len(str(lat)) <= 7  # "24.0734"
    assert len(str(lng)) <= 7


# ------------------------------------------------------------ explainability

def test_explain_match_returns_non_empty_bullets():
    request = {"category": "hardware", "sub_category": "plumbing",
               "product": "Teflon Tape", "alternative_products": [],
               "description": ""}
    shop = {"category": "hardware", "capabilities": ["plumbing", "pipes"]}
    bullets = opportunity_service.explain_match(
        request=request, shop=shop,
        score_breakdown={"category": 1.0, "capability": 0.7, "distance": 0.9, "history": 0.6},
        distance_meters=200, has_inventory_hint=False,
    )
    assert len(bullets) >= 2
    assert any("Same category" in b for b in bullets)
    assert any("200m" in b or "Very close" in b for b in bullets)


# ---------------------------------------------------------- demo determinism

def test_demo_scenario_matches_teflon_tape_request():
    scenario = DEMO_SCENARIOS[0]  # teflon_tape_plumbing
    request = {"product": "Teflon Tape", "category": "hardware"}
    assert _matches_scenario(request, scenario) is True


def test_demo_scenario_does_not_match_unrelated_request():
    scenario = DEMO_SCENARIOS[0]
    request = {"product": "Cotton Shirt", "category": "clothing"}
    assert _matches_scenario(request, scenario) is False


def test_demo_scenario_responses_are_deterministic():
    """No randomness — same scenario always schedules the same shops/prices/delays."""
    s = DEMO_SCENARIOS[0]
    assert s["responses"][0]["shop_name_contains"] == "sharma"
    assert s["responses"][0]["price"] == 30.0
    assert s["responses"][0]["delay_seconds"] == 5
    assert s["responses"][1]["shop_name_contains"] == "gupta"
    assert s["responses"][1]["price"] == 25.0
    assert s["responses"][2]["shop_name_contains"] == "raj"
    assert s["responses"][2]["accepted"] is False


# ------------------------------------------------------- offer sort (Priority 1)

def test_offer_sorting_by_price_ascending_picks_cheapest_first():
    """Pure helper test — the actual sort is in the React frontend, but the
    data shape returned by the API must support these sort keys cleanly."""
    offers = [
        {"id": "1", "price": 50, "distanceMeters": 200, "matchScore": 0.8,
         "trust": {"reliabilityScore": 70}, "responseSeconds": 15},
        {"id": "2", "price": 25, "distanceMeters": 600, "matchScore": 0.6,
         "trust": {"reliabilityScore": 85}, "responseSeconds": 8},
        {"id": "3", "price": 30, "distanceMeters": 1200, "matchScore": 0.7,
         "trust": {"reliabilityScore": 90}, "responseSeconds": 4},
    ]
    # By price ascending
    by_price = sorted(offers, key=lambda o: o["price"])
    assert by_price[0]["id"] == "2"  # ₹25
    # By distance ascending
    by_dist = sorted(offers, key=lambda o: o["distanceMeters"])
    assert by_dist[0]["id"] == "1"  # 200m
    # By reliability descending
    by_rel = sorted(offers, key=lambda o: -o["trust"]["reliabilityScore"])
    assert by_rel[0]["id"] == "3"  # 90
    # By response time ascending
    by_resp = sorted(offers, key=lambda o: o["responseSeconds"])
    assert by_resp[0]["id"] == "3"  # 4s
