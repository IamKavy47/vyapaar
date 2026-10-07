"""Structured-ish logging with a per-request correlation id: [REQ-123] ..."""
import contextvars
import logging
import sys
import uuid

request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


def new_request_id(prefix: str = "REQ") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


def bind_request_id(request_id: str) -> None:
    request_id_ctx.set(request_id)


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        return True


_SENSITIVE = ("password", "token", "api_key", "secret", "authorization")


class RedactFilter(logging.Filter):
    """Best-effort guard so secrets never reach the logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = str(record.msg).lower()
        except Exception:
            return True
        if any(word in msg for word in _SENSITIVE) and "=" in msg:
            record.msg = "[redacted log line containing sensitive keyword]"
            record.args = ()
        return True


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-7s | [%(request_id)s] %(name)s: %(message)s")
    )
    handler.addFilter(RequestIdFilter())
    handler.addFilter(RedactFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    for noisy in ("httpx", "httpcore", "pymongo", "telegram.ext.Application", "apscheduler"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
