"""Browsing the neighbourhood.

Search answers "who *might* have this?" and asks merchants. Browsing answers
"what is on the shelf *right now*?" and only ever shows stock a merchant has
actually recorded.

The two must not be confused, so nothing in this module invents a product, a
price or an availability claim. A browse listing is a merchant's own record; the
customer still reserves through the same YES/NO loop, because a stored row is a
claim about the past, not a promise about this minute.

Zero-inventory merchants are unaffected: they simply do not appear in product
listings, while remaining fully discoverable through search. Browsing is a bonus
for shops that opted in, never a requirement to be found.
"""
from typing import Dict, List, Optional

from bson import ObjectId

from app.config.settings import settings
from app.database import mongo as m
from app.models.inventory import product_key
from app.models.shop import category_label, normalize_category
from app.utils.errors import NotFound, ValidationFailed
from app.utils.geo import from_geojson_point, navigation_link, valid_coordinates
from app.utils.logging import get_logger

logger = get_logger(__name__)

DEFAULT_BROWSE_RADIUS_METERS = settings.SEARCH_RADIUS_DEFAULT_METERS


def _geo_stage(latitude: float, longitude: float, radius: int, extra_query: Optional[Dict] = None):
    query = {"is_active": True}
    if extra_query:
        query.update(extra_query)
    return {
        "$geoNear": {
            "near": {"type": "Point", "coordinates": [longitude, latitude]},
            "distanceField": "distance_meters",
            "maxDistance": int(radius),
            "spherical": True,
            "query": query,
        }
    }


def _require_coordinates(latitude: float, longitude: float, operation: str) -> None:
    if latitude is None or longitude is None or not valid_coordinates(latitude, longitude):
        raise ValidationFailed(
            "Browse called without usable coordinates",
            user_message="📍 Pehle apni location share kijiye, phir aas-paas ka saaman dikhaunga.",
            operation=operation,
            context={"latitude": latitude, "longitude": longitude},
        )


async def nearby_shops(latitude: float, longitude: float, *,
                       category: Optional[str] = None,
                       radius_meters: int = DEFAULT_BROWSE_RADIUS_METERS,
                       limit: int = 10) -> List[Dict]:
    """Open shops around the customer, nearest first, with a live item count."""
    _require_coordinates(latitude, longitude, "browse.nearby_shops")
    extra = {"category": normalize_category(category)} if category else None
    pipeline = [_geo_stage(latitude, longitude, radius_meters, extra), {"$limit": int(limit)}]

    shops: List[Dict] = []
    async for shop in m.shops().aggregate(pipeline):
        item_count = await m.inventory_items().count_documents(
            {"shop_id": shop["_id"], "quantity": {"$gt": 0}}
        )
        shops.append(_shop_summary(shop, item_count))
    logger.info("browse shops | radius=%dm category=%s found=%d",
                radius_meters, category or "all", len(shops))
    return shops


def _shop_summary(shop: Dict, item_count: int = 0) -> Dict:
    coordinates = from_geojson_point(shop.get("location"))
    return {
        "shop_id": str(shop["_id"]),
        "shop_name": shop.get("shop_name", "Shop"),
        "category": shop.get("category", "other"),
        "category_label": category_label(shop.get("category")),
        "phone": shop.get("phone"),
        "address": shop.get("address"),
        "distance_meters": round(float(shop.get("distance_meters") or 0), 1),
        "latitude": coordinates[0] if coordinates else None,
        "longitude": coordinates[1] if coordinates else None,
        "navigation_url": navigation_link(*coordinates) if coordinates else None,
        "item_count": item_count,
        "telegram_user_id": shop.get("telegram_user_id"),
        "accepted_count": shop.get("accepted_count", 0),
    }


