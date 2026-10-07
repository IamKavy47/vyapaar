"""Password hashing, one-time auth tokens, signed sessions, CSRF, rate limiting."""
import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Optional, Tuple

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config.settings import settings

try:  # Argon2id preferred, bcrypt is the documented fallback.
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError

    _ph = PasswordHasher()
    _BACKEND = "argon2id"
except Exception:  # pragma: no cover - only when argon2-cffi is missing
    _ph = None
    _BACKEND = "bcrypt"
    import bcrypt as _bcrypt


def password_backend() -> str:
    return _BACKEND


def hash_password(password: str) -> str:
    if not password or len(password) < 8:
        raise ValueError("Password must be at least 8 characters long.")
    if _BACKEND == "argon2id":
        return _ph.hash(password)
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    if not password or not password_hash:
        return False
    if _BACKEND == "argon2id":
        try:
            return _ph.verify(password_hash, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False
        except Exception:
            return False
    try:
        return _bcrypt.checkpw(password.encode(), password_hash.encode())
    except Exception:
        return False


def needs_rehash(password_hash: str) -> bool:
    if _BACKEND != "argon2id":
        return False
    try:
        return _ph.check_needs_rehash(password_hash)
    except Exception:
        return False


# ---------------- One-time tokens ----------------
def generate_token() -> Tuple[str, str]:
    """Returns (raw_token, token_hash). Only the hash is ever persisted."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a or "", b or "")


# ---------------- Signed sessions ----------------
_serializer = URLSafeTimedSerializer(settings.SESSION_SECRET, salt="vyapaar-session")


def sign_session(payload: Dict) -> str:
    return _serializer.dumps(payload)


def load_session(token: str, max_age_seconds: Optional[int] = None) -> Optional[Dict]:
    if not token:
        return None
    max_age = max_age_seconds or settings.SESSION_TTL_HOURS * 3600
    try:
        return _serializer.loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None


# ---------------- CSRF ----------------
_csrf_serializer = URLSafeTimedSerializer(settings.SESSION_SECRET, salt="vyapaar-csrf")


def issue_csrf_token() -> str:
    return _csrf_serializer.dumps({"n": secrets.token_urlsafe(8)})


def validate_csrf_token(token: str, max_age_seconds: int = 3600) -> bool:
    if not token:
        return False
    try:
        _csrf_serializer.loads(token, max_age=max_age_seconds)
        return True
    except (BadSignature, SignatureExpired):
        return False


# ---------------- In-process rate limiter ----------------
class RateLimiter:
    """Sliding-window limiter. Deliberately in-process: no Redis for the MVP."""

    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        bucket = self._hits[key]
        while bucket and now - bucket[0] > self.window:
            bucket.popleft()
        if len(bucket) >= self.limit:
            return False
        bucket.append(now)
        return True

    def retry_after(self, key: str) -> int:
        bucket = self._hits.get(key)
        if not bucket:
            return 0
        return max(0, int(self.window - (time.monotonic() - bucket[0])) + 1)


auth_limiter = RateLimiter(settings.AUTH_RATE_LIMIT, settings.AUTH_RATE_WINDOW_SECONDS)
ai_limiter = RateLimiter(settings.AI_RATE_LIMIT, settings.AI_RATE_WINDOW_SECONDS)
