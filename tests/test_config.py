"""Configuration invariants that the matching engine relies on."""
from app.config.settings import Settings, settings


def test_default_cooldown_is_twelve_hours():
    assert settings.MERCHANT_COOLDOWN_HOURS == 12


def test_radius_expansion_is_ordered_and_capped():
    steps = settings.radius_steps
    assert steps == sorted(steps)
    assert steps[0] >= settings.MATCH_RADIUS_METERS
    assert max(steps) <= settings.MAX_MATCH_RADIUS_METERS


def test_llm_chain_is_ordered_and_deduplicated():
    chain = Settings(
        PRIMARY_LLM_PROVIDER="gemini", FALLBACK_LLM_PROVIDER="groq",
        TERTIARY_LLM_PROVIDER="groq",
    ).llm_chain
    assert chain == ["gemini", "groq"]


def test_provider_names_are_lowercased():
    assert Settings(PRIMARY_LLM_PROVIDER="GEMINI").PRIMARY_LLM_PROVIDER == "gemini"


def test_admin_ids_parse_from_csv():
    assert Settings(ADMIN_TELEGRAM_IDS="123, 456,abc").admin_ids == [123, 456]


def test_email_disabled_without_smtp_host():
    assert Settings(SMTP_HOST="", SMTP_FROM_EMAIL="").email_enabled is False
    assert Settings(SMTP_HOST="smtp.example.com", SMTP_FROM_EMAIL="a@b.c").email_enabled is True


def test_confidence_thresholds_are_ordered():
    assert 0 < settings.CONFIDENCE_UNCERTAIN < settings.CONFIDENCE_DIRECT <= 1.0
