"""Merchant match: one notified merchant for one request."""
from enum import Enum
from typing import Dict, Optional

from app.models.user import utcnow


class MatchStatus(str, Enum):
    PENDING = "PENDING"
    NOTIFIED = "NOTIFIED"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    EXPIRED = "EXPIRED"


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
        # Provenance tag: "real" came from a live Telegram button tap or web
        # merchant click; "demo_simulated" was injected by the deterministic
        # demo service so a hackathon audience can see the loop end-to-end
        # without real merchants. Surfaced to the customer as a clear label.
        "source": "real",
        "created_at": now,
    }
