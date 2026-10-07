"""Optional inventory.

Inventory is an enhancement, never a requirement. Zero rows here must not stop a
merchant from being discovered.
"""
from typing import Dict, List, Optional

from bson import ObjectId

from app.database import mongo as m
from app.models.inventory import build_inventory_document, product_key
from app.models.user import utcnow
from app.schemas.intent import InventoryExtraction
from app.utils.logging import get_logger

logger = get_logger(__name__)


async def upsert_item(*, shop_id, product: str, quantity: float = 0, unit: str = "piece",
                      brand: Optional[str] = None, price: Optional[float] = None,
                      source: str = "manual", confidence: float = 1.0,
                      image_url: Optional[str] = None,
                      image_source: str = "none") -> Dict:
    doc = build_inventory_document(
        shop_id=ObjectId(str(shop_id)), product=product, quantity=quantity, unit=unit,
        brand=brand, price=price, source=source, confidence=confidence,
        image_url=image_url, image_source=image_source,
    )
    update_set = {
        "product": doc["product"], "unit": doc["unit"], "brand": doc["brand"],
        "price": doc["price"], "source": doc["source"],
        "confidence": doc["confidence"], "updated_at": utcnow(),
    }
    # Only set image_url + image_source if a new one is being provided —
    # so a manual upload doesn't get clobbered by a subsequent AI-fetch
    # attempt that returns None. The first non-None value wins.
    if image_url is not None:
        update_set["image_url"] = image_url
        update_set["image_source"] = image_source
    update_set["in_stock"] = doc["in_stock"]
    await m.inventory_items().update_one(
        {"shop_id": doc["shop_id"], "product_key": doc["product_key"]},
        {
            "$set": update_set,
            "$inc": {"quantity": doc["quantity"]},
            "$setOnInsert": {"created_at": doc["created_at"]},
        },
        upsert=True,
    )
    return doc


async def bulk_store(shop_id, extraction: InventoryExtraction, *, source: str) -> int:
    stored = 0
    for item in extraction.items:
        if not item.product:
            continue
        await upsert_item(
            shop_id=shop_id, product=item.product, quantity=item.quantity or 0,
            unit=item.unit, brand=item.brand, price=item.price, source=source,
            confidence=item.confidence,
        )
        stored += 1
    logger.info("inventory stored | shop=%s items=%d source=%s", shop_id, stored, source)
    return stored


async def list_items(shop_id, limit: int = 30, *, in_stock_only: bool = False) -> List[Dict]:
    query = {"shop_id": ObjectId(str(shop_id))}
    if in_stock_only:
        query.update({"quantity": {"$gt": 0}, "in_stock": {"$ne": False}})
    cursor = m.inventory_items().find(query).sort("updated_at", -1).limit(limit)
    return [doc async for doc in cursor]


async def count_items(shop_id, *, in_stock_only: bool = False) -> int:
    query = {"shop_id": ObjectId(str(shop_id))}
    if in_stock_only:
        query.update({"quantity": {"$gt": 0}, "in_stock": {"$ne": False}})
    return await m.inventory_items().count_documents(query)


async def remove_item(shop_id, product: str) -> bool:
    result = await m.inventory_items().delete_one(
        {"shop_id": ObjectId(str(shop_id)), "product_key": product_key(product)}
    )
    return result.deleted_count > 0


def format_inventory(items: List[Dict]) -> str:
    if not items:
        return ("📦 INVENTORY\n\nAapka inventory khali hai — aur yeh bilkul theek hai.\n"
                "Vyapaar-Mitra aapko phir bhi customers tak pahunchata hai.\n\n"
                "Chahein to invoice ki photo, shelf ki photo ya voice note bhejiye.")
    lines = ["📦 INVENTORY", ""]
    for item in items:
        qty = f"{item.get('quantity', 0):g} {item.get('unit', 'piece')}"
        price = f" · ₹{item['price']:g}" if item.get("price") else ""
        lines.append(f"• {item['product']} — {qty}{price}")
    lines += ["", "Inventory optional hai. Matching iske bina bhi chalti hai."]
    return "\n".join(lines)
