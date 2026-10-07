"""Error taxonomy.

Two audiences, one exception:

* the **user** sees ``user_message`` — short, in Hinglish, never technical;
* the **developer** sees ``debug_line()`` in the logs — error code, correlation id,
  the operation that failed and whatever context was attached.

Every raised AppError carries a short ``ref`` (e.g. ``ERR-7A3C91``). That same ref
is shown to the user and written to the log, so a screenshot from a demo can be
grepped straight to the stack trace that produced it.
"""
import uuid
from typing import Any, Dict, Optional

from app.utils.logging import request_id_ctx

GENERIC_USER_MESSAGE = "⚠️ Kuch technical dikkat aa gayi. Kripya dobara try kijiye."


def new_error_ref() -> str:
    return f"ERR-{uuid.uuid4().hex[:6].upper()}"


class AppError(Exception):
    """Base class for every error this application raises deliberately.

    Anything that is *not* an AppError is, by definition, a bug we did not
    anticipate — the handlers log those at exception level with a full traceback.
    """

    code = "APP_ERROR"
    http_status = 500
    # Whether the user is expected to be able to fix this by doing something.
    actionable = False

    def __init__(self, message: str, *, user_message: Optional[str] = None,
                 operation: str = "", context: Optional[Dict[str, Any]] = None,
                 cause: Optional[BaseException] = None):
        super().__init__(message)
        self.message = message
        self.user_message = user_message or GENERIC_USER_MESSAGE
        self.operation = operation
        self.context = dict(context or {})
        self.cause = cause
        self.ref = new_error_ref()
        self.request_id = request_id_ctx.get()

    def debug_line(self) -> str:
        """One dense line carrying everything needed to find this in the logs."""
        parts = [
            f"ref={self.ref}",
            f"code={self.code}",
            f"request_id={self.request_id}",
        ]
        if self.operation:
            parts.append(f"op={self.operation}")
        parts.append(f"msg={self.message}")
        if self.cause is not None:
            parts.append(f"cause={self.cause.__class__.__name__}: {self.cause}")
        for key, value in self.context.items():
            parts.append(f"{key}={_short(value)}")
        return " | ".join(parts)

    def user_text(self) -> str:
        """What the customer or shopkeeper actually reads."""
        if self.actionable:
            return self.user_message
        return f"{self.user_message}\n\n🔎 Reference: {self.ref}"

    def to_dict(self) -> Dict[str, Any]:
        return {"error": self.code, "detail": self.user_message, "ref": self.ref,
                "request_id": self.request_id}


def _short(value: Any, limit: int = 120) -> str:
    text = str(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


# ---------------- Concrete errors ----------------
class ValidationFailed(AppError):
    """The user gave us something we cannot work with. Their move next."""

    code = "VALIDATION_FAILED"
    http_status = 400
    actionable = True


class NotFound(AppError):
    """A document we expected to exist does not."""

    code = "NOT_FOUND"
    http_status = 404
    actionable = True


class PermissionDenied(AppError):
    code = "PERMISSION_DENIED"
    http_status = 403
    actionable = True


class DatabaseError(AppError):
    """MongoDB is unreachable, timed out, or rejected a write."""

    code = "DATABASE_ERROR"
    http_status = 503

    def __init__(self, message: str, **kwargs):
        kwargs.setdefault(
            "user_message",
            "⚠️ Database abhi respond nahi kar raha. Kuch minute baad try kijiye.",
        )
        super().__init__(message, **kwargs)


class ExternalServiceError(AppError):
    """An upstream we do not control failed: an AI provider, SMTP, Telegram."""

    code = "EXTERNAL_SERVICE_ERROR"
    http_status = 502

    def __init__(self, message: str, *, service: str = "", **kwargs):
        context = dict(kwargs.pop("context", None) or {})
        if service:
            context["service"] = service
        kwargs.setdefault(
            "user_message",
            "⚠️ Ek service abhi available nahi hai. Thodi der baad try kijiye.",
        )
        super().__init__(message, context=context, **kwargs)
        self.service = service


class ConfigurationError(AppError):
    """A required key or setting is missing. Almost always a deployment mistake."""

    code = "CONFIGURATION_ERROR"
    http_status = 500

    def __init__(self, message: str, *, setting: str = "", **kwargs):
        context = dict(kwargs.pop("context", None) or {})
        if setting:
            context["setting"] = setting
        kwargs.setdefault(
            "user_message",
            "⚠️ Yeh feature abhi configure nahi hua hai. Admin ko bataiye.",
        )
        super().__init__(message, context=context, **kwargs)
        self.setting = setting


def describe_unexpected(exc: BaseException, *, operation: str = "",
                        context: Optional[Dict[str, Any]] = None) -> str:
    """Debug line for an exception that is *not* one of ours."""
    parts = [f"code=UNEXPECTED", f"request_id={request_id_ctx.get()}"]
    if operation:
        parts.append(f"op={operation}")
    parts.append(f"exc={exc.__class__.__module__}.{exc.__class__.__name__}: {exc}")
    for key, value in (context or {}).items():
        parts.append(f"{key}={_short(value)}")
    return " | ".join(parts)
