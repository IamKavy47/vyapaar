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
        # Email verification — link-based, single-use, hashed-at-rest tokens
        # issued via email_verification_service.issue_token(). Stays False
        # until the user clicks the link in their verification email.
        "email_verified": False,
        "email_verified_at": None,
        # Pro subscription — timestamp when the current Pro period expires.
        # None means the user has never had Pro (or has been revoked).
        # The /merchant/subscribe endpoint grants a 14-day trial (hackathon
        # demo) or a 30-day paid period (production, post-Razorpay).
        "pro_expires_at": None,
        "pro_trial_used": False,  # has the user used their 14-day free trial?
        "pro_subscribed_at": None,
        "created_at": now,
        "updated_at": now,
        "last_login_at": None,
    }


def public_user(doc: Optional[Dict]) -> Optional[Dict]:
    """Never leak password_hash outside the auth service."""
    if not doc:
        return None
    from app.services.subscription_service import is_pro
    return {
        "id": str(doc.get("_id")),
        "full_name": doc.get("full_name"),
        "email": doc.get("email"),
        "phone": doc.get("phone"),
        "role": doc.get("role"),
        "telegram_user_id": doc.get("telegram_user_id"),
        "is_verified": doc.get("is_verified", False),
        "phone_verified": doc.get("phone_verified", False),
        "email_verified": doc.get("email_verified", False),
        "email_verified_at": (
            doc.get("email_verified_at").isoformat()
            if doc.get("email_verified_at") else None
        ),
        "trusted_contact_phone": doc.get("trusted_contact_phone"),
        "is_active": doc.get("is_active", True),
        # Pro subscription status — computed from pro_expires_at vs now.
        "is_pro": is_pro(doc),
        "pro_expires_at": doc.get("pro_expires_at").isoformat() if doc.get("pro_expires_at") else None,
        "pro_trial_used": doc.get("pro_trial_used", False),
        "created_at": doc.get("created_at"),
    }
