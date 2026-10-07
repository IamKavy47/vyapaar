"""Authentication: one-time Telegram links, registration, login, session handling.

Passwords never travel through Telegram and are never stored in plaintext.
Only the SHA-256 hash of an auth token is persisted.
"""
import secrets
from typing import Dict, Optional, Tuple

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.config.settings import settings
from app.database import mongo as m
from app.models.auth import TokenPurpose, build_auth_token_document, build_session_document
from app.models.customer import build_customer_document
from app.models.shop import CATEGORY_CAPABILITIES, build_shop_document, normalize_category
from app.models.user import UserRole, build_user_document, public_user, utcnow
from app.utils.geo import to_geojson_point
from app.utils.logging import get_logger
from app.utils.security import (
    generate_token, hash_password, hash_token, needs_rehash, verify_password,
)

logger = get_logger(__name__)


class AuthError(Exception):
    """User-facing auth failure. The message is safe to display."""


# ---------------- One-time link tokens ----------------
async def create_auth_link(telegram_user_id: int, purpose: str = TokenPurpose.LINK_ACCOUNT.value,
                           role_hint: Optional[str] = None) -> str:
    raw, token_hash = generate_token()
    doc = build_auth_token_document(
        token_hash=token_hash, telegram_user_id=telegram_user_id, purpose=purpose,
        ttl_minutes=settings.AUTH_TOKEN_TTL_MINUTES, role_hint=role_hint,
    )
    await m.auth_tokens().insert_one(doc)
    # Invalidate older unused tokens for this Telegram user.
    await m.auth_tokens().update_many(
        {"telegram_user_id": telegram_user_id, "used": False, "token_hash": {"$ne": token_hash}},
        {"$set": {"used": True}},
    )
    base = settings.PUBLIC_BASE_URL.rstrip("/")
    return f"{base}/auth/telegram?token={raw}"


async def resolve_auth_token(raw_token: str) -> Dict:
    """Validate without consuming. Raises AuthError with a friendly message."""
    if not raw_token:
        raise AuthError("This link is missing its token. Please request a new one from Telegram.")
    doc = await m.auth_tokens().find_one({"token_hash": hash_token(raw_token)})
    if not doc:
        raise AuthError("This link is not valid. Please request a fresh link from the bot.")
    if doc.get("used"):
        raise AuthError("This link has already been used. Please request a new one.")
    expires_at = doc.get("expires_at")
    if expires_at and expires_at.replace(tzinfo=expires_at.tzinfo or utcnow().tzinfo) < utcnow():
        raise AuthError("This link has expired. Links stay valid for 10 minutes.")
    return doc


async def consume_auth_token(raw_token: str) -> Dict:
    doc = await resolve_auth_token(raw_token)
    result = await m.auth_tokens().update_one(
        {"_id": doc["_id"], "used": False}, {"$set": {"used": True, "used_at": utcnow()}}
    )
    if result.modified_count != 1:  # lost a race — treat as already used
        raise AuthError("This link has already been used. Please request a new one.")
    return doc


# ---------------- Web -> Telegram linking ----------------
async def create_web_link_token(user_id) -> str:
    """One-time token for the reverse direction: a logged-in web user wants to
    attach their Telegram. The bot's ``/start web_<token>`` consumes it.

    Returns the raw token (never stored — only its SHA-256 hash is).
    """
    raw, token_hash = generate_token()
    doc = build_auth_token_document(
        token_hash=token_hash, telegram_user_id=None,
        purpose=TokenPurpose.LINK_ACCOUNT.value,
        ttl_minutes=settings.AUTH_TOKEN_TTL_MINUTES,
    )
    doc["web_user_id"] = ObjectId(str(user_id))
    await m.auth_tokens().insert_one(doc)
    # Invalidate older unused web-link tokens for this account.
    await m.auth_tokens().update_many(
        {"web_user_id": ObjectId(str(user_id)), "used": False,
         "token_hash": {"$ne": token_hash}},
        {"$set": {"used": True}},
    )
    return raw


