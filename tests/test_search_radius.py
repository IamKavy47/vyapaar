"""Customer search-radius preference: clamping bounds, defaults.

Needs pymongo/bson for the module import (location_service also does DB I/O),
so this suite is skipped in dependency-free environments, same as
test_matching.py and test_config.py.
"""
from app.config.settings import settings
from app.services.location_service import clamp_search_radius


def test_clamp_keeps_value_within_bounds_unchanged():
    assert clamp_search_radius(5000) == 5000


def test_clamp_floors_below_minimum():
    assert clamp_search_radius(100) == settings.SEARCH_RADIUS_MIN_METERS


def test_clamp_ceils_above_maximum():
    assert clamp_search_radius(999_999) == settings.SEARCH_RADIUS_MAX_METERS


def test_clamp_handles_float_input():
    assert clamp_search_radius(3000.7) == 3000


def test_clamp_falls_back_to_default_on_garbage():
    assert clamp_search_radius("not-a-number") == settings.SEARCH_RADIUS_DEFAULT_METERS
    assert clamp_search_radius(None) == settings.SEARCH_RADIUS_DEFAULT_METERS
