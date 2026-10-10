"""Email verification regression tests.

Pure-function tests for the new email_verification_service — no live MongoDB,
no live SMTP. Tests cover:
  - Token generation: 32-byte URL-safe raw token, sha256 hash
  - is_email_verified() handles missing field / True / False
  - build_verification_link() points to WEB_APP_BASE_URL or PUBLIC_BASE_URL
  - Token hash + length: raw token ≠ hash, hash is 64 hex chars
"""
import hashlib
import re

import pytest

from app.services import email_verification_service as evs
from app.config.settings import settings


# ------------------------------------------------------------- hashing + token gen

def test_hash_token_is_sha256_hex():
    """Raw token must never be stored — only its sha256 hex digest."""
    raw = "abc123"
    h = evs._hash_token(raw)
    assert h == hashlib.sha256(b"abc123").hexdigest()
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_hash_token_differs_for_different_inputs():
    assert evs._hash_token("a") != evs._hash_token("b")
    assert evs._hash_token("a") == evs._hash_token("a")


def test_generate_raw_token_is_url_safe_and_long_enough():
    """Generated token must be URL-safe (no / + =) and ≥32 chars for
    sufficient entropy (≥128 bits)."""
    token = evs._generate_raw_token()
    assert len(token) >= 32
    # URL-safe alphabet only
    assert re.fullmatch(r"[A-Za-z0-9_\-]+", token), (
        f"Token contains non-URL-safe chars: {token}"
    )


def test_generate_raw_token_is_unique():
    """Two consecutive calls must not collide (cryptographically random)."""
    t1 = evs._generate_raw_token()
    t2 = evs._generate_raw_token()
    assert t1 != t2


# ----------------------------------------------------- is_email_verified

def test_is_email_verified_handles_none():
    assert evs.is_email_verified(None) is False


def test_is_email_verified_handles_missing_field():
    """Old users registered before this feature shipped have no field."""
    assert evs.is_email_verified({"email": "x@y.com"}) is False


def test_is_email_verified_handles_false():
    assert evs.is_email_verified({"email_verified": False}) is False


def test_is_email_verified_handles_true():
    assert evs.is_email_verified({"email_verified": True}) is True


# ----------------------------------------------------- build_verification_link

def test_build_verification_link_uses_public_base_url_by_default():
    """If WEB_APP_BASE_URL is unset, link points to PUBLIC_BASE_URL."""
    # Save state to restore later
    saved = settings.WEB_APP_BASE_URL
    try:
        settings.WEB_APP_BASE_URL = ""
        link = evs.build_verification_link("tok_abc123")
        assert link.startswith(settings.PUBLIC_BASE_URL.rstrip("/"))
        assert "/verify-email?token=tok_abc123" in link
    finally:
        settings.WEB_APP_BASE_URL = saved


def test_build_verification_link_uses_web_app_base_url_when_set():
    saved = settings.WEB_APP_BASE_URL
    try:
        settings.WEB_APP_BASE_URL = "https://app.example.com"
        link = evs.build_verification_link("tok_xyz")
        assert link.startswith("https://app.example.com/verify-email")
        assert "token=tok_xyz" in link
    finally:
        settings.WEB_APP_BASE_URL = saved


def test_build_verification_link_strips_trailing_slash():
    saved = settings.WEB_APP_BASE_URL
    try:
        settings.WEB_APP_BASE_URL = "https://app.example.com/"
        link = evs.build_verification_link("t")
        # Must not have a double-slash
        assert "//verify-email" not in link
        assert link == "https://app.example.com/verify-email?token=t"
    finally:
        settings.WEB_APP_BASE_URL = saved


# ----------------------------------------------------- settings sanity

def test_email_verification_required_defaults_to_false_for_hackathon():
    """Production flips this to True. Default must remain False so the
    hackathon demo doesn't require SMTP to be functional."""
    assert settings.EMAIL_VERIFICATION_REQUIRED is False


def test_email_verification_token_ttl_is_24h():
    """24 hours is the documented sweet spot — long enough to find the email,
    short enough to self-expire before it leaks."""
    assert settings.EMAIL_VERIFICATION_TOKEN_TTL_HOURS == 24


# ----------------------------------------------------- token boundary checks

def test_verify_token_rejects_short_input():
    """A token shorter than 16 chars can't be valid — reject before any
    DB lookup to avoid needless queries."""
    import asyncio
    # We can't actually call verify_token (it hits the DB), but we can
    # assert the early-return logic. The function checks `len(raw_token) < 16`.
    # Using a token of length 15 should return None without touching the DB.
    # Run in an event loop — verify_token is async, but returns None
    # synchronously before the first await when the input is too short.
    async def run():
        return await evs.verify_token("a" * 15)
    result = asyncio.get_event_loop().run_until_complete(run())
    assert result is None


def test_verify_token_rejects_empty_input():
    import asyncio
    async def run():
        return await evs.verify_token("")
    result = asyncio.get_event_loop().run_until_complete(run())
    assert result is None


def test_verify_token_rejects_none_input():
    import asyncio
    async def run():
        return await evs.verify_token(None)
    result = asyncio.get_event_loop().run_until_complete(run())
    assert result is None
