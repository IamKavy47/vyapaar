"""User document model + role enum."""
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Optional


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserRole(str, Enum):
    CUSTOMER = "customer"
    SHOPKEEPER = "shopkeeper"
    ADMIN = "admin"


def build_user_document(
    *,
    full_name: str,
    email: str,
    phone: str,
    password_hash: str,
    role: str,
    telegram_user_id: Optional[int] = None,
    is_verified: bool = False,
) -> Dict:
    now = utcnow()
    return {
        "telegram_user_id": telegram_user_id,
        "full_name": full_name.strip(),
        "email": email.strip().lower(),
        "phone": phone.strip(),
        "password_hash": password_hash,
        "role": role,
        "is_verified": is_verified,
        "is_active": True,
        # Phone OTP verification — mandatory before any real action
        # (search, accept/reject a request, choose an offer, panic, etc.).
        # The OTP stub flow flips this to True on successful verify.
        "phone_verified": False,
        "phone_verified_at": None,
        # Trusted contact for the panic button — captured during customer
        # onboarding. Optional but recommended.
        "trusted_contact_phone": None,
        "created_at": now,
        "updated_at": now,
        "last_login_at": None,
    }


def public_user(doc: Optional[Dict]) -> Optional[Dict]:
    """Never leak password_hash outside the auth service."""
    if not doc:
        return None
    return {
        "id": str(doc.get("_id")),
        "full_name": doc.get("full_name"),
        "email": doc.get("email"),
        "phone": doc.get("phone"),
        "role": doc.get("role"),
        "telegram_user_id": doc.get("telegram_user_id"),
        "is_verified": doc.get("is_verified", False),
        "phone_verified": doc.get("phone_verified", False),
        "trusted_contact_phone": doc.get("trusted_contact_phone"),
        "is_active": doc.get("is_active", True),
        "created_at": doc.get("created_at"),
    }
