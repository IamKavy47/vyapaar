"""Sarvam AI — Indian-language speech to text (Hindi, Hinglish, noisy voice notes)."""
from typing import Optional

import httpx

from app.ai.base import ProviderError, ProviderUnavailable, STTProvider
from app.config.settings import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class SarvamSTTProvider(STTProvider):
    name = "sarvam"

    def __init__(self) -> None:
        self.api_key = settings.SARVAM_API_KEY
        self.base_url = settings.SARVAM_BASE_URL.rstrip("/")
        self.model = settings.SARVAM_STT_MODEL

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def transcribe(self, audio_bytes: bytes, *, mime_type: str = "audio/ogg",
                         language_code: Optional[str] = None) -> str:
        if not self.is_configured:
            raise ProviderUnavailable(self.name, "SARVAM_API_KEY is not set")
        if not audio_bytes:
            raise ProviderError(self.name, "empty audio payload")

        suffix = {"audio/ogg": "ogg", "audio/mpeg": "mp3", "audio/wav": "wav",
                  "audio/x-wav": "wav", "audio/mp4": "m4a"}.get(mime_type, "ogg")
        files = {"file": (f"voice.{suffix}", audio_bytes, mime_type)}
        data = {
            "model": self.model,
            "mode": "transcribe",
            "language_code": language_code or settings.SARVAM_LANGUAGE,
        }
        try:
            async with httpx.AsyncClient(timeout=settings.AI_TIMEOUT_SECONDS) as client:
                resp = await client.post(
                    f"{self.base_url}/speech-to-text",
                    files=files, data=data,
                    headers={"api-subscription-key": self.api_key},
                )
        except httpx.HTTPError as exc:
            raise ProviderError(self.name, f"network error: {exc.__class__.__name__}") from exc
        if resp.status_code >= 400:
            detail = resp.text[:500].replace("\n", " ")
            raise ProviderError(self.name, f"HTTP {resp.status_code}: {detail}")
        payload = resp.json()
        transcript = (payload.get("transcript") or payload.get("text") or "").strip()
        if not transcript:
            raise ProviderError(self.name, "empty transcript")
        return transcript