async def nearby_categories(latitude: float, longitude: float, *,
                            radius_meters: int = DEFAULT_BROWSE_RADIUS_METERS) -> List[Dict]:
    """Which kinds of shop exist around here, and how many list stock."""
    _require_coordinates(latitude, longitude, "browse.nearby_categories")
    pipeline = [
        _geo_stage(latitude, longitude, radius_meters),
        {"$group": {"_id": "$category", "shops": {"$sum": 1},
                    "nearest": {"$min": "$distance_meters"}}},
        {"$sort": {"shops": -1}},
    ]
    rows = []
    async for row in m.shops().aggregate(pipeline):
        rows.append({
            "category": row["_id"] or "other",
            "label": category_label(row["_id"]),
            "shops": row["shops"],
            "nearest_meters": round(float(row.get("nearest") or 0), 1),
        })
    return rows


async def nearby_products(latitude: float, longitude: float, *,
                          query: Optional[str] = None,
                          category: Optional[str] = None,
                          radius_meters: int = DEFAULT_BROWSE_RADIUS_METERS,
                          limit: int = 20) -> List[Dict]:
    """Actual in-stock items on nearby shelves.

    Only rows a merchant recorded, with quantity above zero. Cheapest first when
    prices exist, then nearest — a customer browsing wants the best deal they can
    walk to.
    """
    _require_coordinates(latitude, longitude, "browse.nearby_products")
    extra = {"category": normalize_category(category)} if category else None
    shop_pipeline = [_geo_stage(latitude, longitude, radius_meters, extra), {"$limit": 60}]
    shops = {}
    async for shop in m.shops().aggregate(shop_pipeline):
        shops[shop["_id"]] = shop
    if not shops:
        return []

    item_query: Dict = {"shop_id": {"$in": list(shops.keys())}, "quantity": {"$gt": 0}}
    if query:
        # Exact key first; fall back to a prefix so "pipe" finds "pipe 1 inch".
        key = product_key(query)
        item_query["$or"] = [
            {"product_key": key},
            {"product_key": {"$regex": f"^{_escape_regex(key)}"}},
            {"product": {"$regex": _escape_regex(query.strip()), "$options": "i"}},
        ]

    results: List[Dict] = []
    async for item in m.inventory_items().find(item_query).limit(200):
        shop = shops.get(item["shop_id"])
        if not shop:
            continue
        results.append(_product_entry(item, shop))

    results.sort(key=lambda r: (
        r["price"] is None,                      # priced items first
        r["price"] if r["price"] is not None else 0,
        r["distance_meters"],
    ))
    logger.info("browse products | query=%s category=%s found=%d",
                query or "-", category or "all", len(results))
    return results[:limit]


def _product_entry(item: Dict, shop: Dict) -> Dict:
    coordinates = from_geojson_point(shop.get("location"))
    return {
        "item_id": str(item["_id"]),
        "product": item.get("product", ""),
        "product_key": item.get("product_key", ""),
        "quantity": float(item.get("quantity") or 0),
        "unit": item.get("unit", "piece"),
        "brand": item.get("brand"),
        "price": item.get("price"),
        "source": item.get("source", "manual"),
        "updated_at": item.get("updated_at"),
        "shop_id": str(shop["_id"]),
        "shop_name": shop.get("shop_name", "Shop"),
        "shop_phone": shop.get("phone"),
        "shop_address": shop.get("address"),
        "category": shop.get("category", "other"),
        "distance_meters": round(float(shop.get("distance_meters") or 0), 1),
        "latitude": coordinates[0] if coordinates else None,
        "longitude": coordinates[1] if coordinates else None,
        "navigation_url": navigation_link(*coordinates) if coordinates else None,
        "telegram_user_id": shop.get("telegram_user_id"),
    }


def _escape_regex(value: str) -> str:
    import re
    return re.escape(value)


async def get_shop(shop_id) -> Dict:
    try:
        oid = ObjectId(str(shop_id))
    except Exception as exc:
        raise ValidationFailed("Malformed shop id", operation="browse.get_shop",
                               context={"shop_id": shop_id}, cause=exc)
    shop = await m.shops().find_one({"_id": oid})
    if not shop:
        raise NotFound("Shop not found", user_message="🏪 Yeh shop ab available nahi hai.",
                       operation="browse.get_shop", context={"shop_id": str(shop_id)})
    return shop


