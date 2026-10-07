"""Shared test fixtures. Unit tests here run without MongoDB or API keys."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("SESSION_SECRET", "test-secret-key-for-tests-only")
os.environ.setdefault("MONGODB_DATABASE", "vyapaar_mitra_test")

import pytest  # noqa: E402


@pytest.fixture
def hardware_request():
    return {
        "request_id": "REQ-TEST01",
        "product": "Teflon Tape",
        "category": "hardware",
        "sub_category": "plumbing",
        "description": "White PTFE tape used to seal pipe threads",
        "alternative_products": ["PTFE Thread Seal Tape"],
        "quantity": 1,
        "unit": "piece",
        "latitude": 24.0734,
        "longitude": 75.0686,
    }


@pytest.fixture
def zero_inventory_shop():
    """Sharma Hardware: no products uploaded, ever."""
    return {
        "_id": "shop-sharma",
        "shop_name": "Sharma Hardware",
        "category": "hardware",
        "capabilities": ["plumbing", "pipes", "fittings", "tools", "sealants"],
        "subcategories": [],
        "is_active": True,
        "notified_count": 10,
        "accepted_count": 6,
        "declined_count": 3,
    }


@pytest.fixture
def unrelated_shop():
    return {
        "_id": "shop-fashion",
        "shop_name": "Fashion Point",
        "category": "clothing",
        "capabilities": ["apparel", "fabric", "tailoring"],
        "subcategories": [],
        "is_active": True,
        "notified_count": 0,
        "accepted_count": 0,
        "declined_count": 0,
    }