async def consume_web_link_token(raw_token: str) -> Dict:
    """Validate + burn a web-link token. Returns the token doc (has web_user_id)."""
    doc = await consume_auth_token(raw_token)
    if not doc.get("web_user_id"):
        raise AuthError("This link is not valid. Please request a fresh one from the web app.")
    return doc


# ---------------- Registration / login ----------------
async def register_user(*, full_name: str, email: str, phone: str, password: str, role: str,
                        telegram_user_id: Optional[int] = None,
                        shop_name: Optional[str] = None, shop_category: Optional[str] = None,
                        latitude: Optional[float] = None, longitude: Optional[float] = None,
                        address: Optional[str] = None) -> Dict:
    email = email.strip().lower()
    existing = await m.users().find_one({"email": email})
    if existing:
        raise AuthError("An account with this email already exists. Please log in instead.")

    doc = build_user_document(
        full_name=full_name, email=email, phone=phone,
        password_hash=hash_password(password), role=role,
        telegram_user_id=telegram_user_id, is_verified=False,
    )
    try:
        result = await m.users().insert_one(doc)
    except DuplicateKeyError:
        raise AuthError("This email or Telegram account is already registered.")
    doc["_id"] = result.inserted_id
    await _ensure_role_profile(
        doc, shop_name=shop_name, shop_category=shop_category,
        latitude=latitude, longitude=longitude, address=address,
    )
    logger.info("user registered | role=%s id=%s category=%s located=%s",
                role, result.inserted_id, shop_category or "-",
                latitude is not None and longitude is not None)
    return doc


async def authenticate(email: str, password: str) -> Dict:
    user = await m.users().find_one({"email": email.strip().lower()})
    # Same message for both branches so we don't leak which emails exist.
    if not user or not verify_password(password, user.get("password_hash", "")):
        raise AuthError("Incorrect email or password.")
    if not user.get("is_active", True):
        raise AuthError("This account has been deactivated.")
    updates = {"last_login_at": utcnow(), "updated_at": utcnow()}
    if needs_rehash(user.get("password_hash", "")):
        updates["password_hash"] = hash_password(password)
    await m.users().update_one({"_id": user["_id"]}, {"$set": updates})
    return user


async def link_telegram_account(user_id, telegram_user_id: int, role_hint: Optional[str] = None) -> Dict:
    clash = await m.users().find_one({
        "telegram_user_id": telegram_user_id, "_id": {"$ne": ObjectId(str(user_id))}
    })
    if clash:
        raise AuthError("This Telegram account is already linked to a different user.")
    update = {"telegram_user_id": telegram_user_id, "updated_at": utcnow()}
    if role_hint in {UserRole.CUSTOMER.value, UserRole.SHOPKEEPER.value}:
        update["role"] = role_hint
    await m.users().update_one({"_id": ObjectId(str(user_id))}, {"$set": update})
    user = await m.users().find_one({"_id": ObjectId(str(user_id))})
    await _ensure_role_profile(user)
    logger.info("telegram linked | user=%s telegram=%s", user_id, telegram_user_id)
    return user


async def ensure_role_profile(user: Dict, **kwargs) -> None:
    """Public wrapper around _ensure_role_profile for the web API."""
    await _ensure_role_profile(user, **kwargs)


