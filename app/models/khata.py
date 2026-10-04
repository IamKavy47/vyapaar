"""Digital Khata entries."""
from enum import Enum
from typing import Dict, Optional

from app.models.user import utcnow
from app.utils.parsing import normalize_text


class EntryType(str, Enum):
    CREDIT = "credit"    # udhaar liya — customer owes more
    PAYMENT = "payment"  # paisa wapas diya — customer owes less


def customer_key(name: str) -> str:
    return normalize_text(name).lower()


def build_khata_entry(
    *, merchant_id, customer_name: str, amount: float, entry_type: str,
    description: str = "", customer_identifier: Optional[str] = None,
    source: str = "text",
) -> Dict:
    if entry_type not in {EntryType.CREDIT.value, EntryType.PAYMENT.value}:
        raise ValueError("Invalid khata entry type")
    normalized_name = normalize_text(customer_name).strip()
    if not normalized_name:
        raise ValueError("Customer name is required")
    return {
        "merchant_id": merchant_id,
        "customer_name": normalized_name.title(),
        "customer_key": customer_key(normalized_name),
        "customer_identifier": customer_identifier,
        "amount": round(float(amount), 2),
        "entry_type": entry_type,
        "description": description,
        "source": source,
        "created_at": utcnow(),
    }
