"""Explainable stock opportunity recommendations.

A stock opportunity is a deterministic ranking of "products your
neighbourhood keeps asking for that you do not currently stock". It is NOT a
sales forecast — we never claim "if you stock this you will sell N units".

Inputs (all from the existing collections, computed by the API layer):
  - uniqueRequests: count of distinct customer requests for a product within
    the merchant's opportunity radius in the last `days` days.
  - unavailableRequests: how many of those got NO merchant YES (closed as
    no_match / expired with no acceptance).
  - availableRequests: how many got at least one YES.
  - trendRatio: (last 7d unique requests) / max(1, previous 7d unique requests).
  - averageSearchDistanceMeters: typical distance customers had to look for it.
  - nearbyInventoryCoverage: count of distinct nearby shops that already list
    this product in their inventory.
  - merchantCategoryAffinity: 0.0–1.0 from CATEGORY_AFFINITY between the
    product's category and the merchant's shop category.
  - merchantAlreadyStocks: True if this merchant already has the item in stock.

The score is a weighted sum of normalised sub-scores. Every weight is
configurable; every input is shown to the merchant; no ML is involved.
"""
from typing import Dict, List, Optional

from app.config.settings import settings


def opportunity_score(
    *,
    product: str,
    category: Optional[str],
    unique_requests: int,
    unavailable_requests: int,
    available_requests: int,
    trend_ratio: Optional[float],
    average_search_distance_meters: Optional[int],
    nearby_inventory_coverage: int,
    merchant_category_affinity: float,
    merchant_already_stocks: bool = False,
) -> Dict:
    """Compute one opportunity row. Pure function — no I/O.

    Returns a dict matching the JSON shape in the spec, plus the reason
    string and a per-factor breakdown so the UI can render the explanation.
    """
    # Hide products that already match the merchant's category poorly — we
    # never recommend products unrelated to the merchant's line of business.
    if merchant_category_affinity < 0.2:
        return _empty_opportunity(product, category,
                                  reason="Yeh product aapki shop category se related nahi hai.")

    # Don't recommend something the merchant already stocks.
    if merchant_already_stocks:
        return _empty_opportunity(product, category,
                                  reason="Aap is product ko pehle se stock karte hain.")

    # Minimum demand threshold — too thin a signal is noise, not opportunity.
    if unique_requests < settings.OPPORTUNITY_MIN_REQUESTS:
        return _empty_opportunity(product, category,
                                  reason=f"Abhi sirf {unique_requests} request mili — "
                                         "mauka pakka banane ke liye aur data chahiye.")

    total = unique_requests
    if total <= 0:
        return _empty_opportunity(product, category,
                                  reason="Abhi koi demand data nahi hai.")
    unavailable_rate = max(0.0, min(1.0, unavailable_requests / total))
    available_rate = max(0.0, min(1.0, available_requests / total))

    # Demand volume sub-score (0..1) — saturates around 10 requests so a single
    # viral product doesn't dominate the ranking.
    volume = min(1.0, unique_requests / 10.0)
    # Unmet rate sub-score: higher miss rate = bigger opportunity.
    unmet = unavailable_rate
    # Trend sub-score: rising demand is more interesting than flat.
    if trend_ratio is None:
        trend_score = 0.5
        trend_label = "stable"
    elif trend_ratio >= 1.5:
        trend_score = 1.0
        trend_label = "rising"
    elif trend_ratio >= 1.0:
        trend_score = 0.6
        trend_label = "rising"
    elif trend_ratio >= 0.5:
        trend_score = 0.3
        trend_label = "stable"
    else:
        trend_score = 0.1
        trend_label = "falling"
    # Search difficulty: longer search radius = harder to find = bigger
    # opportunity if the merchant stocks it nearby.
    if average_search_distance_meters and average_search_distance_meters > 0:
        search_difficulty = min(1.0, average_search_distance_meters / 5000.0)
    else:
        search_difficulty = 0.3
    # Coverage inverse: fewer nearby shops list it = bigger opportunity.
    coverage = max(0.0, 1.0 - min(1.0, nearby_inventory_coverage / 5.0))
    # Category fit: passed the gate above, score itself contributes.
    fit = merchant_category_affinity

    raw = (
        0.30 * volume
        + 0.25 * unmet
        + 0.15 * trend_score
        + 0.10 * search_difficulty
        + 0.10 * coverage
        + 0.10 * fit
    )
    score = int(round(max(0.0, min(1.0, raw)) * 100))

    # Recommended quantity is a heuristic, NOT a sales forecast. We say
    # "approximately X units" derived from recent unique demand and a safety
    # margin; the merchant must confirm before adding stock.
    recommended_qty = _recommend_quantity(unique_requests, unavailable_rate)

    reason = _build_reason(
        product=product, unique_requests=unique_requests,
        unavailable_requests=unavailable_requests, unavailable_rate=unavailable_rate,
        trend_label=trend_label, nearby_coverage=nearby_inventory_coverage,
        avg_distance=average_search_distance_meters,
    )

    return {
        "product": product,
        "category": category,
        "uniqueRequests": unique_requests,
        "unavailableRequests": unavailable_requests,
        "availableRequests": available_requests,
        "unavailableRate": round(unavailable_rate, 2),
        "trend": trend_label,
        "trendRatio": round(trend_ratio, 2) if trend_ratio is not None else None,
        "averageSearchDistanceMeters": average_search_distance_meters,
        "nearbyInventoryCoverage": nearby_inventory_coverage,
        "merchantCategoryAffinity": round(merchant_category_affinity, 2),
        "merchantAlreadyStocks": merchant_already_stocks,
        "opportunityScore": score,
        "recommendedQuantity": recommended_qty,
        "reason": reason,
        "breakdown": {
            "volume": round(volume, 2),
            "unmet": round(unmet, 2),
            "trend": round(trend_score, 2),
            "searchDifficulty": round(search_difficulty, 2),
            "coverageGap": round(coverage, 2),
            "categoryFit": round(fit, 2),
        },
    }