async def _ensure_role_profile(user: Dict, *, shop_name: Optional[str] = None,
                               shop_category: Optional[str] = None,
                               latitude: Optional[float] = None,
                               longitude: Optional[float] = None,
                               address: Optional[str] = None) -> None:
    """Every user gets the profile document matching their role.

    When a shopkeeper registers we already know their category and their pin —
    both are things that essentially never change — so the shop is created
    complete rather than as a placeholder the merchant has to repair later over
    chat. Existing shops are only topped up where a field is still empty, so
    re-linking Telegram never overwrites what a merchant edited by hand.
    """
    if not user:
        return
    role = user.get("role")
    uid, tg = user["_id"], user.get("telegram_user_id")
    if role == UserRole.SHOPKEEPER.value:
        existing = await m.shops().find_one({"user_id": uid})
        if not existing:
            await m.shops().insert_one(build_shop_document(
                user_id=uid,
                shop_name=shop_name or user.get("full_name") or "My Shop",
                phone=user.get("phone") or "",
                category=shop_category or "general_store",
                latitude=latitude, longitude=longitude,
                address=address or "",
                telegram_user_id=tg,
            ))
            return
        updates: Dict = {}
        if tg and existing.get("telegram_user_id") != tg:
            updates["telegram_user_id"] = tg
        if shop_category and not existing.get("category"):
            updates["category"] = normalize_category(shop_category)
            updates["capabilities"] = CATEGORY_CAPABILITIES.get(
                normalize_category(shop_category), []
            )
        if latitude is not None and longitude is not None and not existing.get("location"):
            updates["location"] = to_geojson_point(latitude, longitude)
        if address and not existing.get("address"):
            updates["address"] = address
        if updates:
            updates["updated_at"] = utcnow()
            await m.shops().update_one({"_id": existing["_id"]}, {"$set": updates})
    else:
        existing = await m.customers().find_one({"user_id": uid})
        if not existing:
            await m.customers().insert_one(
                build_customer_document(user_id=uid, telegram_user_id=tg)
            )
        elif tg and existing.get("telegram_user_id") != tg:
            await m.customers().update_one({"_id": existing["_id"]},
                                           {"$set": {"telegram_user_id": tg}})


async def logout_telegram(telegram_user_id: int) -> Optional[Dict]:
    """Unlink a Telegram account and end every session it owns.

    Logging out has to be thorough: the Telegram id is the only credential the
    bot has, so leaving it attached anywhere would let the next person holding
    that phone walk straight back into the account. We therefore clear it from
    the user, the shop and the customer profile, drop the web sessions, and burn
    any outstanding one-time links.

    The account itself survives untouched — shop, inventory, khata and history
    are all still there when the user logs back in.
    """
    user = await get_user_by_telegram_id(telegram_user_id)
    if not user:
        return None

    # $unset, never $set: None. The users index is unique+sparse, and sparse only
    # skips documents *missing* the field — an explicit null is indexed, so a
    # second logout would collide with the first on a duplicate null.
    await m.users().update_one(
        {"_id": user["_id"]},
        {"$unset": {"telegram_user_id": ""}, "$set": {"updated_at": utcnow()}},
    )
    await m.shops().update_many({"user_id": user["_id"]},
                                {"$unset": {"telegram_user_id": ""}})
    await m.customers().update_many({"user_id": user["_id"]},
                                    {"$unset": {"telegram_user_id": ""}})
    await m.sessions().delete_many({"user_id": user["_id"]})
    await m.auth_tokens().update_many(
        {"telegram_user_id": telegram_user_id, "used": False},
        {"$set": {"used": True, "used_at": utcnow()}},
    )
    logger.info("telegram logout | user=%s telegram=%s", user["_id"], telegram_user_id)
    return user


# ---------------- Lookups ----------------
async def get_user_by_telegram_id(telegram_user_id: int) -> Optional[Dict]:
    return await m.users().find_one({"telegram_user_id": telegram_user_id})


async def get_user_by_id(user_id) -> Optional[Dict]:
    try:
        return await m.users().find_one({"_id": ObjectId(str(user_id))})
    except Exception:
        return None


async def is_linked(telegram_user_id: int) -> bool:
    return await get_user_by_telegram_id(telegram_user_id) is not None


# ---------------- Sessions ----------------
async def create_session(user: Dict) -> str:
    session_id = secrets.token_urlsafe(24)
    await m.sessions().insert_one(build_session_document(
        session_id=session_id, user_id=user["_id"], role=user.get("role", "customer"),
        ttl_hours=settings.SESSION_TTL_HOURS,
    ))
    return session_id


