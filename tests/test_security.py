"""Password hashing, tokens, sessions, CSRF and rate limiting."""
from datetime import timedelta

from app.models.auth import TokenPurpose, build_auth_token_document
from app.models.user import utcnow
from app.utils.security import (
    RateLimiter, generate_token, hash_password, hash_token, issue_csrf_token, load_session,
    password_backend, sign_session, validate_csrf_token, verify_password,
)


def test_password_hash_is_not_plaintext():
    hashed = hash_password("SuperSecret123")
    assert "SuperSecret123" not in hashed
    assert len(hashed) > 20


def test_password_verifies():
    hashed = hash_password("SuperSecret123")
    assert verify_password("SuperSecret123", hashed)
    assert not verify_password("WrongPassword", hashed)


def test_hashes_are_salted():
    assert hash_password("SamePassword1") != hash_password("SamePassword1")


def test_short_password_rejected():
    try:
        hash_password("short")
        raise AssertionError("should have raised")
    except ValueError:
        pass


def test_backend_is_a_known_algorithm():
    assert password_backend() in {"argon2id", "bcrypt"}


def test_token_is_random_and_only_hash_is_stored():
    raw_a, hash_a = generate_token()
    raw_b, hash_b = generate_token()
    assert raw_a != raw_b
    assert hash_a != hash_b
    assert hash_a == hash_token(raw_a)
    assert raw_a not in hash_a


def test_auth_token_document_expires_in_ten_minutes():
    doc = build_auth_token_document(
        token_hash="abc", telegram_user_id=1, purpose=TokenPurpose.LINK_ACCOUNT.value,
        ttl_minutes=10,
    )
    delta = doc["expires_at"] - doc["created_at"]
    assert delta == timedelta(minutes=10)
    assert doc["used"] is False
    assert doc["expires_at"] > utcnow()


def test_session_signing_roundtrip():
    token = sign_session({"user": "abc"})
    assert load_session(token)["user"] == "abc"


def test_expired_session_is_rejected():
    token = sign_session({"user": "abc"})
    assert load_session(token, max_age_seconds=-1) is None


def test_tampered_session_is_rejected():
    token = sign_session({"user": "abc"})
    assert load_session(token + "x") is None


def test_csrf_roundtrip():
    assert validate_csrf_token(issue_csrf_token())
    assert not validate_csrf_token("not-a-token")
    assert not validate_csrf_token("")


def test_rate_limiter_blocks_after_limit():
    limiter = RateLimiter(limit=3, window_seconds=60)
    assert all(limiter.allow("1.2.3.4") for _ in range(3))
    assert not limiter.allow("1.2.3.4")
    assert limiter.allow("5.6.7.8")  # different key unaffected
