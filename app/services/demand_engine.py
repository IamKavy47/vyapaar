"""Demand intelligence.

Every merchant answer — especially a NO — becomes a demand signal. Over time the
shopkeeper learns what the neighbourhood keeps asking for and cannot find.
"""
from datetime import timedelta
from typing import Dict, List, Optional

from bson import ObjectId

from app.database import mongo as m
from app.models.demand import build_demand_event
from app.models.user import utcnow
from app.utils.logging import get_logger

logger = get_logger(__name__)


async def record_event(*, request: Dict, merchant_id, response: str,
                       price: Optional[float] = None) -> None:
    doc = build_demand_event(
        request_id=request["request_id"],
        merchant_id=ObjectId(str(merchant_id)),
        product=request.get("product") or "",
        category=request.get("category"),
        sub_category=request.get("sub_category"),
        latitude=request["latitude"],
        longitude=request["longitude"],
        response=response,
        price=price,
    )
    await m.demand_events().insert_one(doc)
    logger.info("demand event | product=%s response=%s", doc["product"], response)


async def top_products(*, days: int = 30, limit: int = 10, merchant_id=None,
                       category: Optional[str] = None) -> List[Dict]:
    match: Dict = {"created_at": {"$gte": utcnow() - timedelta(days=days)}}
    if merchant_id:
        match["merchant_id"] = ObjectId(str(merchant_id))
    if category:
        match["category"] = category

    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": "$product_key",
            "product": {"$first": "$product"},
            "category": {"$first": "$category"},
            "request_ids": {"$addToSet": "$request_id"},
            "merchant_response_attempts": {"$sum": 1},
            "unavailable_responses": {"$sum": {"$cond": [{"$eq": ["$response", "unavailable"]}, 1, 0]}},
            "available_responses": {"$sum": {"$cond": [{"$eq": ["$response", "available"]}, 1, 0]}},
            "last_seen": {"$max": "$created_at"},
        }},
        {"$addFields": {"unique_customer_requests": {"$size": "$request_ids"}}},
        {"$sort": {"unique_customer_requests": -1, "merchant_response_attempts": -1}},
        {"$limit": limit},
    ]
    results = []
    async for row in m.demand_events().aggregate(pipeline):
        row["product"] = row.get("product") or row["_id"]
        row["requests"] = row.get("unique_customer_requests", 0)  # backward compatibility for old UI
        row["unavailable"] = row.get("unavailable_responses", 0)
        row["available"] = row.get("available_responses", 0)
        row["unavailable_rate"] = round(
            row["unavailable_responses"] / max(1, row["merchant_response_attempts"]), 2
        )
        row.pop("request_ids", None)
        row.pop("_id", None)
        results.append(row)
    return results


async def category_breakdown(*, days: int = 30, merchant_id=None) -> List[Dict]:
    match: Dict = {"created_at": {"$gte": utcnow() - timedelta(days=days)}}
    if merchant_id:
        match["merchant_id"] = ObjectId(str(merchant_id))
    pipeline = [
        {"$match": match},
        {"$group": {"_id": "$category", "requests": {"$sum": 1}}},
        {"$sort": {"requests": -1}},
        {"$limit": 10},
    ]
    return [{"category": r["_id"], "requests": r["requests"]}
            async for r in m.demand_events().aggregate(pipeline)]


async def nearby_demand(latitude: float, longitude: float, *, radius_meters: int = 2000,
                        days: int = 30, limit: int = 10) -> List[Dict]:
    """What is the neighbourhood asking for, regardless of which shop was asked?"""
    pipeline = [
        {"$geoNear": {
            "near": {"type": "Point", "coordinates": [longitude, latitude]},
            "distanceField": "distance",
            "maxDistance": radius_meters,
            "spherical": True,
            "query": {"created_at": {"$gte": utcnow() - timedelta(days=days)}},
        }},
        {"$group": {
            "_id": "$product_key",
            "product": {"$first": "$product"},
            "request_ids": {"$addToSet": "$request_id"},
            "merchant_response_attempts": {"$sum": 1},
            "unavailable_responses": {"$sum": {"$cond": [{"$eq": ["$response", "unavailable"]}, 1, 0]}},
            "available_responses": {"$sum": {"$cond": [{"$eq": ["$response", "available"]}, 1, 0]}},
        }},
        {"$addFields": {"unique_customer_requests": {"$size": "$request_ids"}}},
        {"$sort": {"unique_customer_requests": -1, "merchant_response_attempts": -1}},
        {"$limit": limit},
    ]
    out = []
    async for row in m.demand_events().aggregate(pipeline):
        out.append({
            "product": row.get("product") or row["_id"],
            "unique_customer_requests": row["unique_customer_requests"],
            "merchant_response_attempts": row["merchant_response_attempts"],
            "unavailable_responses": row["unavailable_responses"],
            "available_responses": row["available_responses"],
            "unavailable_rate": round(
                row["unavailable_responses"] / max(1, row["merchant_response_attempts"]), 2
            ),
        })
    return out


def format_demand_report(rows: List[Dict], *, title: str = "LOCAL DEMAND") -> str:
    if not rows:
        return (f"📊 {title}\n\nAbhi tak koi demand data nahi hai.\n"
                "Jaise hi customers requests bhejenge, yahan insights dikhenge.")
    lines = [f"📊 {title}", ""]
    for row in rows:
        lines.append(f"🔸 {row['product']}")
        lines.append(f"   {row['requests']} requests · {row.get('unavailable', 0)} unavailable")
        lines.append("")
    lines.append("💡 Jo items baar-baar 'unavailable' hain, unhe stock karne par sale badh sakti hai.")
    return "\n".join(lines)