async def get_session_user(session_id: str) -> Optional[Dict]:
    if not session_id:
        return None
    session = await m.sessions().find_one({"session_id": session_id})
    if not session:
        return None
    expires = session.get("expires_at")
    if expires and expires.replace(tzinfo=expires.tzinfo or utcnow().tzinfo) < utcnow():
        return None
    return await get_user_by_id(session["user_id"])


async def destroy_session(session_id: str) -> None:
    if session_id:
        await m.sessions().delete_one({"session_id": session_id})


def to_public(user: Optional[Dict]) -> Optional[Dict]:
    return public_user(user)


def require_role(user: Optional[Dict], *roles: str) -> Tuple[bool, str]:
    if not user:
        return False, "Please log in first."
    if user.get("role") == UserRole.ADMIN.value:
        return True, ""
    if roles and user.get("role") not in roles:
        return False, "You do not have permission to do that."
    return True, ""


# ---------------------------------------------------------------------- OTP
# Phone number verification via 6-digit OTP. The OTP is hashed at rest
# (sha256) — the raw code is only ever in the SMS gateway's hands, plus the
# server console in stub mode for hackathon convenience.

import hashlib


def _normalise_phone(phone: str) -> str:
    """Strip everything except digits and a leading +, so 91 prefixes and
    spaces / dashes don't fragment the lookup."""
    cleaned = "".join(c for c in (phone or "") if c.isdigit())
    if not cleaned:
        return ""
    # Indian numbers: assume 91 prefix if 12 digits starting with 91, else 10.
    if len(cleaned) == 12 and cleaned.startswith("91"):
        return cleaned
    if len(cleaned) == 10:
        return "91" + cleaned
    return cleaned


