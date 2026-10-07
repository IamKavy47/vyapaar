"""Shop document, category taxonomy and the capability map.

The capability map is the heart of zero-inventory matching: it lets us answer
"who nearby could plausibly satisfy this need?" without a single product row.
"""
from enum import Enum
from typing import Dict, List, Optional

from app.models.user import utcnow
from app.utils.geo import to_geojson_point

CATEGORIES: List[str] = [
    "kirana", "hardware", "plumbing", "electrical", "medical", "clothing",
    "stationery", "mobile_electronics", "repair", "bakery_food", "cosmetics",
    "general_store", "other",
]

# Service sub-categories — when shop_type=service, the shopkeeper picks one
# of these as their service line. They map to existing CATEGORY_CAPABILITIES
# so the zero-inventory matching still works on capabilities.
SERVICE_LINES: List[str] = [
    "plumber", "electrician", "tailor", "carpenter", "painter",
    "appliance_repair", "mobile_repair", "beautician", "tutor",
    "delivery", "other_service",
]

SERVICE_LINE_LABELS: Dict[str, str] = {
    "plumber": "Plumber", "electrician": "Electrician", "tailor": "Tailor",
    "carpenter": "Carpenter", "painter": "Painter",
    "appliance_repair": "Appliance Repair", "mobile_repair": "Mobile Repair",
    "beautician": "Beautician", "tutor": "Tutor",
    "delivery": "Delivery", "other_service": "Other Service",
}

# Category affinity for service lines — a plumber can serve plumbing
# requests, an electrician can serve electrical requests, etc.
SERVICE_LINE_AFFINITY: Dict[str, str] = {
    "plumber": "plumbing",
    "electrician": "electrical",
    "tailor": "clothing",
    "carpenter": "hardware",
    "painter": "hardware",
    "appliance_repair": "repair",
    "mobile_repair": "mobile_electronics",
    "beautician": "cosmetics",
    "tutor": "stationery",
    "delivery": "general_store",
    "other_service": "other",
}

CATEGORY_LABELS: Dict[str, str] = {
    "kirana": "Kirana", "hardware": "Hardware", "plumbing": "Plumbing",
    "electrical": "Electrical", "medical": "Medical", "clothing": "Clothing",
    "stationery": "Stationery", "mobile_electronics": "Mobile & Electronics",
    "repair": "Repair", "bakery_food": "Bakery / Food", "cosmetics": "Cosmetics",
    "general_store": "General Store", "other": "Other",
}

# Default capability suggestions offered during onboarding.
CATEGORY_CAPABILITIES: Dict[str, List[str]] = {
    "kirana": ["groceries", "staples", "snacks", "beverages", "household", "cleaning"],
    "hardware": ["plumbing", "pipes", "fittings", "tools", "sealants", "paints", "fasteners", "adhesives"],
    "plumbing": ["pipes", "fittings", "sealants", "taps", "sanitary", "plumbing"],
    "electrical": ["wires", "switches", "bulbs", "tape", "fans", "electrical", "adapters"],
    "medical": ["medicines", "otc", "first_aid", "wellness", "surgical"],
    "clothing": ["apparel", "fabric", "tailoring", "footwear"],
    "stationery": ["paper", "pens", "notebooks", "printing", "art_supplies", "adhesives"],
    "mobile_electronics": ["mobiles", "chargers", "cables", "accessories", "repair", "adapters"],
    "repair": ["repair", "spare_parts", "servicing", "tools"],
    "bakery_food": ["bakery", "snacks", "sweets", "beverages", "ready_food"],
    "cosmetics": ["skincare", "haircare", "beauty", "personal_care"],
    "general_store": ["household", "groceries", "stationery", "cleaning", "misc", "adhesives"],
    "other": ["misc"],
}

# Categories that can plausibly serve a request from another category.
CATEGORY_AFFINITY: Dict[str, Dict[str, float]] = {
    "hardware": {"hardware": 1.0, "plumbing": 0.85, "electrical": 0.6, "general_store": 0.35, "repair": 0.4},
    "plumbing": {"plumbing": 1.0, "hardware": 0.9, "general_store": 0.25},
    "electrical": {"electrical": 1.0, "hardware": 0.7, "mobile_electronics": 0.45, "general_store": 0.3},
    "kirana": {"kirana": 1.0, "general_store": 0.85, "bakery_food": 0.4, "cosmetics": 0.3},
    "medical": {"medical": 1.0, "general_store": 0.2, "cosmetics": 0.25},
    "clothing": {"clothing": 1.0, "general_store": 0.2},
    "stationery": {"stationery": 1.0, "general_store": 0.6, "kirana": 0.3},
    "mobile_electronics": {"mobile_electronics": 1.0, "electrical": 0.4, "repair": 0.5},
    "repair": {"repair": 1.0, "hardware": 0.5, "mobile_electronics": 0.5},
    "bakery_food": {"bakery_food": 1.0, "kirana": 0.5, "general_store": 0.4},
    "cosmetics": {"cosmetics": 1.0, "general_store": 0.4, "medical": 0.3, "kirana": 0.25},
    "general_store": {"general_store": 1.0, "kirana": 0.8, "stationery": 0.4},
    "other": {"other": 1.0, "general_store": 0.5},
}


