"""Provider-agnostic AI interfaces.

Business logic never imports Gemini/Groq/GPT-OSS directly — it depends on these
abstractions only. Swapping a provider is a .env change, not a code change.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class ProviderError(RuntimeError):
    """Raised when a provider is unavailable or returns something unusable."""

    def __init__(self, provider: str, message: str) -> None:
        super().__init__(f"[{provider}] {message}")
        self.provider = provider
        self.message = message


class ProviderUnavailable(ProviderError):
    """Missing API key / not configured. Skip straight to the next provider."""


class LLMProvider(ABC):
    name: str = "base"

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        ...

    @abstractmethod
    async def generate_text(
        self, prompt: str, *, system: Optional[str] = None, temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> str:
        ...

    @abstractmethod
    async def generate_structured(
        self, prompt: str, *, system: Optional[str] = None, temperature: float = 0.1,
        max_tokens: int = 1024,
    ) -> Dict[str, Any]:
        """Must return a parsed JSON object (never a raw string)."""

    async def analyze_image(
        self, image_bytes: bytes, prompt: str, *, mime_type: str = "image/jpeg",
        system: Optional[str] = None,
    ) -> Dict[str, Any]:
        raise ProviderUnavailable(self.name, "This provider does not support vision.")

    @property
    def supports_vision(self) -> bool:
        return False


class STTProvider(ABC):
    name: str = "base-stt"

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        ...

    @abstractmethod
    async def transcribe(
        self, audio_bytes: bytes, *, mime_type: str = "audio/ogg",
        language_code: Optional[str] = None,
    ) -> str:
        ...


class ProviderResult:
    """Carries the answer plus which provider actually produced it."""

    def __init__(self, data: Any, provider: str, fallback_used: bool = False) -> None:
        self.data = data
        self.provider = provider
        self.fallback_used = fallback_used

    def __repr__(self) -> str:  # pragma: no cover
        return f"ProviderResult(provider={self.provider!r}, fallback={self.fallback_used})"


def available_names(providers: List[LLMProvider]) -> List[str]:
    return [p.name for p in providers if p.is_configured]
