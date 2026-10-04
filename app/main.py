"""FastAPI application entry point.

Architecture:
    Telegram -> FastAPI -> Business services -> MongoDB
    React web app (web/) --/api/v1--^      |
                              +-> AI services (Sarvam / Gemini / Groq / GPT-OSS)

FastAPI serves:
  - the Telegram webhook/polling bot (app/bot)
  - the JSON REST API for the React web app (app/api/web.py, prefix /api/v1)
  - the built React app itself at / when web/dist exists (SPA fallback)
  - the legacy minimal HTML auth pages under /auth
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import auth as auth_api
from app.api import demand as demand_api
from app.api import health as health_api
from app.api import requests as requests_api
from app.api import shops as shops_api
from app.api import web as web_api
from app.bot.bot import start_bot, stop_bot
from app.config.settings import settings
from app.database.indexes import create_indexes
from app.database.mongo import close_mongo_connection, connect_to_mongo, mongo
from app.services.scheduler import start_scheduler, stop_scheduler
from app.utils.errors import AppError, describe_unexpected, new_error_ref
from app.utils.logging import bind_request_id, get_logger, new_request_id, setup_logging

setup_logging(settings.LOG_LEVEL)
logger = get_logger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s (demo_mode=%s)", settings.APP_NAME, settings.DEMO_MODE)

    connected = await connect_to_mongo()
    if connected:
        await create_indexes()
    else:
        logger.error("Running WITHOUT a database — most features will be unavailable")

    bot_task = None
    if settings.RUN_BOT:
        try:
            bot_task = await start_bot()
        except Exception as exc:
            logger.error("Telegram bot failed to start: %s", exc)

    scheduler = None
    # Background schedulers are opt-in. Request-based platforms may create
    # multiple app instances, which would duplicate interval/cron jobs.
    if settings.ENABLE_SCHEDULER:
        try:
            scheduler = start_scheduler()
        except Exception as exc:
            logger.warning("Scheduler failed to start: %s", exc)

    yield

    if bot_task is not None:
        await stop_bot()
    if scheduler is not None:
        stop_scheduler()
    await close_mongo_connection()
    logger.info("Shutdown complete")


app = FastAPI(
    title=settings.APP_NAME,
    description="AI-powered hyperlocal commerce without mandatory inventory.",
    version="1.0.0",
    lifespan=lifespan,
)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# The React web app calls /api/v1 with the session cookie; when it is hosted
# separately (e.g. the Vite dev server on :3000) CORS must allow that origin.
if settings.web_cors_origin_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.web_cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(health_api.router)
app.include_router(auth_api.router)
app.include_router(web_api.router)
app.include_router(shops_api.router)
app.include_router(requests_api.router)
app.include_router(demand_api.router)

WEB_DIST_DIR = settings.web_dist_dir
WEB_INDEX = WEB_DIST_DIR / "index.html"
if WEB_DIST_DIR.exists() and (WEB_DIST_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(WEB_DIST_DIR / "assets")),
              name="web-assets")


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = new_request_id("HTTP")
    bind_request_id(request_id)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/", include_in_schema=False)
async def root():
    if WEB_INDEX.exists():
        return FileResponse(str(WEB_INDEX))
    return RedirectResponse(url="/auth/login")


# SPA fallback: client-side routes (/search, /merchant, ...) must serve the
# React app's index.html. Registered last so /api, /auth and /static win.
_RESERVED_PREFIXES = ("/api", "/auth", "/static", "/assets", "/docs",
                      "/redoc", "/openapi.json")


@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(full_path: str):
    if WEB_INDEX.exists() and not full_path.startswith(_RESERVED_PREFIXES):
        # Real files shipped in the build (manifest, icons, …) win over the SPA.
        try:
            candidate = (WEB_DIST_DIR / full_path).resolve()
            if candidate.is_file() and candidate.is_relative_to(WEB_DIST_DIR.resolve()):
                return FileResponse(str(candidate))
        except (OSError, ValueError):
            pass
        return FileResponse(str(WEB_INDEX))
    return JSONResponse(status_code=404, content={"detail": "Not Found"})


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    # Never leak internals; HTML pages get an HTML error, the API gets JSON.
    if request.url.path.startswith("/auth"):
        from app.api.deps import templates
        return templates.TemplateResponse(
            request=request, name="error.html",
            context={"message": str(exc.detail), "app_name": settings.APP_NAME},
            status_code=exc.status_code,
        )
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"detail": "Some fields were invalid. Please check and try again."},
    )


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    """Our own error types already know their status code and safe message."""
    if exc.actionable:
        logger.warning("app error | path=%s | %s", request.url.path, exc.debug_line())
    else:
        logger.error("app error | path=%s | %s", request.url.path, exc.debug_line(),
                     exc_info=exc.cause or exc)
    if request.url.path.startswith("/auth"):
        from app.api.deps import templates
        return templates.TemplateResponse(
            request=request, name="error.html",
            context={"message": exc.user_text(), "app_name": settings.APP_NAME},
            status_code=exc.http_status,
        )
    return JSONResponse(status_code=exc.http_status, content=exc.to_dict())


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    ref = new_error_ref()
    logger.exception(
        "unhandled server error | path=%s | %s",
        request.url.path,
        describe_unexpected(exc, operation="http.request",
                            context={"ref": ref, "method": request.method}),
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Something went wrong on our side. Please try again.", "ref": ref},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app", host=settings.APP_HOST, port=settings.APP_PORT,
        reload=settings.DEMO_MODE, log_level=settings.LOG_LEVEL.lower(),
    )
