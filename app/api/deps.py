"""Shared API dependencies: templates, sessions, rate limiting."""
from pathlib import Path
from typing import Dict, Optional

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.config.settings import settings
from app.services import auth_service
from app.utils.security import auth_limiter

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

SESSION_COOKIE = "vm_session"


def client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check_auth_rate_limit(request: Request) -> bool:
    return auth_limiter.allow(f"http:{client_key(request)}")


async def current_web_user(request: Request) -> Optional[Dict]:
    return await auth_service.get_session_user(request.cookies.get(SESSION_COOKIE, ""))


def set_session_cookie(response, session_id: str) -> None:
    response.set_cookie(
        SESSION_COOKIE, session_id, httponly=True, samesite="lax",
        secure=settings.COOKIE_SECURE, max_age=settings.SESSION_TTL_HOURS * 3600,
    )


def clear_session_cookie(response) -> None:
    response.delete_cookie(SESSION_COOKIE)