def normalize_category(value: Optional[str]) -> str:
    if not value:
        return "other"
    key = value.strip().lower().replace(" & ", "_").replace(" ", "_").replace("-", "_")
    aliases = {
        "mobile": "mobile_electronics", "electronics": "mobile_electronics",
        "mobile_and_electronics": "mobile_electronics", "grocery": "kirana",
        "groceries": "kirana", "food": "bakery_food", "bakery": "bakery_food",
        "pharmacy": "medical", "chemist": "medical", "general": "general_store",
        "hardware_store": "hardware", "stationary": "stationery",
        # web app (LocalMart UI) category keys
        "vegetables": "kirana", "sabzi": "kirana", "dairy": "bakery_food",
        "tailor": "clothing",
    }
    key = aliases.get(key, key)
    return key if key in CATEGORIES else "other"


def category_label(value: Optional[str]) -> str:
    return CATEGORY_LABELS.get(normalize_category(value), "Other")


class ShopType(str, Enum):
    SHOP = "shop"          # fixed location with products (kirana, hardware, etc.)
    VENDOR = "vendor"      # street vendor / thela — mobile or temporary
    SERVICE = "service"    # service provider (plumber, electrician, tailor, repair)


def build_shop_document(
    *, user_id, shop_name: str, phone: str, category: str,
    subcategories: Optional[List[str]] = None, capabilities: Optional[List[str]] = None,
    latitude: Optional[float] = None, longitude: Optional[float] = None,
    address: str = "", description: str = "", telegram_user_id: Optional[int] = None,
    is_verified: bool = False,
    shop_type: str = ShopType.SHOP.value,
    service_line: Optional[str] = None,
) -> Dict:
    now = utcnow()
    category = normalize_category(category)
    caps = capabilities if capabilities else CATEGORY_CAPABILITIES.get(category, [])
    # For service providers, also add the service line as a capability so
    # zero-inventory matching on "plumber" / "electrician" works.
    if shop_type == ShopType.SERVICE.value and service_line:
        caps = list(caps) + [service_line]
        # Also map the service line to its category affinity so category_score
        # gives full marks when a customer asks for plumbing and this is a
        # plumber.
        affinity_cat = SERVICE_LINE_AFFINITY.get(service_line)
        if affinity_cat and affinity_cat != category:
            category = affinity_cat
    doc = {
        "user_id": user_id,
        "telegram_user_id": telegram_user_id,
        "shop_name": shop_name.strip(),
        "phone": (phone or "").strip(),
        "category": category,
        "subcategories": [s.strip().lower() for s in (subcategories or [])],
        "capabilities": sorted({c.strip().lower() for c in caps if c.strip()}),
        "location": None,
        "address": address.strip(),
        "description": description.strip(),
        "is_active": True,
        "is_verified": is_verified,
        # shop_type: "shop" (fixed location with products) | "vendor" (street
        # vendor / thela) | "service" (plumber, electrician, tailor, repair).
        # The is_verified gate in find_candidates applies to ALL types —
        # a street vendor still needs phone OTP + a geo-tagged photo of
        # their thela/cart for the same safety bar as a shop.
        "shop_type": shop_type,
        "service_line": service_line if shop_type == ShopType.SERVICE.value else None,
        "shopfront_photo_url": None,
        "photo_browser_location": None,
        "photo_exif_location": None,
        "photo_uploaded_at": None,
        "photo_approved_at": None,
        "verification_status": "pending",
        "accepted_count": 0,
        "declined_count": 0,
        "notified_count": 0,
        "created_at": now,
        "updated_at": now,
    }
    if latitude is not None and longitude is not None:
        doc["location"] = to_geojson_point(latitude, longitude)
    return doc


def response_rate(shop: Dict) -> float:
    """Historical willingness to answer requests; neutral 0.5 for new shops."""
    notified = int(shop.get("notified_count") or 0)
    if notified <= 0:
        return 0.5
    answered = int(shop.get("accepted_count") or 0) + int(shop.get("declined_count") or 0)
    accepted = int(shop.get("accepted_count") or 0)
    return max(0.0, min(1.0, 0.5 * (answered / notified) + 0.5 * (accepted / max(1, answered))))
