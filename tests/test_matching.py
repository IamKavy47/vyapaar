"""Zero-inventory matching: category, capability, distance, ranking."""
import pytest

from app.config.settings import settings
from app.models.shop import response_rate
from app.services.merchant_matching import (
    capability_score, category_score, distance_score, need_capabilities, score_merchant,
)


def test_same_category_scores_highest():
    assert category_score("hardware", "hardware") == 1.0


def test_adjacent_category_still_plausible():
    assert 0.5 < category_score("hardware", "plumbing") < 1.0


def test_unrelated_category_scores_low():
    assert category_score("hardware", "clothing") <= 0.2


def test_need_capabilities_includes_subcategory_and_product_tokens(hardware_request):
    needed = need_capabilities(hardware_request)
    assert "plumbing" in needed
    assert "teflon" in needed
    assert "tape" in needed


def test_capability_overlap_scores_well(hardware_request, zero_inventory_shop):
    needed = need_capabilities(hardware_request)
    assert capability_score(needed, zero_inventory_shop) >= 0.6


def test_capability_mismatch_scores_low(hardware_request, unrelated_shop):
    needed = need_capabilities(hardware_request)
    assert capability_score(needed, unrelated_shop) <= 0.2


def test_shop_with_no_declared_capabilities_is_still_weakly_plausible(hardware_request):
    needed = need_capabilities(hardware_request)
    assert capability_score(needed, {"capabilities": [], "subcategories": []}) == 0.2


def test_distance_score_decays():
    assert distance_score(0, 5000) == 1.0
    assert distance_score(5000, 5000) == 0.0
    assert distance_score(2500, 5000) == pytest.approx(0.5)


def test_zero_inventory_shop_beats_unrelated_shop(hardware_request, zero_inventory_shop,
                                                  unrelated_shop):
    """The heart of the product: no inventory, still the best match."""
    near = score_merchant(hardware_request, zero_inventory_shop, 200, 5000)
    far = score_merchant(hardware_request, unrelated_shop, 150, 5000)
    assert near["total"] > far["total"]


def test_closer_shop_wins_when_all_else_equal(hardware_request, zero_inventory_shop):
    near = score_merchant(hardware_request, zero_inventory_shop, 100, 5000)
    far = score_merchant(hardware_request, zero_inventory_shop, 4000, 5000)
    assert near["total"] > far["total"]


def test_score_is_bounded(hardware_request, zero_inventory_shop):
    result = score_merchant(hardware_request, zero_inventory_shop, 0, 5000)
    assert 0.0 <= result["total"] <= 1.0


def test_weights_sum_to_one():
    total = (settings.WEIGHT_CATEGORY + settings.WEIGHT_CAPABILITY
             + settings.WEIGHT_DISTANCE + settings.WEIGHT_HISTORY)
    assert total == pytest.approx(1.0)


def test_new_shop_gets_neutral_history():
    assert response_rate({"notified_count": 0}) == 0.5


def test_responsive_shop_scores_above_neutral():
    assert response_rate({"notified_count": 10, "accepted_count": 8, "declined_count": 2}) > 0.7


def test_radius_steps_reuses_default_progression_within_ceiling():
    from app.services.merchant_matching import _radius_steps_for
    steps = _radius_steps_for(5000)
    assert steps == settings.radius_steps


def test_radius_steps_appends_customer_ceiling_above_defaults():
    from app.services.merchant_matching import _radius_steps_for
    steps = _radius_steps_for(10000)
    assert steps[-1] == 10000
    assert steps == sorted(set(steps))


def test_radius_steps_trims_defaults_above_a_narrower_ceiling():
    from app.services.merchant_matching import _radius_steps_for
    steps = _radius_steps_for(2000)
    assert max(steps) == 2000
    assert 5000 not in steps


def test_radius_steps_handles_ceiling_below_smallest_default():
    from app.services.merchant_matching import _radius_steps_for
    steps = _radius_steps_for(300)
    assert steps == [300]
