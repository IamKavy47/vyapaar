"""Khata schemas."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class KhataEntryPublic(BaseModel):
    customer_name: str
    amount: float
    entry_type: str
    description: Optional[str] = None
    created_at: Optional[datetime] = None


class KhataBalance(BaseModel):
    customer_name: str
    outstanding: float
    total_credit: float = 0.0
    total_paid: float = 0.0
    entries: int = 0
    last_entry_at: Optional[datetime] = None


class KhataSummary(BaseModel):
    merchant_id: str
    total_outstanding: float = 0.0
    balances: List[KhataBalance] = Field(default_factory=list)
