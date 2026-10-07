"""One-time auth tokens and server-side sessions."""
from datetime import timedelta
from enum import Enum
from typing import Dict, Optional

from app.models.user import utcnow


class TokenPurpose(str, Enum):
    LOGIN = "login"
    REGISTRATION = "registration"
    LINK_ACCOUNT = "link_account"
    EMAIL_VERIFICATION = "email_verification"


def build_auth_token_document(
    *, token_hash: str, telegram_user_id: Optional[int], purpose: str,
    ttl_minutes: int, role_hint: Optional[str] = None,
) -> Dict:
    now = utcnow()
    return {
        "token_hash": token_hash,
        "telegram_user_id": telegram_user_id,
        "purpose": purpose,
        "role_hint": role_hint,
        "used": False,
        "created_at": now,
        "expires_at": now + timedelta(minutes=ttl_minutes),
    }


def build_session_document(*, session_id: str, user_id, role: str, ttl_hours: int) -> Dict:
    now = utcnow()
    return {
        "session_id": session_id,
        "user_id": user_id,
        "role": role,
        "created_at": now,
        "expires_at": now + timedelta(hours=ttl_hours),
    }
