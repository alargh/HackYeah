"""Application settings, loaded from environment variables (and an optional .env file)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_REPO_DIR = _BACKEND_DIR.parent


def _default_prompts_dir() -> Path:
    # In Docker the prompts are copied next to the app; locally they live at the repo root.
    for candidate in (_BACKEND_DIR / "prompts", _REPO_DIR / "prompts"):
        if candidate.is_dir():
            return candidate
    return _REPO_DIR / "prompts"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(_REPO_DIR / ".env"), str(_BACKEND_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Gemini (runtime mathematical AI) ---
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    google_api_key: str | None = Field(default=None, alias="GOOGLE_API_KEY")
    gemini_model: str = Field(default="gemini-3.5-flash", alias="GEMINI_MODEL")
    gemini_temperature: float = Field(default=0.2, alias="GEMINI_TEMPERATURE")
    gemini_timeout_s: float = Field(default=180.0, alias="GEMINI_TIMEOUT_S")

    # --- Voiceover (Azure or local only) ---
    voiceover: bool = Field(default=True, alias="VOICEOVER")
    # local (default): Chatterbox service -> Piper | azure: Azure -> Chatterbox -> Piper | piper: Piper only
    tts_provider: str = Field(default="local", alias="TTS_PROVIDER")
    tts_url: str = Field(default="http://tts:8001", alias="TTS_URL")
    # Azure AI Speech (TTS_PROVIDER=azure): native neural voices, free tier 0.5 M characters / month
    azure_speech_key: str | None = Field(default=None, alias="AZURE_SPEECH_KEY")
    azure_speech_region: str = Field(
        default="swedencentral", alias="AZURE_SPEECH_REGION"
    )
    azure_tts_voices: str = Field(
        default="pl:pl-PL-MarekNeural,en:en-US-AndrewMultilingualNeural",
        alias="AZURE_TTS_VOICES",
    )
    azure_tts_rate: str = Field(default="-4%", alias="AZURE_TTS_RATE")
    piper_voices_dir: Path = Field(default=Path("/opt/piper"), alias="PIPER_VOICES_DIR")
    piper_voices: str = Field(
        default="pl:pl_PL-gosia-medium,en:en_US-lessac-medium", alias="PIPER_VOICES"
    )

    # --- Storage ---
    data_dir: Path = Field(default=_BACKEND_DIR / "data", alias="DATA_DIR")
    database_url: str | None = Field(default=None, alias="DATABASE_URL")
    prompts_dir: Path = Field(default_factory=_default_prompts_dir, alias="PROMPTS_DIR")

    # --- Pipeline ---
    auto_render: bool = Field(default=True, alias="AUTO_RENDER")
    max_stage_retries: int = Field(default=2, alias="MAX_STAGE_RETRIES")
    max_render_retries: int = Field(default=2, alias="MAX_RENDER_RETRIES")
    worker_threads: int = Field(
        default=6, alias="WORKER_THREADS"
    )  # lessons generated at the same time
    # parallelism inside one lesson: all scenes are generated at once, each renders as soon as it is ready
    scene_workers: int = Field(default=12, alias="SCENE_WORKERS")
    # when a stage still fails after its retries, continue with the best attempt instead of failing the lesson
    continue_on_failure: bool = Field(default=True, alias="CONTINUE_ON_FAILURE")
    render_workers: int = Field(default=2, alias="RENDER_WORKERS")
    # visual planning: a call that thinks longer than this is cancelled and retried; retries run in parallel
    visual_plan_timeout_s: float = Field(default=75.0, alias="VISUAL_PLAN_TIMEOUT_S")
    visual_plan_parallel_retries: int = Field(
        default=2, alias="VISUAL_PLAN_PARALLEL_RETRIES"
    )

    # --- Manim sandbox ---
    manim_quality: str = Field(default="l", alias="MANIM_QUALITY")  # l | m | h
    render_timeout_s: int = Field(default=240, alias="RENDER_TIMEOUT_S")
    render_max_log_bytes: int = Field(default=20_000, alias="RENDER_MAX_LOG_BYTES")
    render_max_file_mb: int = Field(default=200, alias="RENDER_MAX_FILE_MB")

    cors_origins: str = Field(default="*", alias="CORS_ORIGINS")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @property
    def api_key(self) -> str | None:
        return self.gemini_api_key or self.google_api_key

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "media"

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{(self.data_dir / 'tutorly.db').as_posix()}"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.media_dir.mkdir(parents=True, exist_ok=True)
    return settings
