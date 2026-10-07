"""Shop API schemas."""
from typing import List, Optional

from pydantic import BaseModel, Field


class ShopPublic(BaseModel):
    id: str
    shop_name: str
    category: str
    category_label: str
    subcategories: List[str] = Field(default_factory=list)
    capabilities: List[str] = Field(default_factory=list)
    address: Optional[str] = None
    description: Optional[str] = None
    phone: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    distance_meters: Optional[float] = None
    is_active: bool = True
    is_verified: bool = False
    inventory_count: int = 0


class ShopUpdatePayload(BaseModel):
    shop_name: Optional[str] = None
    phone: Optional[str] = None
    category: Optional[str] = None
    capabilities: Optional[List[str]] = None
    address: Optional[str] = None
    description: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
