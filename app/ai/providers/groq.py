"""GROQ provider — fast fallback inference.

NOTE: GROQ is the inference provider. It is NOT Grok (the xAI model).
"""
from typing import Any, Dict, Optional

import httpx

from app.ai.base import LLMProvider, ProviderError, ProviderUnavailable
from app.config.settings import settings
from app.utils.logging import get_logger
from app.utils.parsing import extract_json_object

logger = get_logger(__name__)


class OpenAICompatibleProvider(LLMProvider):
    """Shared implementation for any /chat/completions endpoint."""

    name = "openai_compatible"

    def __init__(self, api_key: str, model: str, base_url: str, name: str) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.name = name

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.model)

    async def _chat(self, messages: list, temperature: float, max_tokens: int,
                    json_mode: bool) -> str:
        if not self.is_configured:
            raise ProviderUnavailable(self.name, "API key or model is not configured")
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        try:
            async with httpx.AsyncClient(timeout=settings.AI_TIMEOUT_SECONDS) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
        except httpx.HTTPError as exc:
            raise ProviderError(self.name, f"network error: {exc.__class__.__name__}") from exc
        if resp.status_code >= 400:
            raise ProviderError(self.name, f"HTTP {resp.status_code}")
        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            raise ProviderError(self.name, "empty choices")
        text = (choices[0].get("message") or {}).get("content") or ""
        if not text.strip():
            raise ProviderError(self.name, "empty response text")
        return text.strip()

    def _messages(self, prompt: str, system: Optional[str]) -> list:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return messages

    async def generate_text(self, prompt: str, *, system: Optional[str] = None,
                            temperature: float = 0.2, max_tokens: int = 1024) -> str:
        return await self._chat(self._messages(prompt, system), temperature, max_tokens, False)

    async def generate_structured(self, prompt: str, *, system: Optional[str] = None,
                                  temperature: float = 0.1, max_tokens: int = 1024) -> Dict[str, Any]:
        system = (system or "") + "\n\nRespond with a single valid JSON object only."
        raw = await self._chat(self._messages(prompt, system), temperature, max_tokens, True)
        parsed = extract_json_object(raw)
        if not parsed:
            raise ProviderError(self.name, "response was not valid JSON")
        return parsed


class GroqProvider(OpenAICompatibleProvider):
    def __init__(self) -> None:
        super().__init__(settings.GROQ_API_KEY, settings.GROQ_MODEL,
                         settings.GROQ_BASE_URL, "groq")
