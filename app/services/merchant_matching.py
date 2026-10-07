"""ZERO-INVENTORY MERCHANT MATCHING — the core innovation.

Traditional commerce asks: "what products has this shop uploaded?"
Vyapaar-Mitra asks:        "who nearby can satisfy this customer's need?"

A merchant with an empty catalogue is still matched, because we reason over
category, capabilities, distance and historical behaviour. Inventory, when it
exists, is only a bonus signal.
"""
import re
from typing import Dict, List, Optional, Set

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.config.settings import settings
from app.database import mongo as m
from app.models.inventory import product_key
from app.models.merchant_match import MatchStatus, build_match_document
from app.models.shop import (
    CATEGORY_AFFINITY, CATEGORY_CAPABILITIES, normalize_category, response_rate,
)
from app.models.user import utcnow
from app.schemas.match import MatchCandidate
from app.utils.geo import from_geojson_point, haversine_meters
from app.utils.logging import get_logger

logger = get_logger(__name__)

_STOPWORDS = {"the", "a", "an", "of", "for", "with", "and", "ka", "ke", "ki", "wala", "chahiye"}
_TOKEN_RE = re.compile(r"[a-z0-9\u0900-\u097f]+", re.IGNORECASE)
_CAPABILITY_ALIASES = {
    "teflon": {"ptfe", "thread", "seal", "sealing", "pipe", "plumber", "white_tape", "safed"},
    "tape": {"ptfe", "seal", "sealing", "plumber", "thread"},
    "ptfe": {"teflon", "thread", "seal", "tape"},
    "नल": {"pipe", "plumbing", "tap"},
    "पाइप": {"pipe", "plumbing"},
    "टेप": {"tape", "teflon", "ptfe"},
    "safed": {"white", "teflon", "ptfe"},
}


def _tokens(text: Optional[str]) -> Set[str]:
    if not text:
        return set()
    tokens = {m.group(0).strip().lower() for m in _TOKEN_RE.finditer(text)}
    normalized = set()
    for token in tokens:
        if token in _STOPWORDS:
            continue
        if len(token) <= 2 and not re.search(r"[\u0900-\u097f]", token):
            continue
        normalized.add(token)
        normalized |= _CAPABILITY_ALIASES.get(token, set())
    return normalized


def need_capabilities(request: Dict) -> Set[str]:
    """What a shop would need to be able to do to serve this request."""
    category = normalize_category(request.get("category"))
    caps: Set[str] = set(CATEGORY_CAPABILITIES.get(category, []))
    if request.get("sub_category"):
        caps.add(str(request["sub_category"]).strip().lower().replace(" ", "_"))
    caps |= _tokens(request.get("product"))
    for alt in request.get("alternative_products") or []:
        caps |= _tokens(alt)
    caps |= _tokens(request.get("description"))
    return {c for c in caps if c}


def category_score(request_category: str, shop_category: str) -> float:
    affinity = CATEGORY_AFFINITY.get(normalize_category(request_category), {})
    return float(affinity.get(normalize_category(shop_category), 0.1))


def capability_score(needed: Set[str], shop: Dict) -> float:
    shop_caps = {str(c).lower() for c in (shop.get("capabilities") or [])}
    shop_caps |= {str(s).lower() for s in (shop.get("subcategories") or [])}
    if not shop_caps or not needed:
        return 0.2  # a shop with no declared capabilities is still weakly plausible
    overlap = shop_caps & needed
    if overlap:
        return min(1.0, 0.45 + 0.2 * len(overlap))
    # Token-prefix credit only for meaningful stems ("pipe" <-> "pipes"), not broad substrings.
    need_stems = {n.rstrip("s") for n in needed}
    cap_stems = {c.rstrip("s") for c in shop_caps}
    if need_stems & cap_stems:
        return 0.35
    return 0.1


def distance_score(distance_meters: float, max_radius: int) -> float:
    if max_radius <= 0:
        return 0.0
    return max(0.0, 1.0 - (float(distance_meters) / float(max_radius)))


def score_merchant(request: Dict, shop: Dict, distance_meters: float,
                   max_radius: Optional[int] = None,
                   needed: Optional[Set[str]] = None) -> Dict:
    """Weighted, fully explainable score. Weights are configurable in .env."""
    max_radius = max_radius or settings.MAX_MATCH_RADIUS_METERS
    needed = needed if needed is not None else need_capabilities(request)

    cat = category_score(request.get("category"), shop.get("category"))
    cap = capability_score(needed, shop)
    dist = distance_score(distance_meters, max_radius)
    hist = response_rate(shop)

    total = (
        settings.WEIGHT_CATEGORY * cat
        + settings.WEIGHT_CAPABILITY * cap
        + settings.WEIGHT_DISTANCE * dist
        + settings.WEIGHT_HISTORY * hist
    )
    return {
        "total": round(min(1.0, total), 4),
        "category": round(cat, 3),
        "capability": round(cap, 3),
        "distance": round(dist, 3),
        "history": round(hist, 3),
        "reason": explain_score({
            "category": round(cat, 3), "capability": round(cap, 3),
            "distance": round(dist, 3), "history": round(hist, 3),
        }),
    }


