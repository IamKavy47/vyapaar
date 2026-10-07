"""Demand events. A merchant's 'NO' is not a dead end — it is market data."""
from typing import Dict, Optional

from app.models.inventory import product_key
from app.models.shop import normalize_category
from app.models.user import utcnow
from app.utils.geo import to_geojson_point


def build_demand_event(
    *, request_id: str, merchant_id, product: str, category: Optional[str],
    sub_category: Optional[str], latitude: float, longitude: float,
    response: str, price: Optional[float] = None,
) -> Dict:
    return {
        "request_id": request_id,
        "merchant_id": merchant_id,
        "product": product,
        "product_key": product_key(product or ""),
        "category": normalize_category(category),
        "sub_category": sub_category,
        "location": to_geojson_point(latitude, longitude),
        "latitude": latitude,
        "longitude": longitude,
        "response": response,  # available | unavailable | no_response
        "price": price,
        "created_at": utcnow(),
    }
