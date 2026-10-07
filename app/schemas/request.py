"""Product request API schemas."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class RequestPublic(BaseModel):
    request_id: str
    product: Optional[str] = None
    category: Optional[str] = None
    sub_category: Optional[str] = None
    quantity: int = 1
    unit: str = "piece"
    confidence: float = 0.0
    status: str
    input_type: str
    matched_count: int = 0
    created_at: Optional[datetime] = None


class TestMatchPayload(BaseModel):
    """POST /api/test/match — run the full pipeline without Telegram."""
    text: str = Field(min_length=2, max_length=500)
    latitude: float
    longitude: float
    notify: bool = False
    customer_name: str = "API Tester"


class ClarificationOption(BaseModel):
    label: str
    value: str
