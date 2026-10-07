"""Provider registry + the ordered fallback chain."""
from typing import Dict, List, Optional

from app.ai.base import LLMProvider, STTProvider
from app.ai.providers.gemini import GeminiProvider
from app.ai.providers.gpt_oss import GptOssProvider
from app.ai.providers.groq import GroqProvider
from app.ai.providers.sarvam import SarvamSTTProvider
from app.config.settings import settings

_LLM_FACTORIES = {
    "gemini": GeminiProvider,
    "groq": GroqProvider,
    "gpt_oss": GptOssProvider,
    "gptoss": GptOssProvider,
}

_llm_cache: Dict[str, LLMProvider] = {}
_stt_cache: Dict[str, STTProvider] = {}


def get_llm_provider(name: str) -> Optional[LLMProvider]:
    key = (name or "").strip().lower()
    if key not in _LLM_FACTORIES:
        return None
    if key not in _llm_cache:
        _llm_cache[key] = _LLM_FACTORIES[key]()
    return _llm_cache[key]


def llm_chain() -> List[LLMProvider]:
    """Ordered provider chain from .env: gemini -> groq -> gpt_oss."""
    chain: List[LLMProvider] = []
    for name in settings.llm_chain:
        provider = get_llm_provider(name)
        if provider is not None:
            chain.append(provider)
    return chain


def vision_chain() -> List[LLMProvider]:
    return [p for p in llm_chain() if p.supports_vision]


def get_stt_provider() -> STTProvider:
    if "sarvam" not in _stt_cache:
        _stt_cache["sarvam"] = SarvamSTTProvider()
    return _stt_cache["sarvam"]


def provider_status() -> Dict[str, bool]:
    status = {p.name: p.is_configured for p in llm_chain()}
    status["sarvam_stt"] = get_stt_provider().is_configured
    return status
