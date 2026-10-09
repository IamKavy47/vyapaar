"""Central configuration. Everything is driven by environment variables (.env)."""
from functools import lru_cache
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    # ---------------- App ----------------
    APP_NAME: str = "Vyapaar-Mitra"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    PUBLIC_BASE_URL: str = "http://localhost:8000"
    LOG_LEVEL: str = "INFO"
    DEMO_MODE: bool = True
    RUN_BOT: bool = False
    ENABLE_SCHEDULER: bool = False

    # ---------------- Telegram ----------------
    TELEGRAM_BOT_TOKEN: str = ""
    # Bot username (without @) — used to build t.me deep links for web users
    # connecting their Telegram account.
    TELEGRAM_BOT_USERNAME: str = ""
    ADMIN_TELEGRAM_IDS: str = ""

    # ---------------- Web frontend (React app in web/) ----------------
    # Comma-separated origins allowed to call /api/v1 with cookies when the
    # web app is hosted separately from this backend (e.g. Vite dev server).
    WEB_CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"
    # Built frontend directory. Empty -> auto-detect <repo>/web/dist.
    # When it exists, FastAPI serves the React app at / with SPA fallback.
    WEB_DIST_DIR: str = ""

    # ---------------- MongoDB ----------------
    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DATABASE: str = "vyapaar_mitra"

    # ---------------- AI providers ----------------
    PRIMARY_LLM_PROVIDER: str = "gemini"
    FALLBACK_LLM_PROVIDER: str = "groq"
    TERTIARY_LLM_PROVIDER: str = "gpt_oss"

    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"
    GEMINI_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta"

    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"

    # GPT-OSS (open-weight) served through any OpenAI-compatible endpoint
    GPT_OSS_API_KEY: str = ""
    GPT_OSS_MODEL: str = "openai/gpt-oss-20b"
    GPT_OSS_BASE_URL: str = "https://api.groq.com/openai/v1"

    SARVAM_API_KEY: str = ""
    SARVAM_BASE_URL: str = "https://api.sarvam.ai"
    SARVAM_STT_MODEL: str = "saaras:v4"
    SARVAM_LANGUAGE: str = "hi-IN"

    AI_TIMEOUT_SECONDS: float = 45.0

    # ---------------- Matching ----------------
    MATCH_RADIUS_METERS: int = 500
    MAX_MATCH_RADIUS_METERS: int = 5000
    RADIUS_EXPANSION_STEPS: str = "500,1000,2000,5000"
    MAX_MERCHANTS_PER_REQUEST: int = 8
    MERCHANT_COOLDOWN_HOURS: int = 12
    REQUEST_EXPIRY_MINUTES: int = 30

    # ---------------- Multi-offer comparison ----------------
    # How long to wait, after the FIRST merchant YES, before notifying the
    # customer that offers are available. Lets several merchants reply first so
    # the customer sees a real comparison instead of just the fastest gun.
    # Set to 0 to preserve the legacy one-notification-per-YES behaviour.
    OFFER_WINDOW_SECONDS: int = 20

    # ---------------- Trust & freshness ----------------
    # Below this many total responses (accepted+declined), a shop is labelled
    # "New merchant" rather than scored — unfair to penalise new shops for
    # data they could not have accumulated yet.
    TRUST_MIN_SAMPLE: int = 5
    # Response time buckets (seconds) for the trust label. Below FAST = "usually
    # responds quickly"; below OK = "responds in reasonable time"; otherwise
    # "may take a while".
    TRUST_RESPONSE_TIME_FAST_SEC: int = 60
    TRUST_RESPONSE_TIME_OK_SEC: int = 300

    # ---------------- Stock opportunity scoring ----------------
    # A product must have at least this many unique nearby customer requests
    # before we surface it as a stock opportunity to a merchant — otherwise the
    # signal is too thin to act on.
    OPPORTUNITY_MIN_REQUESTS: int = 3
    # How wide to look around the merchant's shop when computing opportunity.
    OPPORTUNITY_RADIUS_METERS: int = 3000

    # ---------------- Demand heatmap privacy ----------------
    # Bucket (~300m) — every demand point is snapped to the centre of its
    # bucket so individual customer locations are never exposed to merchants.
    HEATMAP_BUCKET_METERS: int = 300

    # ---------------- Phone verification (anti-scam / anti-impersonation) ----------------
    # OTP is mandatory for both customers and shopkeepers before any action.
    # In stub mode the OTP is logged to stdout AND returned in the API response
    # so a hackathon demo can paste it from the server console — no SMS gateway
    # signup needed. Flip to false in production and wire MSG91 / Twilio below.
    OTP_STUB_MODE: bool = True
    OTP_TTL_MINUTES: int = 5
    OTP_LENGTH: int = 6
    # 6-digit numeric OTP, hashed at rest (sha256) like auth tokens.
    # Real SMS gateway stub — plug in MSG91 / Twilio here in production.
    SMS_GATEWAY: str = "stub"  # "stub" | "msg91" | "twilio"
    MSG91_AUTH_KEY: str = ""
    MSG91_SENDER_ID: str = "VYAPAR"
    MSG91_ROUTE: str = "4"  # transactional
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_NUMBER: str = ""

    # ---------------- Shopfront photo verification ----------------
    # Shopkeeper takes a photo of their shop exterior from inside the PWA;
    # the browser captures GPS at the same moment, AND the JPEG's EXIF GPS
    # is parsed server-side as a cross-check. Both must be within this many
    # metres of the registered shop location, or the upload is rejected.
    SHOPFRONT_PHOTO_DISTANCE_METERS: int = 200
    SHOPFRONT_PHOTO_MAX_BYTES: int = 5 * 1024 * 1024  # 5 MB
    SHOPFRONT_PHOTO_DIR: str = ""  # empty -> app/static/shop_photos/
    # ImgBB is the recommended image host — free, has a simple API, returns
    # a public URL. Sign up at https://imgbb.com/api and paste your API key
    # here. Leave blank to fall back to local disk (photos served from
    # /static/shop_photos/{shop_id}.jpg — works for local dev only).
    IMGBB_API_KEY: str = ""

    # ---------------- Product images (Browse page) ----------------
    # When a shopkeeper adds a product to their inventory, they can optionally
    # upload a photo. If they don't, the backend fetches one from Pexels
    # (free, 200 req/hour, real stock photos). The "AI" flavour is that the
    # product name is passed through Gemini for query expansion (e.g.
    # "Teflon Tape" -> "white PTFE plumbing thread seal tape") so the Pexels
    # search returns more relevant results. PEXELS_API_KEY is required;
    # GEMINI_API_KEY is optional for the query-expansion step.
    PEXELS_API_KEY: str = ""
    # Comma-separated list of categories to append to the Pexels query for
    # better results — e.g. "Teflon Tape hardware" instead of just "Teflon Tape".
    PRODUCT_IMAGE_SEARCH_SUFFIX: str = "product india"

    # ---------------- Customer safety ----------------
    # Trusted-contact phone is captured during customer onboarding; the panic
    # button SMSes this contact with the customer's location + chosen shop
    # details. For the hackathon SMS is stubbed (logged), so no SMS gateway
    # cost is incurred.
    PANIC_SMS_STUB: bool = True

    # ---------------- Razorpay (payments) ----------------
    # Razorpay is the payment gateway for in-app payments. The customer pays
    # when picking up a product/service — the shopkeeper confirms availability,
    # the customer pays via UPI/card/netbanking, and the payment is linked
    # to the request + match for audit trail.
    # Get keys at https://dashboard.razorpay.com/app/keys
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""
    RAZORPAY_CURRENCY: str = "INR"

    # A customer's own range preference. Defaults to the 5km auto-expansion
    # ceiling above, but each customer can widen or narrow it — rural users
    # often need more than 5km, dense markets often want less noise.
    SEARCH_RADIUS_DEFAULT_METERS: int = 5000
    SEARCH_RADIUS_MIN_METERS: int = 1000
    SEARCH_RADIUS_MAX_METERS: int = 20000
    SEARCH_RADIUS_PRESETS_METERS: str = "1000,2000,5000,10000,20000"

    WEIGHT_CATEGORY: float = 0.30
    WEIGHT_CAPABILITY: float = 0.35
    WEIGHT_DISTANCE: float = 0.20
    WEIGHT_HISTORY: float = 0.15

    CONFIDENCE_DIRECT: float = 0.80
    CONFIDENCE_UNCERTAIN: float = 0.60

    # ---------------- Security ----------------
    SESSION_SECRET: str = "change-me-in-production"
    AUTH_TOKEN_TTL_MINUTES: int = 10
    SESSION_TTL_HOURS: int = 72
    AUTH_RATE_LIMIT: int = 10
    AUTH_RATE_WINDOW_SECONDS: int = 60
    AI_RATE_LIMIT: int = 20
    AI_RATE_WINDOW_SECONDS: int = 60
    COOKIE_SECURE: bool = False

    # ---------------- Email (optional) ----------------
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    SMTP_USE_TLS: bool = True
    ENABLE_SCHEDULED_REPORTS: bool = False
    DEMAND_REPORT_HOUR: int = 20

    @field_validator("PRIMARY_LLM_PROVIDER", "FALLBACK_LLM_PROVIDER", "TERTIARY_LLM_PROVIDER")
    @classmethod
    def _lower(cls, v: str) -> str:
        return (v or "").strip().lower()

    # ---------------- Derived helpers ----------------
    @property
    def admin_ids(self) -> List[int]:
        out = []
        for chunk in self.ADMIN_TELEGRAM_IDS.split(","):
            chunk = chunk.strip()
            if chunk.isdigit():
                out.append(int(chunk))
        return out

    @property
    def radius_steps(self) -> List[int]:
        steps = []
        for chunk in self.RADIUS_EXPANSION_STEPS.split(","):
            chunk = chunk.strip()
            if chunk.isdigit() and int(chunk) <= self.MAX_MATCH_RADIUS_METERS:
                steps.append(int(chunk))
        if not steps:
            steps = [self.MATCH_RADIUS_METERS, self.MAX_MATCH_RADIUS_METERS]
        return sorted(set(steps))

    @property
    def web_cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.WEB_CORS_ORIGINS.split(",") if o.strip()]

    @property
    def web_dist_dir(self):
        from pathlib import Path
        if self.WEB_DIST_DIR:
            return Path(self.WEB_DIST_DIR)
        return Path(__file__).resolve().parent.parent.parent / "web" / "dist"

    @property
    def search_radius_presets(self) -> List[int]:
        presets = []
        for chunk in self.SEARCH_RADIUS_PRESETS_METERS.split(","):
            chunk = chunk.strip()
            if chunk.isdigit():
                value = int(chunk)
                if self.SEARCH_RADIUS_MIN_METERS <= value <= self.SEARCH_RADIUS_MAX_METERS:
                    presets.append(value)
        if not presets:
            presets = [self.SEARCH_RADIUS_DEFAULT_METERS]
        return sorted(set(presets))

    @property
    def llm_chain(self) -> List[str]:
        chain = [self.PRIMARY_LLM_PROVIDER, self.FALLBACK_LLM_PROVIDER, self.TERTIARY_LLM_PROVIDER]
        seen, out = set(), []
        for name in chain:
            if name and name not in seen:
                seen.add(name)
                out.append(name)
        return out

    @property
    def email_enabled(self) -> bool:
        return bool(self.SMTP_HOST and self.SMTP_FROM_EMAIL)

    @property
    def shopfront_photo_dir(self):
        from pathlib import Path
        if self.SHOPFRONT_PHOTO_DIR:
            return Path(self.SHOPFRONT_PHOTO_DIR)
        return Path(__file__).resolve().parent.parent / "static" / "shop_photos"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
