"""Demand analytics endpoints."""
from typing import Optional

from fastapi import APIRouter, Query

from app.services import demand_engine

router = APIRouter(prefix="/api/demand", tags=["demand"])


@router.get("")
async def demand_overview(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(10, ge=1, le=50),
    category: Optional[str] = None,
):
    return {
        "days": days,
        "top_products": await demand_engine.top_products(days=days, limit=limit, category=category),
        "categories": await demand_engine.category_breakdown(days=days),
    }


@router.get("/nearby")
async def demand_nearby(
    latitude: float,
    longitude: float,
    radius_meters: int = Query(2000, ge=100, le=20000),
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(10, ge=1, le=50),
):
    return {
        "radius_meters": radius_meters,
        "products": await demand_engine.nearby_demand(
            latitude, longitude, radius_meters=radius_meters, days=days, limit=limit
        ),
    }
