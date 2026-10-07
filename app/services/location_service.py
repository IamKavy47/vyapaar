"""Location updates for customers and shops (GeoJSON only, never bare lat/lng)."""
from typing import Dict, Optional, Tuple

from bson import ObjectId

from app.config.settings import settings
from app.database import mongo as m
from app.models.user import utcnow
from app.utils.geo import from_geojson_point, to_geojson_point, valid_coordinates
from app.utils.logging import get_logger

logger = get_logger(__name__)


class InvalidLocationError(ValueError):
    pass


async def update_customer_location(user_id, latitude: float, longitude: float) -> None:
    if not valid_coordinates(latitude, longitude):
        raise InvalidLocationError("Coordinates are out of range.")
    now = utcnow()
    await m.customers().update_one(
        {"user_id": ObjectId(str(user_id))},
        {"$set": {
            "location": to_geojson_point(latitude, longitude),
            "location_updated_at": now,
            "updated_at": now,
        }},
        upsert=True,
    )
    logger.info("customer location updated | user=%s", user_id)


async def update_shop_location(user_id, latitude: float, longitude: float,
                               address: Optional[str] = None) -> None:
    if not valid_coordinates(latitude, longitude):
        raise InvalidLocationError("Coordinates are out of range.")
    update = {
        "location": to_geojson_point(latitude, longitude),
        "updated_at": utcnow(),
    }
    if address:
        update["address"] = address
    await m.shops().update_one({"user_id": ObjectId(str(user_id))}, {"$set": update})
    logger.info("shop location updated | user=%s", user_id)


async def get_customer_location(user_id) -> Optional[Tuple[float, float]]:
    doc = await m.customers().find_one({"user_id": ObjectId(str(user_id))})
    if not doc:
        return None
    return from_geojson_point(doc.get("location"))


async def get_shop_location(user_id) -> Optional[Tuple[float, float]]:
    doc = await m.shops().find_one({"user_id": ObjectId(str(user_id))})
    if not doc:
        return None
    return from_geojson_point(doc.get("location"))


def location_of(doc: Dict) -> Optional[Tuple[float, float]]:
    return from_geojson_point((doc or {}).get("location"))


def clamp_search_radius(meters) -> int:
    """Keep a customer's range inside sane bounds, whatever they typed."""
    try:
        value = int(float(meters))
    except (TypeError, ValueError):
        value = settings.SEARCH_RADIUS_DEFAULT_METERS
    return max(settings.SEARCH_RADIUS_MIN_METERS, min(settings.SEARCH_RADIUS_MAX_METERS, value))


async def get_search_radius(user_id) -> int:
    """A customer's own search/browse range. 5km by default, until they change it."""
    doc = await m.customers().find_one({"user_id": ObjectId(str(user_id))})
    value = (doc or {}).get("search_radius_meters")
    return clamp_search_radius(value) if value else settings.SEARCH_RADIUS_DEFAULT_METERS


async def set_search_radius(user_id, meters) -> int:
    """Persist a new range. Returns the clamped value actually stored."""
    clamped = clamp_search_radius(meters)
    await m.customers().update_one(
        {"user_id": ObjectId(str(user_id))},
        {"$set": {"search_radius_meters": clamped, "updated_at": utcnow()}},
        upsert=True,
    )
    logger.info("search radius updated | user=%s radius=%dm", user_id, clamped)
    return clamped