def _hash_otp(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _generate_otp(length: int = 6) -> str:
    """Cryptographically random numeric OTP of the given length."""
    alphabet = "0123456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


class OTPError(AuthError):
    """OTP-specific failures — wrong code, expired, no code sent, etc."""


async def send_otp(phone: str) -> Dict:
    """Generate + persist (hashed) + dispatch an OTP to the given phone.

    Returns ``{"sent": True, "dev_otp": "123456"}`` when OTP_STUB_MODE is on
    — the dev_otp field lets the hackathon UI paste the code from the network
    response without an SMS gateway. In production, dev_otp is None and the
    real SMS gateway (MSG91 / Twilio) carries the code.
    """
    from datetime import timedelta
    phone_norm = _normalise_phone(phone)
    if not phone_norm or len(phone_norm) < 12:
        raise OTPError("Phone number looks invalid — please enter a 10-digit Indian mobile.")

    # Invalidate any prior unused OTPs for this phone before issuing a new one.
    await m.otp_codes().update_many(
        {"phone": phone_norm, "used_at": None},
        {"$set": {"used_at": utcnow()}},
    )

    code = _generate_otp(settings.OTP_LENGTH)
    now = utcnow()
    expires_at = now + timedelta(minutes=settings.OTP_TTL_MINUTES)
    doc = {
        "phone": phone_norm,
        "code_hash": _hash_otp(code),
        "created_at": now,
        "expires_at": expires_at,
        "used_at": None,
        "attempts": 0,
    }
    await m.otp_codes().insert_one(doc)

    # Dispatch. In stub mode, log + return the raw code so the demo can paste
    # it from the server console or the network response.
    if settings.OTP_STUB_MODE or settings.SMS_GATEWAY == "stub":
        logger.warning("OTP (stub mode) | phone=%s code=%s", phone_norm, code)
        return {"sent": True, "dev_otp": code, "phone": phone_norm}

    # Production dispatch (placeholder for MSG91 / Twilio).
    try:
        await _dispatch_sms(phone_norm, f"{settings.APP_NAME}: your verification code is {code}. It expires in {settings.OTP_TTL_MINUTES} minutes.")
    except Exception as exc:
        logger.error("SMS dispatch failed | phone=%s | %s", phone_norm, exc)
        # Don't leak the code to the UI in production.
        raise OTPError("Could not send OTP. Please try again in a minute.") from exc

    return {"sent": True, "dev_otp": None, "phone": phone_norm}


async def verify_otp(phone: str, code: str) -> Dict:
    """Verify an OTP against the most recent unused one for the phone.

    On success: marks the OTP used, returns ``{ok: True, phone: ...}``.
    On failure: increments attempt count, raises OTPError with a user-safe
    message. After 5 failed attempts the OTP is auto-invalidated.
    """
    ok, record = await consume_otp(phone, code)  # raises OTPError on failure
    # Update the matching user (by phone). If no user has this phone yet,
    # the caller (registration) will use the OTP check as a pre-registration
    # gate — the verified_phone is returned for them to attach to the new
    # account.
    user = await m.users().find_one({"phone": record["phone"]})
    if user:
        await mark_phone_verified(user["_id"])
        return {"ok": True, "phone": record["phone"], "user_id": str(user["_id"])}
    return {"ok": True, "phone": record["phone"], "user_id": None}


async def consume_otp(phone: str, code: str) -> Tuple[bool, Dict]:
    """Pure OTP check + consume. Raises OTPError on failure.

    Returns ``(True, record)`` on success. Caller can use ``record['phone']``
    for downstream account creation. Does NOT touch the user table —
    ``mark_phone_verified`` does that separately.
    """
    phone_norm = _normalise_phone(phone)
    if not phone_norm:
        raise OTPError("Phone number is missing.")
    code = (code or "").strip()
    if not code or not code.isdigit() or len(code) != settings.OTP_LENGTH:
        raise OTPError(f"Code must be {settings.OTP_LENGTH} digits.")

    now = utcnow()
    record = await m.otp_codes().find_one({
        "phone": phone_norm,
        "used_at": None,
        "expires_at": {"$gt": now},
    }, sort=[("created_at", -1)])

    if not record:
        raise OTPError("No active OTP for this number — please request a new one.")

    if record.get("attempts", 0) >= 5:
        await m.otp_codes().update_one(
            {"_id": record["_id"]}, {"$set": {"used_at": now}},
        )
        raise OTPError("Too many wrong attempts — please request a new code.")

    if _hash_otp(code) != record["code_hash"]:
        await m.otp_codes().update_one(
            {"_id": record["_id"]}, {"$inc": {"attempts": 1}},
        )
        raise OTPError("Wrong code. Please check and try again.")

    await m.otp_codes().update_one(
        {"_id": record["_id"]}, {"$set": {"used_at": now}},
    )
    return True, record


async def mark_phone_verified(user_id) -> None:
    """Flip ``phone_verified`` to True for a user (used by both the
    standalone verify-otp endpoint and the registration flow)."""
    now = utcnow()
    await m.users().update_one(
        {"_id": user_id},
        {"$set": {
            "phone_verified": True,
            "phone_verified_at": now,
            "updated_at": now,
        }},
    )


async def is_phone_verified(user_id) -> bool:
    user = await get_user_by_id(user_id)
    return bool(user and user.get("phone_verified"))


async def _dispatch_sms(phone: str, text: str) -> None:
    """Production SMS dispatch — placeholder for MSG91 / Twilio."""
    if settings.SMS_GATEWAY == "msg91":
        # TODO: wire MSG91 transactional SMS API.
        # https://api.msg91.com/apidoc/textsms/sendv5
        logger.warning("MSG91 SMS gateway not yet wired — message dropped | to=%s", phone)
        return
    if settings.SMS_GATEWAY == "twilio":
        # TODO: wire Twilio Programmable SMS.
        logger.warning("Twilio SMS gateway not yet wired — message dropped | to=%s", phone)
        return
    # Default: no-op (stub mode handled by the caller).
    return
