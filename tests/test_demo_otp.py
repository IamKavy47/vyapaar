"""Demo OTP path tests.

When OTP_STUB_MODE=true, the OTP must be the fixed demo code from
OTP_DEMO_CODE (default "123456"). This makes the hackathon demo frictionless:
the frontend auto-fills the input + shows a banner, so judges can just
click through registration without typing. The hash check in consume_otp
still validates the code — demo OTPs are real OTPs, just predictable.
"""
import pytest

from app.config.settings import Settings
from app.services.auth_service import _generate_otp, _hash_otp


# ----------------------------------------------------- _generate_otp demo path

def test_generate_otp_returns_demo_code_in_stub_mode():
    """When OTP_STUB_MODE=true, the generated OTP must be OTP_DEMO_CODE."""
    settings = Settings(_env_file=None)  # fresh instance, defaults only
    assert settings.OTP_STUB_MODE is True
    assert settings.OTP_DEMO_CODE == "123456"
    # Replace the module-level settings instance with our test instance
    # for the duration of the function call.
    import app.services.auth_service as svc
    saved = svc.settings
    try:
        svc.settings = settings
        code = _generate_otp(6)
    finally:
        svc.settings = saved
    assert code == "123456"


def test_generate_otp_returns_random_code_in_production_mode():
    """When OTP_STUB_MODE=false, the OTP must be cryptographically random
    (different from the demo code on every call, 6 digits, numeric only)."""
    settings = Settings(_env_file=None)
    settings.OTP_STUB_MODE = False
    import app.services.auth_service as svc
    saved = svc.settings
    try:
        svc.settings = settings
        code1 = _generate_otp(6)
        code2 = _generate_otp(6)
    finally:
        svc.settings = saved
    assert len(code1) == 6
    assert code1.isdigit()
    # Random codes are extremely unlikely to collide on consecutive calls.
    assert code1 != code2
    # Random code shouldn't always be 123456 (would be a broken stub path).
    # Allow at most one of the two to coincidentally equal the demo code.
    assert not (code1 == "123456" and code2 == "123456")


def test_generate_otp_respects_custom_demo_code():
    """If OTP_DEMO_CODE is overridden, the generated OTP must use the override."""
    settings = Settings(_env_file=None)
    settings.OTP_DEMO_CODE = "999999"
    import app.services.auth_service as svc
    saved = svc.settings
    try:
        svc.settings = settings
        code = _generate_otp(6)
    finally:
        svc.settings = saved
    assert code == "999999"


def test_generate_otp_pads_short_demo_code():
    """If OTP_DEMO_CODE is shorter than OTP_LENGTH, pad with zeros so the
    consume-side digit-length check still passes."""
    settings = Settings(_env_file=None)
    settings.OTP_DEMO_CODE = "123"  # shorter than 6
    import app.services.auth_service as svc
    saved = svc.settings
    try:
        svc.settings = settings
        code = _generate_otp(6)
    finally:
        svc.settings = saved
    assert code == "123000"
    assert len(code) == 6


def test_generate_otp_truncates_long_demo_code():
    """If OTP_DEMO_CODE is longer than OTP_LENGTH, truncate to match."""
    settings = Settings(_env_file=None)
    settings.OTP_DEMO_CODE = "1234567890"  # 10 digits
    import app.services.auth_service as svc
    saved = svc.settings
    try:
        svc.settings = settings
        code = _generate_otp(6)
    finally:
        svc.settings = saved
    assert code == "123456"
    assert len(code) == 6


# ----------------------------------------------------- hash check still validates

def test_demo_otp_hash_matches():
    """The demo code's hash must match what _hash_otp produces — so the
    existing consume_otp hash comparison still works against demo OTPs."""
    code = "123456"
    stored_hash = _hash_otp(code)
    # The hash of the same code must equal the stored hash.
    assert _hash_otp(code) == stored_hash
    # The hash of a different code must NOT equal the stored hash.
    assert _hash_otp("999999") != stored_hash


# ----------------------------------------------------- settings sanity

def test_otp_demo_code_default_is_123456():
    """Default must be '123456' so the .env.example docs match the code."""
    settings = Settings(_env_file=None)
    assert settings.OTP_DEMO_CODE == "123456"


def test_otp_stub_mode_default_is_true():
    """Default must be True so the hackathon demo works without SMTP/Twilio."""
    settings = Settings(_env_file=None)
    assert settings.OTP_STUB_MODE is True
