"""Customer product request — the single object every input type funnels into."""
from enum import Enum
from typing import Dict, List, Optional

from app.models.inventory import product_key
from app.models.shop import normalize_category
from app.models.user import utcnow
from app.utils.geo import to_geojson_point


class RequestStatus(str, Enum):
    CREATED = "CREATED"
    PROCESSING = "PROCESSING"
    MATCHING = "MATCHING"
    OFFERED = "OFFERED"
    MATCHED = "MATCHED"
    COMPLETED = "COMPLETED"  # customer picked a winning shop (web app)
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class InputType(str, Enum):
    TEXT = "text"
    VOICE = "voice"
    IMAGE = "image"


def build_request_document(
    *, request_id: str, customer_id, telegram_user_id: Optional[int], intent: Dict,
    latitude: float, longitude: float, input_type: str = "text",
    raw_text: str = "", transcript: str = "", max_radius_meters: Optional[int] = None,
) -> Dict:
    now = utcnow()
    return {
        "request_id": request_id,
        "customer_id": customer_id,
        "telegram_user_id": telegram_user_id,
        "raw_text": raw_text,
        "transcript": transcript,
        "input_type": input_type,
        "product": intent.get("product"),
        "product_key": product_key(intent.get("product") or ""),
        "category": normalize_category(intent.get("category")),
        "sub_category": intent.get("sub_category"),
        "quantity": intent.get("quantity", 1),
        "unit": intent.get("unit", "piece"),
        "brand": intent.get("brand"),
        "description": intent.get("description"),
        "confidence": intent.get("confidence", 0.0),
        "alternative_products": intent.get("alternative_products", []) or [],
        "uncertain": bool(intent.get("uncertain", False)),
        "ai_provider": intent.get("provider"),
        "location": to_geojson_point(latitude, longitude),
        "latitude": latitude,
        "longitude": longitude,
        # The ceiling this particular search may expand out to — the customer's
        # own range preference, captured at request time so a later change to
        # their setting never rewrites the history of a search already sent out.
        "max_radius_meters": int(max_radius_meters) if max_radius_meters else None,
        "status": RequestStatus.CREATED.value,
        "matched_count": 0,
        # Multi-offer window: when the first merchant YES arrives we set
        # ``offer_window_expires_at = now + OFFER_WINDOW_SECONDS``. The
        # scheduler (and any later YES) check it to decide when to flush the
        # batched "you have N offers" notification to the customer.
        "offer_window_expires_at": None,
        "customer_notified_at": None,
        # Customer's final pick (one offer only). Persisted so a refresh after
        # selection still shows the chosen shop, and a second selection
        # attempt is rejected by the API.
        "selected_match_id": None,
        "selected_at": None,
        "created_at": now,
        "updated_at": now,
    }


def search_terms(request: Dict) -> List[str]:
    """Product plus alternatives — used for inventory hints and price lookups."""
    terms = [request.get("product") or ""]
    terms.extend(request.get("alternative_products") or [])
    return [t for t in (x.strip() for x in terms) if t]
