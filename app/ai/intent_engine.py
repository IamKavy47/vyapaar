"""Intent engine: raw customer input -> ProductIntent, with provider fallback.

Fallback order comes from .env (gemini -> groq -> gpt_oss). If every provider
fails we return a low-confidence intent and say so honestly — we never fabricate
an AI answer.
"""
from typing import List, Optional, Tuple

from app.ai.base import LLMProvider, ProviderError
from app.ai.prompts import (
    INTENT_SYSTEM, INTENT_USER_TEMPLATE, QUERY_NORMALIZE_SYSTEM,
)
from app.ai.providers import get_stt_provider, llm_chain
from app.config.settings import settings
from app.schemas.intent import ProductIntent
from app.utils.logging import get_logger

logger = get_logger(__name__)


class AIUnavailableError(RuntimeError):
    """Every configured provider failed. Caller must tell the user the truth."""


async def _run_structured(prompt: str, system: str, *, providers: Optional[List[LLMProvider]] = None,
                          max_tokens: int = 1024) -> Tuple[dict, str]:
    chain = providers if providers is not None else llm_chain()
    errors = []
    for provider in chain:
        if not provider.is_configured:
            logger.debug("Skipping %s (not configured)", provider.name)
            continue
        try:
            logger.info("LLM started | provider=%s", provider.name)
            data = await provider.generate_structured(prompt, system=system, max_tokens=max_tokens)
            logger.info("LLM completed | provider=%s", provider.name)
            return data, provider.name
        except ProviderError as exc:
            errors.append(str(exc))
            logger.warning("Provider %s failed, falling back: %s", provider.name, exc.message)
        except Exception as exc:  # defensive: a provider must never crash the request
            errors.append(f"[{provider.name}] {exc.__class__.__name__}")
            logger.warning("Provider %s raised %s", provider.name, exc.__class__.__name__)
    raise AIUnavailableError("; ".join(errors) or "no AI provider is configured")


async def extract_intent(text: str, *, input_type: str = "text") -> ProductIntent:
    """Text/transcript -> ProductIntent. Raises AIUnavailableError if all providers fail."""
    prompt = INTENT_USER_TEMPLATE.format(text=text.strip(), input_type=input_type)
    data, provider_name = await _run_structured(prompt, INTENT_SYSTEM)
    intent = ProductIntent(**{k: v for k, v in data.items() if k in ProductIntent.model_fields})
    intent.provider = provider_name
    intent.uncertain = (
        settings.CONFIDENCE_UNCERTAIN <= intent.confidence < settings.CONFIDENCE_DIRECT
    )
    logger.info(
        "intent extracted | product=%s category=%s confidence=%.2f provider=%s",
        intent.product, intent.category, intent.confidence, provider_name,
    )
    return intent


async def transcribe_voice(audio_bytes: bytes, *, mime_type: str = "audio/ogg",
                           language_code: Optional[str] = None) -> str:
    """Sarvam STT. There is no silent fallback — the caller offers text input instead."""
    stt = get_stt_provider()
    logger.info("STT started | provider=%s bytes=%d", stt.name, len(audio_bytes or b""))
    transcript = await stt.transcribe(audio_bytes, mime_type=mime_type, language_code=language_code)
    logger.info("STT completed | chars=%d", len(transcript))
    return transcript


async def normalize_query(text: str) -> str:
    """Cheap text task — deliberately routed to the fast provider first."""
    chain = llm_chain()
    fast = [p for p in chain if p.name in {"groq", "gpt_oss"}] + chain
    for provider in fast:
        if not provider.is_configured:
            continue
        try:
            out = await provider.generate_text(
                text, system=QUERY_NORMALIZE_SYSTEM, temperature=0.0, max_tokens=64
            )
            return out.strip().strip('"')
        except Exception:
            continue
    return text


def confidence_band(confidence: float) -> str:
    """direct (>=0.80) | uncertain (0.60-0.79) | clarify (<0.60)"""
    if confidence >= settings.CONFIDENCE_DIRECT:
        return "direct"
    if confidence >= settings.CONFIDENCE_UNCERTAIN:
        return "uncertain"
    return "clarify"


def clarification_options(intent: ProductIntent) -> List[str]:
    """Build the 'did you mean' list without inventing products out of thin air."""
    options: List[str] = []
    if intent.product:
        options.append(intent.product)
    for alt in intent.alternative_products:
        if alt.lower() not in {o.lower() for o in options}:
            options.append(alt)
    return options[:3]
