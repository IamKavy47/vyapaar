"""ProductIntent — the universal representation of "what the customer needs".

Text, voice and images all collapse into this one object. There is exactly one
search system.
"""
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from app.models.shop import normalize_category
from app.utils.parsing import clamp_confidence, safe_int


class ProductIntent(BaseModel):
    intent: str = Field(default="find_product")
    product: Optional[str] = None
    category: str = Field(default="other")
    sub_category: Optional[str] = None
    quantity: int = Field(default=1, ge=1, le=10000)
    unit: str = Field(default="piece")
    brand: Optional[str] = None
    description: Optional[str] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    alternative_products: List[str] = Field(default_factory=list)

    # Internal bookkeeping (not part of the LLM contract)
    provider: Optional[str] = None
    uncertain: bool = False

    @field_validator("category", mode="before")
    @classmethod
    def _cat(cls, v):
        return normalize_category(v)

    @field_validator("confidence", mode="before")
    @classmethod
    def _conf(cls, v):
        return clamp_confidence(v)

    @field_validator("quantity", mode="before")
    @classmethod
    def _qty(cls, v):
        return max(1, min(10000, safe_int(v, 1)))

    @field_validator("alternative_products", mode="before")
    @classmethod
    def _alts(cls, v):
        if isinstance(v, str):
            v = [v]
        if not isinstance(v, list):
            return []
        return [str(x).strip() for x in v if str(x).strip()][:5]

    @field_validator("unit", mode="before")
    @classmethod
    def _unit(cls, v):
        return (str(v).strip().lower() or "piece") if v else "piece"

    @property
    def is_actionable(self) -> bool:
        return bool(self.product) and self.intent in {"find_product", "compare_price"}


class KhataIntent(BaseModel):
    """Structured output of "Ramesh ne 500 rupaye udhaar liye"."""
    customer_name: Optional[str] = None
    amount: float = 0.0
    entry_type: str = "credit"  # credit | payment
    description: Optional[str] = None
    confidence: float = 0.0

    @field_validator("entry_type", mode="before")
    @classmethod
    def _type(cls, v):
        value = str(v or "credit").strip().lower()
        if value in {"payment", "paid", "repayment", "credit_payment", "settle"}:
            return "payment"
        return "credit"

    @field_validator("amount", mode="before")
    @classmethod
    def _amount(cls, v):
        try:
            return max(0.0, float(v))
        except (TypeError, ValueError):
            return 0.0

    @field_validator("confidence", mode="before")
    @classmethod
    def _conf(cls, v):
        return clamp_confidence(v)


class InventoryLine(BaseModel):
    product: str
    quantity: float = 1
    unit: str = "piece"
    brand: Optional[str] = None
    price: Optional[float] = None
    confidence: float = 0.0

    @field_validator("confidence", mode="before")
    @classmethod
    def _conf(cls, v):
        return clamp_confidence(v)


class InventoryExtraction(BaseModel):
    items: List[InventoryLine] = Field(default_factory=list)
    source_type: str = "unknown"  # invoice | shelf | voice
    notes: Optional[str] = None
