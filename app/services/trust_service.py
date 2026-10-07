"""Explainable merchant trust score and freshness labels.

Pure functions only — no database calls — so they're trivial to unit-test.
The web API layer (app.api.web) is responsible for fetching the inputs
(shop counters, recent merchant_matches for response-time history) and
passing them in here.
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from app.config.settings import settings
from app.models.shop import response_rate


def _to_seconds(value: Optional[datetime], reference: Optional[datetime] = None) -> Optional[int]:
    """Difference in whole seconds between two datetimes, None if either missing."""
    if value is None:
        return None
    ref = reference or datetime.now(tz=value.tzinfo) if value.tzinfo else datetime.utcnow()
    try:
        delta = (value - ref).total_seconds()
    except Exception:
        return None
    if delta < 0:
        # response came before notification (clock skew / old data) — treat as fast
        return 0
    return int(delta)


def average_response_seconds(response_times_seconds: List[int]) -> Optional[int]:
    """Median response time across a list of per-match seconds (None if empty)."""
    if not response_times_seconds:
        return None
    ordered = sorted(response_times_seconds)
    midpoint = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return int(ordered[midpoint])
    return int((ordered[midpoint - 1] + ordered[midpoint]) / 2)


def compute_trust_score(
    *,
    notified_count: int,
    accepted_count: int,
    declined_count: int,
    completed_selections: int = 0,
    response_times_seconds: Optional[List[int]] = None,
    is_verified: bool = False,
    account_age_days: Optional[int] = None,
) -> Dict:
    """Deterministic, fully explainable merchant trust score.

    Returns a dict with:
      - responseRate: 0.0–1.0 (answered / notified), neutral 0.5 for new shops
      - acceptanceRate: 0.0–1.0 (accepted / answered)
      - averageResponseSeconds: int or None
      - reliabilityScore: 0–100 integer
      - label: short Hinglish phrase ("Usually responds quickly" etc.)
      - isNewMerchant: bool
      - sampleSize: int (answered count)
      - reason: human-readable explanation

    Guards:
      - Shops with fewer than TRUST_MIN_SAMPLE responses get the
        "New merchant" label and a neutral score of 50 — never a low score
        that would unfairly hurt a new shop.
    """
    answered = accepted_count + declined_count
    sample_size = answered

    # Response rate: answered / notified, neutral 0.5 for new shops (matches
    # the existing response_rate helper in shop.py).
    rr = response_rate({
        "notified_count": notified_count,
        "accepted_count": accepted_count,
        "declined_count": declined_count,
    })

    # Acceptance rate: of those answered, how often said YES.
    if answered > 0:
        ar = max(0.0, min(1.0, accepted_count / answered))
    else:
        ar = 0.5

    # Response time: median across recent matches.
    avg_resp = average_response_seconds(response_times_seconds or [])

    is_new = sample_size < settings.TRUST_MIN_SAMPLE

    if is_new:
        # Neutral score + clear label. Do NOT hand a low score to a shop that
        # simply hasn't had a chance to respond yet.
        return {
            "responseRate": round(rr, 2),
            "acceptanceRate": round(ar, 2),
            "averageResponseSeconds": avg_resp,
            "reliabilityScore": 50,
            "label": "New merchant",
            "isNewMerchant": True,
            "sampleSize": sample_size,
            "isVerified": bool(is_verified),
            "reason": (
                f"Abhi sirf {sample_size} response mili hai — bharosemand score "
                "kaafi data ke baad banega. Isliye beech ka score (50/100)."
                if sample_size > 0
                else "Abhi tak koi response nahi mili — nayi dukaan hai. Beech ka score (50/100)."
            ),
        }

    # Score formula — explainable in plain language:
    #   50% weight: response rate (did they answer at all?)
    #   25% weight: acceptance rate (when they answered, did theyre say YES?)
    #   15% weight: response speed (fast = full marks, slow = 0)
    #   10% weight: verified status + completed selections bonus
    speed_score = _speed_score(avg_resp)
    completed_bonus = min(1.0, completed_selections / 5.0) if completed_selections else 0.0
    verified_bonus = 1.0 if is_verified else 0.0
    reputation_component = 0.5 * completed_bonus + 0.5 * verified_bonus

    raw = (
        0.50 * rr
        + 0.25 * ar
        + 0.15 * speed_score
        + 0.10 * reputation_component
    )
    score = int(round(max(0.0, min(1.0, raw)) * 100))

    if avg_resp is not None and avg_resp <= settings.TRUST_RESPONSE_TIME_FAST_SEC:
        speed_label = "usually responds quickly"
    elif avg_resp is not None and avg_resp <= settings.TRUST_RESPONSE_TIME_OK_SEC:
        speed_label = "responds in reasonable time"
    elif avg_resp is not None:
        speed_label = "may take a while to respond"
    else:
        speed_label = "response time not yet measured"

    label = _trust_label(score, speed_label)

    reason_bits = []
    if rr >= 0.85:
        reason_bits.append(f"{int(rr * 100)}% requests ka jawab deti hai")
    elif rr >= 0.6:
        reason_bits.append(f"{int(rr * 100)}% requests ka jawab deti hai")
    if ar >= 0.7:
        reason_bits.append(f"{int(ar * 100)}% baar YES bolti hai")
    if avg_resp is not None and avg_resp <= settings.TRUST_RESPONSE_TIME_FAST_SEC:
        reason_bits.append(f"average response {avg_resp}s")
    if completed_selections > 0:
        reason_bits.append(f"{completed_selections} customer ne select kiya")
    if is_verified:
        reason_bits.append("verified shop")
    if not reason_bits:
        reason_bits.append("limited history so far")
    reason = (
        f"Bharosemand score {score}/100 — " + ", ".join(reason_bits) + "."
    )

    return {
        "responseRate": round(rr, 2),
        "acceptanceRate": round(ar, 2),
        "averageResponseSeconds": avg_resp,
        "reliabilityScore": score,
        "label": label,
        "isNewMerchant": False,
        "sampleSize": sample_size,
        "isVerified": bool(is_verified),
        "reason": reason,
    }


def _speed_score(avg_resp_seconds: Optional[int]) -> float:
    """0.0–1.0. Fast (< FAST) = 1.0, slow (> OK) = 0.0, linear between."""
    if avg_resp_seconds is None:
        return 0.5
    fast = settings.TRUST_RESPONSE_TIME_FAST_SEC
    ok = settings.TRUST_RESPONSE_TIME_OK_SEC
    if avg_resp_seconds <= fast:
        return 1.0
    if avg_resp_seconds >= ok:
        return 0.0
    return 1.0 - (avg_resp_seconds - fast) / max(1, ok - fast)


def _trust_label(score: int, speed_label: str) -> str:
    """One-line Hinglish label suitable for a badge on the offer card."""
    if score >= 80:
        return f"Bharosemand · {speed_label}"
    if score >= 60:
        return f"Achhi dukaan · {speed_label}"
    if score >= 40:
        return f"Theek-thaak · {speed_label}"
    return "Nayi dukaan"


def freshness_label(*, responded_at: Optional[datetime], notified_at: Optional[datetime],
                    has_inventory_hint: bool, inventory_updated_at: Optional[datetime] = None,
                    has_price: bool = False, now: Optional[datetime] = None) -> Dict:
    """Human-readable freshness signals shown on the customer's offer card.

    Two labels are produced because they answer different questions:
      - statusLabel: "Confirmed just now" / "Confirmed 5 minutes ago" /
                     "Shop-listed stock" — what the merchant just told us.
      - priceLabel: "Price confirmed by merchant" / "Price not provided" /
                    "Stock price (not merchant-confirmed)" — provenance of
                    the price we display, so customers know what to trust.
    """
    now = now or datetime.utcnow()
    if responded_at is not None:
        if now.tzinfo is None and responded_at.tzinfo is not None:
            now = now.replace(tzinfo=responded_at.tzinfo)
        delta = (now - responded_at).total_seconds()
        if delta < 0:
            delta = 0
        if delta < 60:
            status_label = "Confirmed just now"
        elif delta < 3600:
            status_label = f"Confirmed {int(delta // 60)} minutes ago"
        elif delta < 86400:
            status_label = f"Confirmed {int(delta // 3600)} hours ago"
        else:
            status_label = f"Confirmed {int(delta // 86400)} days ago"
        price_label = (
            "Price confirmed by merchant" if has_price else "Price not provided"
        )
    elif has_inventory_hint:
        if inventory_updated_at is not None:
            if now.tzinfo is None and inventory_updated_at.tzinfo is not None:
                now = now.replace(tzinfo=inventory_updated_at.tzinfo)
            delta_inv = (now - inventory_updated_at).total_seconds()
            if delta_inv < 0:
                delta_inv = 0
            if delta_inv < 86400:
                status_label = "Shop-listed stock"
            elif delta_inv < 7 * 86400:
                status_label = f"Inventory updated {int(delta_inv // 86400)} day(s) ago"
            else:
                status_label = "Inventory may be stale"
        else:
            status_label = "Shop-listed stock"
        price_label = (
            "Stock price (not merchant-confirmed)" if has_price else "Price not provided"
        )
    else:
        status_label = "Awaiting merchant response"
        price_label = "Price not provided"

    return {
        "statusLabel": status_label,
        "priceLabel": price_label,
        "respondedSecondsAgo": int((now - responded_at).total_seconds()) if responded_at else None,
    }
