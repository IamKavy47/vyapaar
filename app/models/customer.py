"""Customer profile document."""
from typing import Dict, Optional

from app.config.settings import settings
from app.models.user import utcnow
from app.utils.geo import to_geojson_point


def build_customer_document(
    *, user_id, telegram_user_id: Optional[int] = None, latitude: Optional[float] = None,
    longitude: Optional[float] = None, preferences: Optional[Dict] = None,
    search_radius_meters: Optional[int] = None,
) -> Dict:
    now = utcnow()
    doc = {
        "user_id": user_id,
        "telegram_user_id": telegram_user_id,
        "location": None,
        "location_updated_at": None,
        # How far search and browse look by default. 5km out of the box, but the
        # customer can widen or narrow it any time — see location_service.
        "search_radius_meters": search_radius_meters or settings.SEARCH_RADIUS_DEFAULT_METERS,
        "preferences": preferences or {"language": "hinglish", "notify_email": True},
        "created_at": now,
        "updated_at": now,
    }
    if latitude is not None and longitude is not None:
        doc["location"] = to_geojson_point(latitude, longitude)
        doc["location_updated_at"] = now
    return doc