def _recommend_quantity(unique_requests: int, unavailable_rate: float) -> int:
    """Heuristic suggested stocking quantity. Capped and clearly labelled as
    an estimate — never presented as guaranteed sales."""
    if unique_requests <= 0:
        return 0
    # Start with the demand seen in the window, scale by unmet rate so we
    # only suggest stocking what isn't currently served.
    base = max(1, int(unique_requests * unavailable_rate))
    # Add a small buffer so the merchant doesn't sell out on day one, then
    # cap at a sensible shop-floor number.
    suggested = int(base * 1.5) + 5
    return max(5, min(suggested, 50))


def _build_reason(*, product, unique_requests, unavailable_requests,
                  unavailable_rate, trend_label, nearby_coverage, avg_distance) -> str:
    bits = [
        f"{unique_requests} nearby customers ne is product ki request bheji",
    ]
    if unavailable_requests > 0:
        bits.append(f"{int(unavailable_rate * 100)}% ko nahi mila")
    if trend_label == "rising":
        bits.append("demand badh rahi hai")
    elif trend_label == "falling":
        bits.append("demand ghat rahi hai")
    if nearby_coverage is not None:
        if nearby_coverage == 0:
            bits.append("aas-paas koi bhi dukaan is product ko stock nahi karti")
        else:
            bits.append(f"sirf {nearby_coverage} nearby dukaan(s) is product ko list karti hain")
    if avg_distance:
        bits.append(f"customers average {avg_distance}m door dhoondhte hain")
    return ", ".join(bits) + "."


def _empty_opportunity(product: str, category: Optional[str], *, reason: str) -> Dict:
    return {
        "product": product,
        "category": category,
        "uniqueRequests": 0,
        "unavailableRequests": 0,
        "availableRequests": 0,
        "unavailableRate": 0.0,
        "trend": "stable",
        "trendRatio": None,
        "averageSearchDistanceMeters": None,
        "nearbyInventoryCoverage": 0,
        "merchantCategoryAffinity": 0.0,
        "merchantAlreadyStocks": False,
        "opportunityScore": 0,
        "recommendedQuantity": 0,
        "reason": reason,
        "breakdown": None,
    }


def sort_opportunities(rows: List[Dict]) -> List[Dict]:
    """Sort opportunity rows by score descending, then by uniqueRequests desc.

    Empty (filtered-out) rows are dropped before sorting.
    """
    eligible = [r for r in rows if r.get("opportunityScore", 0) > 0]
    eligible.sort(key=lambda r: (-r["opportunityScore"], -r["uniqueRequests"]))
    return eligible


def explain_match(*, request: Dict, shop: Dict, score_breakdown: Dict,
                  distance_meters: float, has_inventory_hint: bool = False,
                  trust_label: Optional[str] = None) -> List[str]:
    """Short, plain-language "why was this shop recommended" bullets.

    Uses the same score breakdown produced by merchant_matching.score_merchant
    so the explanation is consistent with the ranking the customer sees.
    """
    bullets: List[str] = []
    cat_score = score_breakdown.get("category", 0.0)
    cap_score = score_breakdown.get("capability", 0.0)
    if cat_score >= 0.8:
        bullets.append("Same category as your request")
    elif cat_score >= 0.4:
        bullets.append("Adjacent category — usually carries this")
    if cap_score >= 0.6:
        bullets.append("Capability match with the requested item")
    if distance_meters is not None:
        if distance_meters < 500:
            bullets.append(f"Very close — about {int(distance_meters)}m away")
        elif distance_meters < 2000:
            bullets.append(f"Within walking distance — about {int(distance_meters / 100) * 100}m away")
        else:
            bullets.append(f"About {distance_meters / 1000:.1f}km away")
    if has_inventory_hint:
        bullets.append("Already lists this product in inventory")
    if trust_label:
        bullets.append(trust_label)
    if score_breakdown.get("history", 0.0) >= 0.7:
        bullets.append("Strong response history")
    if not bullets:
        bullets.append("Within your search range and category")
    return bullets
