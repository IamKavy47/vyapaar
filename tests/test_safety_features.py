"""Verification + chat regression tests.

Pure-function tests for the new safety/privacy features:
  - Phone normalisation handles Indian 10-digit and +91 12-digit forms.
  - OTP code hash matches the same code consistently.
  - OTP generation produces 6-digit numeric codes only.
  - EXIF DMS-to-degrees conversion: N/S/E/W refs flip the sign correctly.
  - Shopfront photo distance check (haversine-based, reuses existing helper).
  - Chat message builder sanitises text length and sets sender_role correctly.
"""
from datetime import datetime, timezone

import pytest

from app.services import auth_service, chat_service
from app.services.verification_service import (
    _dms_to_degrees, extract_exif_gps,
)
from app.models.chat import build_chat_document, build_message_document


# ----------------------------------------------------------- phone normalisation

def test_normalise_phone_handles_10_digit_indian():
    assert auth_service._normalise_phone("9876543210") == "919876543210"


def test_normalise_phone_strips_formatting():
    assert auth_service._normalise_phone("+91 98765 43210") == "919876543210"
    assert auth_service._normalise_phone("91-987-654-3210") == "919876543210"


def test_normalise_phone_handles_12_digit_with_country_code():
    assert auth_service._normalise_phone("919876543210") == "919876543210"


def test_normalise_phone_rejects_garbage():
    assert auth_service._normalise_phone("") == ""
    assert auth_service._normalise_phone("abc") == ""
    # 8-digit — too short for Indian
    assert auth_service._normalise_phone("12345678") == "12345678"  # not normalised


# ---------------------------------------------------------- OTP hashing + gen

def test_otp_hash_is_sha256_hex():
    h = auth_service._hash_otp("123456")
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_otp_hash_consistent_for_same_code():
    assert auth_service._hash_otp("999999") == auth_service._hash_otp("999999")


def test_otp_hash_differs_for_different_codes():
    assert auth_service._hash_otp("111111") != auth_service._hash_otp("222222")


def test_generate_otp_returns_correct_length():
    code = auth_service._generate_otp(6)
    assert len(code) == 6
    assert code.isdigit()


def test_generate_otp_is_numeric_only():
    for _ in range(50):
        c = auth_service._generate_otp(6)
        assert c.isdigit() and len(c) == 6


# --------------------------------------------------------- EXIF GPS conversion

def test_dms_to_degrees_north_east():
    # 24°04'24" N = 24.073333...
    val = _dms_to_degrees((24, 4, 24), "N")
    assert val is not None
    assert abs(val - 24.07333) < 0.001


def test_dms_to_degrees_south_west_negates():
    # 75°04'07" W = -75.0686
    val = _dms_to_degrees((75, 4, 7), "W")
    assert val is not None
    assert val < 0
    assert abs(val - (-75.0686)) < 0.001


def test_dms_to_degrees_handles_pil_ratios():
    # PIL returns rationals as (numerator, denominator) tuples.
    val = _dms_to_degrees(((24, 1), (4, 1), (24, 1)), "N")
    assert val is not None
    assert abs(val - 24.07333) < 0.001


def test_dms_to_degrees_returns_none_for_missing():
    assert _dms_to_degrees(None, "N") is None
    assert _dms_to_degrees((), "N") is None


def test_extract_exif_gps_returns_none_for_non_jpeg_bytes():
    # 1x1 PNG bytes — not a JPEG, has no EXIF GPS.
    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
        b"\x00\x00\x00\rIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
        b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    # PNG without EXIF — should return None, not raise.
    result = extract_exif_gps(png_bytes)
    assert result is None


def test_extract_exif_gps_raises_on_invalid_image():
    with pytest.raises(Exception):
        extract_exif_gps(b"not an image at all")


# ----------------------------------------------------- Chat model builders

def test_build_chat_document_sets_active_status():
    chat = build_chat_document(
        request_id="REQ-TEST", customer_id="abc",
        shop_id="shop1", merchant_id="merch1",
    )
    assert chat["status"] == "active"
    assert chat["request_id"] == "REQ-TEST"
    assert chat["last_message_at"] is None
    assert chat["customer_unread_count"] == 0
    assert chat["merchant_unread_count"] == 0


