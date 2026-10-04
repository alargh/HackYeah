from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import Settings
from app.core.container import Container, build_pipeline
from app.core.db import init_db
from app.services.prompts import PromptStore
from app.workers.jobs import InlineJobRunner
from tests.fixtures import FakeRenderer, FakeTransport, FakeTTS, default_responses

REPO = Path(__file__).resolve().parents[2]


def _prompts_dir() -> Path:
    for d in (Path(__file__).resolve().parents[1] / "prompts", REPO / "prompts"):
        if d.is_dir():
            return d
    raise RuntimeError("prompts directory not found")


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    s = Settings(
        DATA_DIR=tmp_path / "data",
        PROMPTS_DIR=_prompts_dir(),
        GEMINI_API_KEY=None,
        GOOGLE_API_KEY=None,
        AUTO_RENDER=True,
        MAX_STAGE_RETRIES=2,
        MAX_RENDER_RETRIES=1,
    )
    s.media_dir.mkdir(parents=True, exist_ok=True)
    init_db(s.sqlalchemy_url)
    return s


@pytest.fixture
def prompts() -> PromptStore:
    return PromptStore(_prompts_dir())


def make_pipeline(settings: Settings, responses=None, renderer=None, tts="default"):
    transport = FakeTransport(responses or default_responses())
    pipeline = build_pipeline(settings, transport, FakeTTS() if tts == "default" else tts)
    pipeline.renderer = renderer or FakeRenderer()
    return pipeline, transport


@pytest.fixture
def make_container(settings: Settings):
    def _make(responses=None, renderer=None, tts="default") -> tuple[Container, FakeTransport]:
        pipeline, transport = make_pipeline(settings, responses, renderer, tts)
        return Container(settings, pipeline, InlineJobRunner(), PromptStore(settings.prompts_dir)), transport

    return _make
