"""Merchant match / offer schemas."""
from datetime import datetime
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
    id: Optional[str] = None
    request_id: Optional[str] = None
    shop_id: Optional[str] = None
    shop_name: str
    distance_meters: float
    price: Optional[float] = None
    price_missing: bool = False
    match_score: Optional[float] = None
    score_breakdown: dict = Field(default_factory=dict)
    response_time_seconds: Optional[int] = None
    accepted_offer_age_seconds: Optional[int] = None
    reliability: Optional[float] = None
    inventory_updated_at: Optional[datetime] = None
    is_verified: bool = False
    status: str
    phone: Optional[str] = None
