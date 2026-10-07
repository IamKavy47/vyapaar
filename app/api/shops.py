"""Read-only shop endpoints (useful for demos and future front-ends)."""
from typing import List, Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query

from app.database import mongo as m
from app.models.shop import category_label, normalize_category
from app.schemas.shop import ShopPublic
from app.services import inventory_service
from app.utils.geo import from_geojson_point

router = APIRouter(prefix="/api/shops", tags=["shops"])


async def _to_public(doc: dict, distance: Optional[float] = None) -> ShopPublic:
    coords = from_geojson_point(doc.get("location"))
    return ShopPublic(
        id=str(doc["_id"]),
        shop_name=doc.get("shop_name", ""),
        category=doc.get("category", "other"),
        category_label=category_label(doc.get("category")),
        subcategories=doc.get("subcategories") or [],
        capabilities=doc.get("capabilities") or [],
        address=doc.get("address"),
        description=doc.get("description"),
        phone=doc.get("phone"),
        latitude=coords[0] if coords else None,
        longitude=coords[1] if coords else None,
        distance_meters=round(distance, 1) if distance is not None else None,
        is_active=doc.get("is_active", True),
        is_verified=doc.get("is_verified", False),
        inventory_count=await inventory_service.count_items(doc["_id"]),
    )


@router.get("", response_model=List[ShopPublic])
async def list_shops(
    category: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    radius_meters: int = Query(5000, ge=50, le=50000),
    limit: int = Query(20, ge=1, le=100),
):
    query = {"is_active": True}
    if category:
        query["category"] = normalize_category(category)

    if latitude is not None and longitude is not None:
        pipeline = [
            {"$geoNear": {
                "near": {"type": "Point", "coordinates": [longitude, latitude]},
                "distanceField": "distance_meters",
                "maxDistance": radius_meters,
                "spherical": True,
                "query": query,
            }},
            {"$limit": limit},
        ]
        return [await _to_public(doc, doc.get("distance_meters"))
                async for doc in m.shops().aggregate(pipeline)]

    cursor = m.shops().find(query).limit(limit)
    return [await _to_public(doc) async for doc in cursor]


@router.get("/{shop_id}", response_model=ShopPublic)
async def get_shop(shop_id: str):
    try:
        doc = await m.shops().find_one({"_id": ObjectId(shop_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid shop id")
    if not doc:
        raise HTTPException(status_code=404, detail="Shop not found")
    return await _to_public(doc)
