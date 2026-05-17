"""
Unified LLM Client — T5.1 (Người C)

Abstract LLMClient with configurable providers:
- OpenAIClient: Production (configurable model via env)
"""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=True)

# Retry configuration
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0  # seconds
RETRY_BACKOFF = 2.0  # exponential backoff multiplier
RETRYABLE_ERRORS = (
    "rate_limit",
    "timeout",
    "connection",
    "503",
    "502",
    "500",
)


class LLMClient(ABC):
    """Abstract LLM client interface."""

    @abstractmethod
    async def chat(
        self,
        prompt: str,
        schema: Optional[dict[str, Any]] = None,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        pass

    @abstractmethod
    async def chat_stream(
        self,
        prompt: str,
        schema: Optional[dict[str, Any]] = None,
        temperature: float = 0.0,
    ) -> AsyncIterator[str]:
        pass

    @abstractmethod
    async def extract(
        self,
        text: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        pass

    @abstractmethod
    async def classify(
        self,
        text: str,
        categories: list[str],
    ) -> dict[str, Any]:
        pass


class OpenAIClient(LLMClient):
    """
    OpenAI provider.

    Configuration via environment variables:
        OPENAI_API_KEY: API key (required)
        OPENAI_MODEL: Model name (default: gpt-5.4-mini)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self._api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self._model = model or os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
        if not self._api_key:
            raise ValueError("OPENAI_API_KEY is required. Set it in .env or environment.")
        self._client = None

    def _get_client(self):
        """Lazy initialize client."""
        if self._client is None:
            from openai import AsyncOpenAI
            base_url = os.getenv("OPENAI_BASE_URL", "") or "https://api.openai.com/v1"
            self._client = AsyncOpenAI(api_key=self._api_key, base_url=base_url)
        return self._client

    async def chat(
        self,
        prompt: str,
        schema: Optional[dict[str, Any]] = None,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        client = self._get_client()
        messages = [{"role": "user", "content": prompt}]

        kwargs = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
        }

        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                logger.info(
                    "LLM request start model=%s prompt_chars=%d schema=%s temperature=%.2f attempt=%d",
                    self._model,
                    len(prompt),
                    bool(schema),
                    temperature,
                    attempt + 1,
                )
                response = await client.chat.completions.create(**kwargs)
                content = response.choices[0].message.content.strip()

                # Strip markdown code blocks if present
                if content.startswith("```"):
                    lines = content.split("\n")
                    lines = [l for l in lines if not l.startswith("```")]
                    content = "\n".join(lines)

                parsed = json.loads(content)
                logger.info(
                    "LLM request success model=%s response_chars=%d keys=%s",
                    self._model,
                    len(content),
                    sorted(parsed.keys()) if isinstance(parsed, dict) else type(parsed).__name__,
                )
                return parsed

            except Exception as e:
                last_error = e
                error_str = str(e).lower()
                is_retryable = any(err in error_str for err in RETRYABLE_ERRORS)

                if not is_retryable or attempt == MAX_RETRIES - 1:
                    logger.error(f"LLM call failed after {attempt + 1} attempts: {e}")
                    raise

                delay = RETRY_BASE_DELAY * (RETRY_BACKOFF ** attempt)
                logger.warning(f"LLM call failed (attempt {attempt + 1}/{MAX_RETRIES}), retrying in {delay}s: {e}")
                await asyncio.sleep(delay)

        raise last_error  # Should never reach here

    async def chat_stream(
        self,
        prompt: str,
        schema: Optional[dict[str, Any]] = None,
        temperature: float = 0.0,
    ) -> AsyncIterator[str]:
        client = self._get_client()
        messages = [{"role": "user", "content": prompt}]

        kwargs = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }

        last_error = None
        for attempt in range(MAX_RETRIES):
            emitted_any = False
            try:
                logger.info(
                    "LLM stream start model=%s prompt_chars=%d schema=%s temperature=%.2f attempt=%d",
                    self._model,
                    len(prompt),
                    bool(schema),
                    temperature,
                    attempt + 1,
                )
                stream = client.chat.completions.create(**kwargs)
                if inspect.isawaitable(stream):
                    stream = await stream
                async for event in stream:
                    delta = ""
                    choice = event.choices[0] if event.choices else None
                    if choice and choice.delta and choice.delta.content:
                        delta = choice.delta.content
                    if delta:
                        emitted_any = True
                        yield delta
                return
            except Exception as e:
                last_error = e
                error_str = str(e).lower()
                is_retryable = any(err in error_str for err in RETRYABLE_ERRORS)
                if emitted_any or not is_retryable or attempt == MAX_RETRIES - 1:
                    logger.error("LLM stream failed after %d attempts: %s", attempt + 1, e)
                    raise

                delay = RETRY_BASE_DELAY * (RETRY_BACKOFF ** attempt)
                logger.warning("LLM stream failed (attempt %d/%d), retrying in %ss: %s", attempt + 1, MAX_RETRIES, delay, e)
                await asyncio.sleep(delay)

        raise last_error  # Should never reach here

    async def extract(
        self,
        text: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        prompt = f"Extract structured data from the following text according to the schema:\n\nSchema: {json.dumps(schema)}\n\nText: {text}\n\nReturn only valid JSON."
        named_schema = {"name": "extraction", "schema": schema, "strict": False}
        return await self.chat(prompt, schema=named_schema)

    async def classify(
        self,
        text: str,
        categories: list[str],
    ) -> dict[str, Any]:
        prompt = f"Classify the following text into one of these categories: {', '.join(categories)}\n\nText: {text}\n\nReturn JSON with keys: category (string), confidence (float 0-1)."
        result = await self.chat(prompt)
        return {"category": result.get("category", ""), "confidence": result.get("confidence", 0.0)}


def create_client(
    provider: Optional[str] = None,
    **kwargs: Any,
) -> LLMClient:
    """
    Factory function to create LLM client.

    Args:
        provider: "openai" | None (auto-detect from env)
        **kwargs: Provider-specific arguments

    Returns:
        LLMClient instance
    """
    provider = provider or os.getenv("LLM_PROVIDER", "openai")

    if provider == "openai":
        return OpenAIClient(
            api_key=kwargs.get("api_key"),
            model=kwargs.get("model"),
        )
    else:
        raise ValueError(f"Unknown LLM provider: {provider}. Supported: openai")
