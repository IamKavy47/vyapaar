"""Google Gemini provider — primary LLM + vision."""
import base64
from typing import Any, Dict, Optional

import httpx

from app.ai.base import LLMProvider, ProviderError, ProviderUnavailable
from app.config.settings import settings
from app.utils.logging import get_logger
from app.utils.parsing import extract_json_object

logger = get_logger(__name__)


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self) -> None:
        self.api_key = settings.GEMINI_API_KEY
        self.model = settings.GEMINI_MODEL
        self.base_url = settings.GEMINI_BASE_URL.rstrip("/")

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    @property
    def supports_vision(self) -> bool:
        return True

    def _url(self) -> str:
        return f"{self.base_url}/models/{self.model}:generateContent"

    async def _call(self, parts: list, system: Optional[str], temperature: float,
                    max_tokens: int, json_mode: bool) -> str:
        if not self.is_configured:
            raise ProviderUnavailable(self.name, "GEMINI_API_KEY is not set")
        payload: Dict[str, Any] = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        if json_mode:
            payload["generationConfig"]["responseMimeType"] = "application/json"
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        try:
            async with httpx.AsyncClient(timeout=settings.AI_TIMEOUT_SECONDS) as client:
                resp = await client.post(
                    self._url(), json=payload, headers={"x-goog-api-key": self.api_key}
                )
        except httpx.HTTPError as exc:
            raise ProviderError(self.name, f"network error: {exc.__class__.__name__}") from exc
        if resp.status_code >= 400:
            raise ProviderError(self.name, f"HTTP {resp.status_code}")
        data = resp.json()
        candidates = data.get("candidates") or []
        if not candidates:
            raise ProviderError(self.name, "empty candidate list (possibly blocked)")
        parts_out = candidates[0].get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts_out).strip()
        if not text:
            raise ProviderError(self.name, "empty response text")
        return text

    async def generate_text(self, prompt: str, *, system: Optional[str] = None,
                            temperature: float = 0.2, max_tokens: int = 1024) -> str:
        return await self._call([{"text": prompt}], system, temperature, max_tokens, False)

    async def generate_structured(self, prompt: str, *, system: Optional[str] = None,
                                  temperature: float = 0.1, max_tokens: int = 1024) -> Dict[str, Any]:
        raw = await self._call([{"text": prompt}], system, temperature, max_tokens, True)
        parsed = extract_json_object(raw)
        if not parsed:
            raise ProviderError(self.name, "response was not valid JSON")
        return parsed

    async def analyze_image(self, image_bytes: bytes, prompt: str, *,
                            mime_type: str = "image/jpeg",
                            system: Optional[str] = None) -> Dict[str, Any]:
        parts = [
            {"inline_data": {"mime_type": mime_type,
                             "data": base64.b64encode(image_bytes).decode()}},
            {"text": prompt},
        ]
        raw = await self._call(parts, system, 0.1, 1536, True)
        parsed = extract_json_object(raw)
        if not parsed:
            raise ProviderError(self.name, "vision response was not valid JSON")
        return parsed