def explain_score(breakdown: Dict) -> str:
    parts = []
    if breakdown.get("capability", 0) >= 0.45:
        parts.append("strong capability match")
    if breakdown.get("category", 0) >= 0.7:
        parts.append("right category")
    if breakdown.get("distance", 0) >= 0.6:
        parts.append("nearby")
    if breakdown.get("history", 0) >= 0.7:
        parts.append("reliable responder")
    if not parts:
        return "basic nearby category fit"
    return ", ".join(parts[:3])


async def _inventory_hints(shop_ids: List[ObjectId], terms: List[str]) -> Dict[str, Dict]:
    """Optional signal: does this shop already have the item on record?"""
    if not shop_ids or not terms:
        return {}
    keys = [product_key(t) for t in terms if t]
    cursor = m.inventory_items().find(
        {"shop_id": {"$in": shop_ids}, "product_key": {"$in": keys}}
    )
    hints: Dict[str, Dict] = {}
    async for item in cursor:
        sid = str(item["shop_id"])
        current = hints.get(sid)
        if current is None or (item.get("price") is not None and current.get("price") is None):
            hints[sid] = {"price": item.get("price"), "quantity": item.get("quantity")}
    return hints


async def _cooled_down_ids(product: Optional[str]) -> Set[str]:
    """Merchants who already said NO to this product recently are left alone."""
    if not product:
        return set()
    cursor = m.merchant_cooldowns().find(
        {"product_key": product_key(product), "expires_at": {"$gt": utcnow()}}
    )
    return {str(doc["merchant_id"]) async for doc in cursor}


def _radius_steps_for(max_radius_meters: int) -> List[int]:
    """Expansion steps up to a ceiling that may exceed the default 5km.

    Reuses the configured 500m/1km/2km/5km progression for anything within it,
    then appends the customer's own ceiling as the final step so a 10km or 20km
    preference still gets a sensible last hop instead of jumping straight there.
    """
    steps = [s for s in settings.radius_steps if s <= max_radius_meters]
    if not steps or steps[-1] != max_radius_meters:
        steps.append(max_radius_meters)
    return sorted(set(steps))


async def find_candidates(request: Dict, *, limit: Optional[int] = None) -> Dict:
    """Geospatial search with automatic radius expansion (500m -> ... -> customer's range)."""
    limit = limit or settings.MAX_MERCHANTS_PER_REQUEST
    latitude, longitude = request["latitude"], request["longitude"]
    needed = need_capabilities(request)
    blocked = await _cooled_down_ids(request.get("product"))

    already = {
        str(doc["merchant_id"])
        async for doc in m.merchant_matches().find({"request_id": request["request_id"]})
    }

    max_radius = int(request.get("max_radius_meters") or settings.MAX_MATCH_RADIUS_METERS)
    steps = _radius_steps_for(max_radius)
    chosen_radius = steps[0]
    scored: List[Dict] = []

    for radius in steps:
        chosen_radius = radius
        pipeline = [
            {
                "$geoNear": {
                    "near": {"type": "Point", "coordinates": [longitude, latitude]},
                    "distanceField": "distance_meters",
                    "maxDistance": radius,
                    "spherical": True,
                    "query": {
                        "is_active": True,
                        "description": {
                            "$not": {"$regex": "demo merchant seeded", "$options": "i"}
                        },
                        "address": {
                            "$not": {"$regex": "^Demo Market", "$options": "i"}
                        },
                    },
                }
            },
            {"$limit": 60},
        ]
        shops = [doc async for doc in m.shops().aggregate(pipeline)]
        logger.info("merchant search | radius=%dm shops_in_range=%d", radius, len(shops))

        scored = []
        for shop in shops:
            sid = str(shop["_id"])
            if sid in blocked or sid in already:
                continue
            distance = float(shop.get("distance_meters") or haversine_meters(
                latitude, longitude, *(shop.get("location", {}).get("coordinates", [0, 0])[::-1])
            ))
            breakdown = score_merchant(request, shop, distance, radius, needed)
            if breakdown["total"] < 0.25:
                continue  # implausible shop — do not spam them
            scored.append({"shop": shop, "distance": distance, "score": breakdown})

        if scored:
            break

    scored.sort(key=lambda x: (-x["score"]["total"], x["distance"]))
    scored = scored[:limit]

    hints = await _inventory_hints(
        [s["shop"]["_id"] for s in scored],
        [request.get("product") or ""] + list(request.get("alternative_products") or []),
    )

    candidates = []
    for entry in scored:
        shop = entry["shop"]
        hint = hints.get(str(shop["_id"]))
        candidates.append(MatchCandidate(
            merchant_id=str(shop["_id"]),
            shop_name=shop.get("shop_name", "Shop"),
            category=shop.get("category", "other"),
            distance_meters=round(entry["distance"], 1),
            match_score=entry["score"]["total"],
            score_breakdown=entry["score"],
            has_inventory_hint=hint is not None,
            known_price=(hint or {}).get("price"),
            telegram_user_id=shop.get("telegram_user_id"),
        ))

    logger.info(
        "merchant count | request=%s candidates=%d radius=%dm",
        request.get("request_id"), len(candidates), chosen_radius,
    )
    return {"candidates": candidates, "radius_used_meters": chosen_radius}


