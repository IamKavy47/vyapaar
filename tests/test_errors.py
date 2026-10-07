"""Error taxonomy tests. No third-party deps, so these always run offline."""
from app.utils.errors import (
    AppError, ConfigurationError, DatabaseError, ExternalServiceError, NotFound,
    ValidationFailed, describe_unexpected, new_error_ref,
)


def test_error_ref_has_expected_shape():
    ref = new_error_ref()
    assert ref.startswith("ERR-")
    assert len(ref) == 10  # "ERR-" + 6 hex chars


def test_error_ref_is_unique_per_call():
    assert new_error_ref() != new_error_ref()


def test_actionable_error_has_no_reference_in_user_text():
    err = ValidationFailed("bad phone", user_message="Please enter a valid phone number.")
    assert err.user_text() == "Please enter a valid phone number."
    assert "ERR-" not in err.user_text()


def test_non_actionable_error_shows_reference():
    err = DatabaseError("connection reset")
    text = err.user_text()
    assert err.ref in text


def test_debug_line_carries_operation_and_context():
    err = NotFound("shop missing", operation="browse.get_shop",
                   context={"shop_id": "abc123"})
    line = err.debug_line()
    assert "op=browse.get_shop" in line
    assert "shop_id=abc123" in line
    assert err.ref in line


def test_debug_line_carries_cause():
    cause = ValueError("bad objectid")
    err = ValidationFailed("could not parse id", cause=cause)
    assert "ValueError" in err.debug_line()


def test_external_service_error_records_service_name():
    err = ExternalServiceError("timed out", service="gemini")
    assert err.context["service"] == "gemini"
    assert "service=gemini" in err.debug_line()


def test_configuration_error_records_setting_name():
    err = ConfigurationError("missing SMTP host", setting="SMTP_HOST")
    assert err.context["setting"] == "SMTP_HOST"


def test_http_status_defaults_are_sane():
    assert ValidationFailed("x").http_status == 400
    assert NotFound("x").http_status == 404
    assert DatabaseError("x").http_status == 503


def test_to_dict_never_leaks_internal_message():
    err = DatabaseError("password=hunter2 in connection string")
    payload = err.to_dict()
    assert "hunter2" not in payload["detail"]
    assert payload["ref"] == err.ref


def test_describe_unexpected_includes_exception_type_and_context():
    try:
        raise KeyError("missing_field")
    except KeyError as exc:
        line = describe_unexpected(exc, operation="test.op", context={"x": 1})
    assert "KeyError" in line
    assert "op=test.op" in line
    assert "x=1" in line