async def shop_with_stock(shop_id, *, customer_latitude: Optional[float] = None,
                          customer_longitude: Optional[float] = None,
                          limit: int = 20) -> Dict:
    """One shop's card: details, distance from the customer, and what it stocks."""
    shop = await get_shop(shop_id)
    items = [
        _product_entry(item, shop)
        async for item in m.inventory_items()
        .find({"shop_id": shop["_id"], "quantity": {"$gt": 0}})
        .sort("updated_at", -1).limit(limit)
    ]
    summary = _shop_summary(shop, len(items))
    if customer_latitude is not None and customer_longitude is not None and summary["latitude"]:
        from app.utils.geo import haversine_meters
        summary["distance_meters"] = round(haversine_meters(
            customer_latitude, customer_longitude, summary["latitude"], summary["longitude"]
        ), 1)
    return {"shop": summary, "items": items}


async def get_item(item_id) -> Dict:
    try:
        oid = ObjectId(str(item_id))
    except Exception as exc:
        raise ValidationFailed("Malformed inventory item id", operation="browse.get_item",
                               context={"item_id": item_id}, cause=exc)
    item = await m.inventory_items().find_one({"_id": oid})
    if not item:
        raise NotFound("Inventory item not found",
                       user_message="📦 Yeh item ab list mein nahi hai.",
                       operation="browse.get_item", context={"item_id": str(item_id)})
    return item


def format_product_list(products: List[Dict], *, heading: str) -> str:
    if not products:
        return (f"{heading}\n\nAas-paas kisi shop ne abhi is item ka stock list nahi kiya hai.\n\n"
                "🔎 Find Product dabaiye — main shops se seedha pooch lunga, "
                "chahe unhone inventory upload ki ho ya nahi.")
    from app.utils.geo import humanize_distance
    lines = [heading, ""]
    for index, entry in enumerate(products, start=1):
        price = f"₹{entry['price']:g}" if entry.get("price") is not None else "price not listed"
        quantity = f"{entry['quantity']:g} {entry['unit']}"
        lines.append(f"{index}. {entry['product']} — {price}")
        lines.append(f"   🏪 {entry['shop_name']} · "
                     f"{humanize_distance(entry['distance_meters'])} · {quantity} in stock")
    lines += ["", "Neeche button dabakar shop se reserve kar sakte hain.",
              "Prices shops ne khud daale hain — jaane se pehle confirm kar lijiye."]
    return "\n".join(lines)


def format_shop_card(shop: Dict, items: List[Dict]) -> str:
    from app.utils.geo import humanize_distance
    lines = [
        f"🏪 {shop['shop_name']}",
        f"🏷️ {shop['category_label']} · 📍 {humanize_distance(shop['distance_meters'])} away",
    ]
    if shop.get("phone"):
        lines.append(f"📞 {shop['phone']}")
    if shop.get("address"):
        lines.append(f"🏠 {shop['address']}")
    if shop.get("navigation_url"):
        lines.append(f"🧭 Directions: {shop['navigation_url']}")
    lines.append("")
    if items:
        lines.append("📦 IN STOCK")
        for entry in items:
            price = f" — ₹{entry['price']:g}" if entry.get("price") is not None else ""
            lines.append(f"• {entry['product']}{price} "
                         f"({entry['quantity']:g} {entry['unit']})")
    else:
        lines.append("📦 Is shop ne abhi inventory list nahi ki hai.")
        lines.append("Phir bhi aap pooch sakte hain — shop ko request bhej dijiye.")
    return "\n".join(lines)


def reservation_message(*, product: str, quantity: float, unit: str,
                        customer_name: str, distance_text: str,
                        price: Optional[float]) -> str:
    """What the shopkeeper sees when a browsing customer reserves an item."""
    lines = [
        "🛒 RESERVATION REQUEST",
        "",
        f"👤 {customer_name} ne aapki listing se yeh item choose kiya hai",
        f"📍 Approximately {distance_text} away",
        "",
        f"🔧 {product}",
        f"📦 Quantity: {quantity:g} {unit}",
    ]
    if price is not None:
        lines.append(f"💰 Aapki listed price: ₹{price:g}")
    lines += ["", "Abhi bhi stock mein hai?"]
    return "\n".join(lines)


def max_browse_radius() -> int:
    return settings.SEARCH_RADIUS_MAX_METERS
