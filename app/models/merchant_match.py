"""Merchant match: one notified merchant for one request."""
from enum import Enum
from typing import Dict, Optional

from app.models.user import utcnow


class MatchStatus(str, Enum):
    PENDING = "pending"
    NOTIFIED = "notified"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"
    SELECTED = "selected"
    SUPERSEDED = "superseded"


def build_match_document(
    *, request_id: str, merchant_id, distance_meters: float, match_score: float,
    score_breakdown: Optional[Dict] = None,
) -> Dict:
    now = utcnow()
    return {
        "request_id": request_id,
        "merchant_id": merchant_id,
        "distance_meters": round(float(distance_meters), 1),
        "match_score": round(float(match_score), 4),
        "score_breakdown": score_breakdown or {},
        "status": MatchStatus.PENDING.value,
        "price": None,
        "notified_at": None,
        "responded_at": None,
        "created_at": now,
    }
