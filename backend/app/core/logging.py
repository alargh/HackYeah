"""Structured (JSON lines) logging.

Usage:
    log = get_logger(__name__)
    log.info("stage finished", extra=fields(lesson_id=..., stage=..., status=...))
"""

from __future__ import annotations

import json
import logging
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

_STRUCTURED_KEY = "structured"


def fields(**kwargs: Any) -> dict[str, Any]:
    return {_STRUCTURED_KEY: {k: v for k, v in kwargs.items() if v is not None}}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        payload.update(getattr(record, _STRUCTURED_KEY, {}) or {})
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if any(isinstance(h.formatter, JsonFormatter) for h in root.handlers):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.handlers = [handler]
    root.setLevel(level.upper())
    # Keep third-party noise down.
    for noisy in ("httpx", "httpcore", "google_genai", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


@contextmanager
def log_stage(logger: logging.Logger, stage: str, **ctx: Any) -> Iterator[dict[str, Any]]:
    """Log start/finish of a pipeline stage with duration. Callers may add keys to the yielded dict."""
    extra: dict[str, Any] = {}
    start = time.perf_counter()
    logger.info("stage started", extra=fields(stage=stage, status="STARTED", **ctx))
    try:
        yield extra
    except Exception as exc:
        logger.error(
            "stage failed",
            extra=fields(
                stage=stage,
                status="FAILED",
                duration_ms=round((time.perf_counter() - start) * 1000),
                error=str(exc)[:500],
                **ctx,
                **extra,
            ),
        )
        raise
    logger.info(
        "stage finished",
        extra=fields(
            stage=stage,
            status="OK",
            duration_ms=round((time.perf_counter() - start) * 1000),
            **ctx,
            **extra,
        ),
    )
