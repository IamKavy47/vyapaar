"""Geo helpers: Haversine + GeoJSON conversion."""
from math import asin, cos, radians, sin, sqrt
from typing import Dict, Optional, Tuple

EARTH_RADIUS_METERS = 6_371_000.0


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two WGS84 points, in metres."""
    p1, p2 = radians(lat1), radians(lat2)
    dphi = p2 - p1
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_METERS * asin(min(1.0, sqrt(a)))


def to_geojson_point(latitude: float, longitude: float) -> Dict:
    """MongoDB 2dsphere expects [longitude, latitude] — never the other way round."""
    return {"type": "Point", "coordinates": [float(longitude), float(latitude)]}


def from_geojson_point(point: Optional[Dict]) -> Optional[Tuple[float, float]]:
    """Returns (latitude, longitude) or None."""
    if not point:
        return None
    coords = point.get("coordinates") or []
    if len(coords) != 2:
        return None
    return float(coords[1]), float(coords[0])


def valid_coordinates(latitude: float, longitude: float) -> bool:
    return -90.0 <= float(latitude) <= 90.0 and -180.0 <= float(longitude) <= 180.0


def humanize_distance(meters: float) -> str:
    if meters < 1000:
        return f"~{int(round(meters / 10.0) * 10)}m"
    return f"~{meters / 1000.0:.1f}km"


def navigation_link(latitude: float, longitude: float) -> str:
    """Turn-by-turn directions from wherever the user currently is.

    Google Maps' universal URL opens the native app on Android and iOS and falls
    back to the browser everywhere else, so one link covers every customer.
    """
    return (
        "https://www.google.com/maps/dir/?api=1"
        f"&destination={float(latitude):.6f},{float(longitude):.6f}"
    )


def map_pin_link(latitude: float, longitude: float) -> str:
    """A dropped pin — 'where is this shop', without starting navigation."""
    return (
        "https://www.google.com/maps/search/?api=1"
        f"&query={float(latitude):.6f},{float(longitude):.6f}"
    )