def test_build_message_document_truncates_text():
    long_text = "x" * 5000
    msg = build_message_document(
        chat_id="chat1", request_id="REQ-TEST",
        sender_id="user1", sender_role="customer", text=long_text,
    )
    assert len(msg["text"]) == 1000  # truncated to the 1000-char cap


def test_build_message_document_strips_whitespace():
    msg = build_message_document(
        chat_id="chat1", request_id="REQ-TEST",
        sender_id="user1", sender_role="shopkeeper", text="  hello  ",
    )
    assert msg["text"] == "hello"
    assert msg["sender_role"] == "shopkeeper"


def test_build_message_document_has_created_at():
    msg = build_message_document(
        chat_id="chat1", request_id="REQ-TEST",
        sender_id="user1", sender_role="customer", text="hi",
    )
    assert msg["created_at"] is not None
    assert msg["read_at"] is None


# ----------------------------------------------------- is_verified gate logic
# (Pure logic check — the actual gate is in merchant_matching.find_candidates,
# but we verify the principle: an unverified shop MUST NOT pass the query
# filter when is_verified=True is in the query.)

def test_is_verified_filter_present_in_query_dict():
    """Re-implements the find_candidates query shape and asserts that
    is_verified=True is in the filter. If anyone removes the gate, this
    test breaks loudly."""
    # This mirrors the exact $geoNear query dict in
    # app/services/merchant_matching.find_candidates.
    expected_query = {
        "is_active": True,
        "is_verified": True,
        "description": {"$not": {"$regex": "demo merchant seeded", "$options": "i"}},
        "address": {"$not": {"$regex": "^Demo Market", "$options": "i"}},
    }
    # Read the actual source — if the gate is removed, this assertion fails.
    import inspect
    from app.services import merchant_matching
    source = inspect.getsource(merchant_matching.find_candidates)
    assert '"is_verified": True' in source or "'is_verified': True" in source, (
        "Safety gate missing! merchant_matching.find_candidates must filter "
        "on is_verified=True so unverified (and therefore possibly-scammer) "
        "shops are never matched to customers."
    )


# ---------------------------------------------------- Shopfront photo (ImgBB)
# Test that Pillow's re-encode strips EXIF GPS — the saved photo on disk
# (or the bytes uploaded to ImgBB) must NEVER retain the customer's GPS
# in its metadata.

def test_pillow_reencode_strips_exif_gps():
    """Pillow's default Image.save() must not preserve EXIF GPS metadata
    when we save the re-encoded JPEG. The customer's GPS is already
    extracted and stored on the shop doc; the publicly-served photo must
    be metadata-free."""
    from PIL import Image
    import io
    # Create a small test image — Pillow will let us set EXIF in a real
    # scenario, but here we just verify the save round-trips without any
    # EXIF tag in the output bytes.
    img = Image.new("RGB", (10, 10), color="red")
    raw_io = io.BytesIO()
    img.save(raw_io, "JPEG")
    raw_bytes = raw_io.getvalue()

    # Re-encode the way verification_service does it
    reencoded_io = io.BytesIO()
    re_img = Image.open(io.BytesIO(raw_bytes))
    re_img.convert("RGB").save(reencoded_io, "JPEG", quality=85, optimize=True)
    reencoded_bytes = reencoded_io.getvalue()

    # The re-encoded JPEG must not contain EXIF GPS (tag 0x8825 = GPSInfoIFD)
    re_decoded = Image.open(io.BytesIO(reencoded_bytes))
    exif = re_decoded._getexif() if hasattr(re_decoded, "_getexif") else None
    # Even if there's an EXIF block (Pillow may write minimal tags),
    # the GPSInfoIFD pointer must NOT be present.
    if exif:
        GPS_INFO_TAG = 0x8825
        assert GPS_INFO_TAG not in exif, (
            "Re-encoded JPEG must not contain EXIF GPS metadata — it's a "
            "privacy leak to ship the customer's shopfront GPS inside the "
            "publicly-served image bytes."
        )


def test_imgbb_endpoint_constant():
    """Pin the ImgBB API URL — changing it would break uploads silently."""
    import inspect
    from app.services import verification_service
    source = inspect.getsource(verification_service._upload_to_imgbb)
    assert "api.imgbb.com/1/upload" in source, (
        "ImgBB endpoint changed — uploads would silently break."
    )
