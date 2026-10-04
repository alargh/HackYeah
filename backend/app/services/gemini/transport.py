"""LLM transports. The rest of the app depends only on the `LLMTransport` protocol.

`GoogleGenAITransport` is the only module that imports the Gemini SDK.
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from typing import Any, Protocol, runtime_checkable

from app.core.logging import fields, get_logger

log = get_logger(__name__)


class TransportError(RuntimeError):
    pass


class TransportTimeout(TransportError):
    pass


_local = threading.local()


@contextmanager
def deadline(seconds: float | None):
    """Cap the HTTP time of Gemini calls made by this thread (the request is cancelled, not abandoned)."""
    prev = getattr(_local, "timeout_s", None)
    _local.timeout_s = seconds
    try:
        yield
    finally:
        _local.timeout_s = prev


def current_deadline() -> float | None:
    return getattr(_local, "timeout_s", None)


@runtime_checkable
class LLMTransport(Protocol):
    model_name: str

    def generate(self, *, system: str, user: str, json_schema: dict[str, Any] | None) -> str:
        """Return the raw model text (JSON when json_schema is given)."""
        ...


class GoogleGenAITransport:
    """Gemini via the official `google-genai` SDK, with JSON-schema constrained output."""

    def __init__(self, api_key: str, model: str, temperature: float = 0.2, timeout_s: float = 180.0, max_retries: int = 3):
        from google import genai
        from google.genai import types

        self._types = types
        self.model_name = model
        self.temperature = temperature
        self.max_retries = max_retries
        self._client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=int(timeout_s * 1000)))
        self._schema_supported = True

    def _config(self, system: str, json_schema: dict[str, Any] | None) -> Any:
        types = self._types
        kwargs: dict[str, Any] = {"system_instruction": system, "temperature": self.temperature}
        if current_deadline():
            kwargs["http_options"] = types.HttpOptions(timeout=int(current_deadline() * 1000))
        if json_schema is not None:
            kwargs["response_mime_type"] = "application/json"
            if self._schema_supported:
                kwargs["response_json_schema"] = json_schema
        return types.GenerateContentConfig(**kwargs)

    def generate(self, *, system: str, user: str, json_schema: dict[str, Any] | None) -> str:
        from google.genai import errors

        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self._client.models.generate_content(
                    model=self.model_name, contents=user, config=self._config(system, json_schema)
                )
                text = resp.text
                if not text:
                    reason = None
                    if resp.candidates:
                        reason = getattr(resp.candidates[0], "finish_reason", None)
                    raise TransportError(f"empty response from Gemini (finish_reason={reason})")
                return text
            except errors.ClientError as exc:
                # A 400 can mean the schema uses a feature the API rejects: fall back to
                # JSON mode + schema-in-prompt (the schema is always included in the prompt too).
                if exc.code == 400 and json_schema is not None and self._schema_supported:
                    log.warning("schema rejected, falling back to JSON mode", extra=fields(error=str(exc)[:300]))
                    self._schema_supported = False
                    continue
                if exc.code == 429 and attempt < self.max_retries:
                    last_exc = exc
                    time.sleep(2**attempt)
                    continue
                raise TransportError(f"Gemini client error {exc.code}: {exc}") from exc
            except errors.ServerError as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    time.sleep(2**attempt)
                    continue
            except TransportError as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    continue
            except Exception as exc:  # noqa: BLE001 - httpx timeouts: give up now, the caller retries smarter
                if current_deadline() and "timeout" in type(exc).__name__.lower():
                    raise TransportTimeout(f"Gemini call exceeded {current_deadline():.0f} s") from exc
                raise
        raise TransportError(f"Gemini request failed after {self.max_retries} attempts: {last_exc}")
