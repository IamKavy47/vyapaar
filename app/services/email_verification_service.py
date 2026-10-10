"""Email verification service — single-use, expiring, hashed-at-rest tokens.

Distinct from the phone OTP system (which verifies the user's phone). This
service verifies that the user actually controls the email address they
registered with — by sending them a one-time link containing a token.

Token lifecycle:
  - issue_token(user_id, email) — generates a 32-byte URL-safe token,
    stores its sha256 hash + user_id + email + expiry (24h default) in the
    `email_verification_tokens` collection. Returns the RAW token (only
    ever seen by the user via the email link).
  - verify_token(raw_token) — looks up by hash, checks expiry, returns
    the token doc on success. The caller is responsible for marking the
    user verified + deleting the token (single-use).
  - mark_verified(user_id) — sets user.email_verified=True +
    email_verified_at=now, deletes all tokens for this user.
  - resend(user_id, email) — issues a fresh token (deletes prior tokens
    for this user first, to prevent token farming).

For the hackathon demo, EMAIL_VERIFICATION_REQUIRED defaults to False
(hackathon flow needs to be demoable withoutSMTP friction); flip to True
in production to enforce email verification at login.
"""
import hashlib
import secrets
from datetime import timedelta
from typing import Dict, Optional

from bson import ObjectId

from app.config.settings import settings
from app.database import mongo as m
from app.models.user import utcnow
from app.utils.logging import get_logger

logger = get_logger(__name__)

# 32 bytes → 43 URL-safe base64 characters. Plenty of entropy.
TOKEN_BYTES = 32
# Default TTL 24 hours — long enough for a user to find the email,
# short enough that a leaked link self-expires.
DEFAULT_TTL_HOURS = 24


def _hash_token(raw: str) -> str:
    """sha256 — same scheme as phone OTP. Raw token never persisted."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _generate_raw_token() -> str:
    """Cryptographically random URL-safe token."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def is_email_verified(user_doc: Optional[Dict]) -> bool:
    """Check if a user's email has been verified. Defaults to False if the
    field is missing (e.g. users registered before this feature shipped)."""
    if not user_doc:
        return False
    return bool(user_doc.get("email_verified", False))


async def issue_token(*, user_id, email: str, ttl_hours: Optional[int] = None) -> str:
    """Issue a fresh email-verification token for this user.

    Deletes any prior tokens for this user first (one active token at a
    time). Returns the RAW token — the caller is responsible for putting
    it in the verification email link. The hash is what we store.
    """
    if ttl_hours is None:
        ttl_hours = settings.EMAIL_VERIFICATION_TOKEN_TTL_HOURS if hasattr(
            settings, "EMAIL_VERIFICATION_TOKEN_TTL_HOURS") else DEFAULT_TTL_HOURS
    now = utcnow()
    expires = now + timedelta(hours=ttl_hours)
    raw = _generate_raw_token()
    doc = {
        "user_id": ObjectId(str(user_id)),
        "email": email.strip().lower(),
        "token_hash": _hash_token(raw),
        "created_at": now,
        "expires_at": expires,
        "consumed_at": None,  # set when verify_token consumes it
    }
    # Delete prior tokens for this user — only one outstanding at a time.
    await m.email_verification_tokens().delete_many({"user_id": ObjectId(str(user_id))})
    await m.email_verification_tokens().insert_one(doc)
    logger.info("email verification token issued | user=%s email=%s expires=%s",
                user_id, email, expires.isoformat())
    return raw


async def verify_token(raw_token: str) -> Optional[Dict]:
    """Look up a token by its hash. Returns the token doc if found + not
    expired + not already consumed. Does NOT delete the token or mark the
    user verified — the caller (the API endpoint) is responsible for that,
    so the user's session can be created atomically with the verification."""
    if not raw_token or len(raw_token) < 16:
        return None
    h = _hash_token(raw_token)
    doc = await m.email_verification_tokens().find_one({"token_hash": h})
    if not doc:
        return None
    now = utcnow()
    expires = doc.get("expires_at")
    if not expires:
        return None
    if expires.tzinfo is None:
        from datetime import timezone
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < now:
        # Token expired — leave the doc so the user gets a clear "expired"
        # error message rather than a "not found" error. The TTL index
        # will clean it up later.
        return {"expired": True, **doc}
    if doc.get("consumed_at"):
        return {"consumed": True, **doc}
    return doc


async def mark_verified(*, user_id) -> bool:
    """Mark a user's email as verified and delete all outstanding tokens
    for them (single-use semantics)."""
    now = utcnow()
    result = await m.users().update_one(
        {"_id": ObjectId(str(user_id))},
        {"$set": {
            "email_verified": True,
            "email_verified_at": now,
            "updated_at": now,
        }},
    )
    # Always delete outstanding tokens, even if the user was already verified
    # (idempotent — clicking an old link after re-verifying shouldn't crash).
    await m.email_verification_tokens().delete_many({"user_id": ObjectId(str(user_id))})
    logger.info("email verified | user=%s modified=%s", user_id, result.modified_count)
    return result.modified_count > 0


async def resend_verification(*, user_id, email: str, full_name: str = "") -> str:
    """Re-issue a verification token (deletes prior tokens first) and
    return the raw token. Caller sends the email. Use this from the
    /auth/resend-verification endpoint after rate-limiting."""
    return await issue_token(user_id=user_id, email=email)


def build_verification_link(raw_token: str) -> str:
    """Build the URL that goes in the verification email. Points to the
    React frontend's /verify-email route, which calls the backend verify
    endpoint. The base URL is configurable via WEB_APP_BASE_URL (defaults
    to PUBLIC_BASE_URL for the monolith deployment)."""
    base = (settings.WEB_APP_BASE_URL or settings.PUBLIC_BASE_URL).rstrip("/")
    return f"{base}/verify-email?token={raw_token}"
