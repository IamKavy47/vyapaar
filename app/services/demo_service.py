"""Deterministic demo simulator.

When DEMO_MODE is true and no live Telegram bot is polling, this module
schedules simulated merchant YES/NO responses for newly-created requests
that match a known scenario. Each simulated response is tagged
``source="demo_simulated"`` on the merchant_matches row and clearly labelled
in the customer UI as "Demo-simulated merchant response".

The scenarios are hardcoded and deterministic — no fake randomness, no fake
analytics. The simulator never claims to be a real customer or real merchant.

The flagship scenario (Teflon Tape / plumbing) walks the demo through the
entire loop end-to-end:

    Customer: "Mere sink ke neeche pipe leak ho raha hai, safed tape chahiye."
    Intent  : Teflon Tape  (Hardware category)
    Shops   : Sharma Hardware (zero inventory, capable, ~200m, YES ₹30)
              Gupta Electricals (inventory listed, ₹25, ~650m, YES ₹25)
              Raj Plumbing (capable, ~1.2km, NO — doesn't stock)
    Outcome : customer compares two YES offers, picks one, the NO becomes
              demand intelligence -> Raj Plumbing sees a stock opportunity.
"""
import asyncio
import logging
from typing import Dict, List, Optional

from app.config.settings import settings
from app.models.user import utcnow

logger = logging.getLogger(__name__)


# Each scenario identifies the request by product-keyword + category, then
# looks up the matching merchant by a substring of the shop_name. The
# response is scheduled `delay_seconds` after the request was matched.
#
# Quantities/prices are deliberately small integers so the demo numbers are
# easy to read out loud during the pitch.
DEMO_SCENARIOS: List[Dict] = [
    {
        "name": "teflon_tape_plumbing",
        "product_contains": ["tape", "teflon", "ptfe"],
        "category": "hardware",
        "responses": [
            {"shop_name_contains": "sharma", "accepted": True,
             "price": 30.0, "delay_seconds": 5,
             "note": "Zero-inventory shop with the right capabilities — they have it physically."},
            {"shop_name_contains": "gupta", "accepted": True,
             "price": 25.0, "delay_seconds": 12,
             "note": "Shop with inventory listed — confirms at the listed price."},
            {"shop_name_contains": "raj", "accepted": False,
             "delay_seconds": 18,
             "note": "Plumbing shop that does NOT stock this — becomes demand intelligence."},
        ],
    },
    # Generic fallback: if no scenario matches, simulate a single YES from the
    # closest candidate so the customer still sees the loop complete. This is
    # NOT fake activity — it's clearly labelled demo simulation.
]


def _matches_scenario(request: Dict, scenario: Dict) -> bool:
    product = (request.get("product") or "").lower()
    keywords = scenario.get("product_contains") or []
    if not any(kw in product for kw in keywords):
        return False
    if scenario.get("category") and request.get("category") != scenario["category"]:
        return False
    return True


def _find_scenario(request: Dict) -> Optional[Dict]:
    for scenario in DEMO_SCENARIOS:
        if _matches_scenario(request, scenario):
            return scenario
    return None


async def maybe_schedule_demo_responses(request: Dict, candidates) -> int:
    """Schedule simulated merchant responses for a request if DEMO_MODE is on.

    Returns the number of simulated responses scheduled (0 if not in demo
    mode, no Telegram bot needed, or no scenario matched).

    ``candidates`` is the list returned by merchant_matching.find_candidates —
    a list of MatchCandidate dataclass instances with ``merchant_id``,
    ``shop_name``, etc.
    """
    if not settings.DEMO_MODE:
        return 0
    # Don't simulate when real Telegram polling is running — real merchants
    # should respond in that case.
    from app.services import notification_service
    if settings.RUN_BOT and notification_service.get_bot() is not None:
        return 0

    scenario = _find_scenario(request)
    if not scenario:
        return 0

    scheduled = 0
    for response in scenario.get("responses", []):
        needle = response["shop_name_contains"]
        match_candidate = None
        for cand in candidates:
            if needle in (cand.shop_name or "").lower():
                match_candidate = cand
                break
        if not match_candidate:
            continue
        # Look up the persisted merchant_match row for this (request, merchant).
        from app.database import mongo as m
        match_doc = await m.merchant_matches().find_one({
            "request_id": request["request_id"],
            "merchant_id": _safe_oid(match_candidate.merchant_id),
        })
        if not match_doc:
            continue
        asyncio.create_task(_simulate_after_delay(
            match_id=match_doc["_id"],
            accepted=response["accepted"],
            price=response.get("price"),
            delay=response["delay_seconds"],
            note=response.get("note", ""),
        ))
        scheduled += 1
    if scheduled:
        logger.info("demo simulation scheduled | request=%s count=%d scenario=%s",
                    request.get("request_id"), scheduled, scenario.get("name"))
    return scheduled


def _safe_oid(value):
    from bson import ObjectId
    try:
        return ObjectId(str(value))
    except Exception:
        return None


async def _simulate_after_delay(*, match_id, accepted: bool,
                                price: Optional[float], delay: int,
                                note: str = "") -> None:
    """After sleeping, record the simulated merchant response.

    Tagged source="demo_simulated" so the UI can label it clearly.
    """
    from app.services import search_service
    try:
        await asyncio.sleep(max(1, int(delay)))
        ok, _ = await search_service.handle_merchant_response(
            match_id, accepted=accepted, price=price, source="demo_simulated",
        )
        if not ok:
            logger.warning("demo simulation skipped (no longer active) | match=%s", match_id)
            return
        logger.info("demo response recorded | match=%s accepted=%s price=%s | %s",
                    match_id, accepted, price, note)
    except Exception as exc:
        # Demo simulation must never break a real request.
        logger.warning("demo simulation failed | match=%s | %s", match_id, exc)