async def persist_matches(request_id: str, candidates: List[MatchCandidate]) -> List[Dict]:
    """Create merchant_matches rows. Duplicates are ignored by the unique index."""
    created = []
    for candidate in candidates:
        doc = build_match_document(
            request_id=request_id,
            merchant_id=ObjectId(candidate.merchant_id),
            distance_meters=candidate.distance_meters,
            match_score=candidate.match_score,
            score_breakdown=candidate.score_breakdown,
        )
        try:
            result = await m.merchant_matches().insert_one(doc)
            doc["_id"] = result.inserted_id
            created.append(doc)
        except DuplicateKeyError:
            logger.debug("duplicate match skipped | %s / %s", request_id, candidate.merchant_id)
        except Exception:
            logger.exception("match persistence failed | request=%s merchant=%s",
                             request_id, candidate.merchant_id)
            raise
    return created


async def mark_notified(match_id) -> None:
    await m.merchant_matches().update_one(
        {"_id": match_id},
        {"$set": {"status": MatchStatus.NOTIFIED.value, "notified_at": utcnow()}},
    )


async def record_response(match_id, *, accepted: bool, price: Optional[float] = None) -> Optional[Dict]:
    """Idempotent: only the first response per match is recorded."""
    status = MatchStatus.ACCEPTED.value if accepted else MatchStatus.DECLINED.value
    result = await m.merchant_matches().find_one_and_update(
        {"_id": match_id, "status": {"$in": [MatchStatus.PENDING.value, MatchStatus.NOTIFIED.value]}},
        {"$set": {"status": status, "price": price, "responded_at": utcnow()}},
        return_document=True,
    )
    return result


async def set_cooldown(merchant_id, product: str) -> None:
    """A NO means 'don't ask me about this again for MERCHANT_COOLDOWN_HOURS'."""
    from datetime import timedelta
    if not product:
        return
    await m.merchant_cooldowns().update_one(
        {"merchant_id": ObjectId(str(merchant_id)), "product_key": product_key(product)},
        {"$set": {
            "product": product,
            "expires_at": utcnow() + timedelta(hours=settings.MERCHANT_COOLDOWN_HOURS),
            "updated_at": utcnow(),
        }},
        upsert=True,
    )


async def is_on_cooldown(merchant_id, product: str) -> bool:
    doc = await m.merchant_cooldowns().find_one({
        "merchant_id": ObjectId(str(merchant_id)),
        "product_key": product_key(product or ""),
        "expires_at": {"$gt": utcnow()},
    })
    return doc is not None


async def get_match(match_id) -> Optional[Dict]:
    try:
        return await m.merchant_matches().find_one({"_id": ObjectId(str(match_id))})
    except Exception:
        return None


async def accepted_offers(request_id: str) -> List[Dict]:
    cursor = m.merchant_matches().find(
        {"request_id": request_id, "status": {"$in": [MatchStatus.ACCEPTED.value, MatchStatus.SELECTED.value]}}
    ).sort("price", 1)
    offers = []
    async for match in cursor:
        shop = await m.shops().find_one({"_id": match["merchant_id"]})
        coordinates = from_geojson_point((shop or {}).get("location"))
        notified = int((shop or {}).get("notified_count") or 0)
        accepted = int((shop or {}).get("accepted_count") or 0)
        reliability = round(accepted / max(1, notified), 2)
        offers.append({
            "id": str(match.get("_id")),
            "request_id": match.get("request_id"),
            "shop_id": str(match.get("merchant_id")),
            "shop_name": (shop or {}).get("shop_name", "Shop"),
            "phone": (shop or {}).get("phone"),
            "address": (shop or {}).get("address"),
            "is_verified": bool((shop or {}).get("is_verified")),
            "latitude": coordinates[0] if coordinates else None,
            "longitude": coordinates[1] if coordinates else None,
            "distance_meters": match.get("distance_meters"),
            "price": match.get("price"),
            "price_missing": match.get("price") is None,
            "match_score": match.get("match_score"),
            "score_breakdown": match.get("score_breakdown") or {},
            "status": match.get("status"),
            "response_time_seconds": max(
                0, int(((match.get("responded_at") or match.get("created_at")) - match.get("created_at")).total_seconds())
            ) if match.get("created_at") else None,
            "accepted_offer_age_seconds": max(
                0, int((utcnow() - (match.get("responded_at") or match.get("created_at"))).total_seconds())
            ) if (match.get("responded_at") or match.get("created_at")) else None,
            "inventory_updated_at": (shop or {}).get("updated_at"),
            "reliability": reliability,
            "confirmed_recently": bool(
                match.get("responded_at")
                and (utcnow() - match.get("responded_at")).total_seconds() <= 600
            ),
        })
    return offers
