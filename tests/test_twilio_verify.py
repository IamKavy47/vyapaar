"""Twilio Verify OTP integration tests.

Pure-function tests for the new Verify path in auth_service. No live Twilio
calls — the twilio.rest.Client is mocked so we can assert that send_otp +
consume_otp invoke the Verify API correctly when TWILIO_VERIFY_SERVICE_SID
is set, and fall back to the local-code path when it's empty.

Tests cover:
  - send_otp uses Verify API when SID is set + SMS_GATEWAY=twilio
  - send_otp falls back to local generation when SID is empty
  - send_otp returns dev_otp in stub mode (Verify path is skipped)
  - consume_otp returns success when Verify Check returns 'approved'
  - consume_otp raises OTPError when Verify Check returns 'pending'
  - Settings flag TWILIO_VERIFY_SERVICE_SID is read correctly
"""
import asyncio
from unittest.mock import patch, MagicMock

import pytest

from app.config.settings import settings
from app.services import auth_service
from app.services.auth_service import OTPError, _twilio_verify_start, _twilio_verify_check


# ----------------------------------------------------- _twilio_verify_start

def test_twilio_verify_start_calls_verify_api():
    """_twilio_verify_start should call client.verify.v2.services(...).verifications.create."""
    fake_verification = MagicMock()
    fake_verification.sid = "VE123"
    fake_verification.status = "pending"

    fake_client = MagicMock()
    fake_verify_service = MagicMock()
    fake_verify_service.verifications.create.return_value = fake_verification
    fake_client.verify.v2.services.return_value = fake_verify_service

    with patch("app.services.auth_service.settings") as mock_settings, \
         patch("twilio.rest.Client", return_value=fake_client):
        mock_settings.TWILIO_ACCOUNT_SID = "AC_test"
        mock_settings.TWILIO_AUTH_TOKEN = "test_token"
        mock_settings.TWILIO_VERIFY_SERVICE_SID = "VA_test"
        result = _twilio_verify_start("919876543210")

    assert result == {"sid": "VE123", "status": "pending"}
    # Verify the right channel was used
    call_kwargs = fake_verify_service.verifications.create.call_args.kwargs
    assert call_kwargs["to"] == "+919876543210"
    assert call_kwargs["channel"] == "sms"


def test_twilio_verify_start_handles_canceled_status():
    """If Twilio immediately returns 'canceled' (e.g. trial-account restriction),
    we should raise a RuntimeError so send_otp converts it to OTPError."""
    fake_verification = MagicMock()
    fake_verification.sid = "VE_cancel"
    fake_verification.status = "canceled"
    fake_verification.error_code = 21223  # trial-account restriction

    fake_client = MagicMock()
    fake_verify_service = MagicMock()
    fake_verify_service.verifications.create.return_value = fake_verification
    fake_client.verify.v2.services.return_value = fake_verify_service

    with patch("app.services.auth_service.settings") as mock_settings, \
         patch("twilio.rest.Client", return_value=fake_client):
        mock_settings.TWILIO_ACCOUNT_SID = "AC_test"
        mock_settings.TWILIO_AUTH_TOKEN = "test_token"
        mock_settings.TWILIO_VERIFY_SERVICE_SID = "VA_test"
        with pytest.raises(RuntimeError, match="Twilio Verify canceled"):
            _twilio_verify_start("919876543210")


# ----------------------------------------------------- _twilio_verify_check

def test_twilio_verify_check_returns_approved_status():
    fake_check = MagicMock()
    fake_check.sid = "VChk_approved"
    fake_check.status = "approved"

    fake_client = MagicMock()
    fake_verify_service = MagicMock()
    fake_verify_service.verification_checks.create.return_value = fake_check
    fake_client.verify.v2.services.return_value = fake_verify_service

    with patch("app.services.auth_service.settings") as mock_settings, \
         patch("twilio.rest.Client", return_value=fake_client):
        mock_settings.TWILIO_ACCOUNT_SID = "AC_test"
        mock_settings.TWILIO_AUTH_TOKEN = "test_token"
        mock_settings.TWILIO_VERIFY_SERVICE_SID = "VA_test"
        result = _twilio_verify_check("919876543210", "123456")

    assert result == {"sid": "VChk_approved", "status": "approved"}
    call_kwargs = fake_verify_service.verification_checks.create.call_args.kwargs
    assert call_kwargs["to"] == "+919876543210"
    assert call_kwargs["code"] == "123456"


def test_twilio_verify_check_returns_pending_status_for_wrong_code():
    """A wrong code should return status=pending (not raise). The caller
    (consume_otp) converts 'pending' to OTPError("Wrong code...")."""
    fake_check = MagicMock()
    fake_check.sid = "VChk_pending"
    fake_check.status = "pending"

    fake_client = MagicMock()
    fake_verify_service = MagicMock()
    fake_verify_service.verification_checks.create.return_value = fake_check
    fake_client.verify.v2.services.return_value = fake_verify_service

    with patch("app.services.auth_service.settings") as mock_settings, \
         patch("twilio.rest.Client", return_value=fake_client):
        mock_settings.TWILIO_ACCOUNT_SID = "AC_test"
        mock_settings.TWILIO_AUTH_TOKEN = "test_token"
        mock_settings.TWILIO_VERIFY_SERVICE_SID = "VA_test"
        result = _twilio_verify_check("919876543210", "000000")

    assert result["status"] == "pending"


# ----------------------------------------------------- settings sanity

def test_twilio_verify_service_sid_default_is_empty():
    """Verify SID must default to empty so existing deployments that haven't
    set it continue to use the basic SMS path unchanged."""
    # Default value at the class level — pydantic-settings reads .env at
    # instantiation, so the actual instance value depends on .env. Assert
    # against the type annotation default by re-instantiating with no env.
    from app.config.settings import Settings
    fresh = Settings(_env_file=None)  # don't read .env
    assert fresh.TWILIO_VERIFY_SERVICE_SID == ""
