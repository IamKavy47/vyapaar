"""GPT-OSS open-weight provider (gpt-oss-20b / gpt-oss-120b).

Served through any OpenAI-compatible endpoint — Groq, vLLM, Ollama, LM Studio —
so the base URL and model name are both configurable.
"""
from app.ai.providers.groq import OpenAICompatibleProvider
from app.config.settings import settings


class GptOssProvider(OpenAICompatibleProvider):
    def __init__(self) -> None:
        super().__init__(
            settings.GPT_OSS_API_KEY or settings.GROQ_API_KEY,
            settings.GPT_OSS_MODEL,
            settings.GPT_OSS_BASE_URL,
            "gpt_oss",
        )
