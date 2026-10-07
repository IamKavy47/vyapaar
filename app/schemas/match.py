"""Merchant match / offer schemas."""
from typing import List, Optional

from pydantic import BaseModel, Field


class MatchCandidate(BaseModel):
    merchant_id: str
    shop_name: str
    category: str
    distance_meters: float
    match_score: float
    score_breakdown: dict = Field(default_factory=dict)
    has_inventory_hint: bool = False
    known_price: Optional[float] = None
    telegram_user_id: Optional[int] = None


class MatchResult(BaseModel):
    request_id: str
    product: Optional[str] = None
    radius_used_meters: int = 0
    candidates: List[MatchCandidate] = Field(default_factory=list)
    notified: int = 0
    message: Optional[str] = None


class OfferPublic(BaseModel):
    shop_name: str
    distance_meters: float
    price: Optional[float] = None
    status: str
    phone: Optional[str] = None
