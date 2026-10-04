"""Wiring: builds the pipeline from settings. Tests build their own with a fake transport."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.services.gemini import GeminiClient, GoogleGenAITransport, LLMTransport
from app.services.manim import ManimRenderer
from app.services.pipeline import LessonPipeline
from app.services.prompts import PromptStore
from app.services.tts import (
    AzureSpeech,
    FallbackSpeech,
    LocalNeuralSpeech,
    PiperSpeech,
    SpeechSynthesizer,
)
from app.workers.jobs import JobRunner


@dataclass
class Container:
    settings: Settings
    pipeline: LessonPipeline | None
    jobs: JobRunner
    prompts: PromptStore
    llm_error: str | None = None


def build_pipeline(
    settings: Settings, transport: LLMTransport, tts: SpeechSynthesizer | None = None
) -> LessonPipeline:
    prompts = PromptStore(settings.prompts_dir)
    llm = GeminiClient(transport, prompts)
    renderer = ManimRenderer(
        quality=settings.manim_quality,
        timeout_s=settings.render_timeout_s,
        max_log_bytes=settings.render_max_log_bytes,
        max_file_mb=settings.render_max_file_mb,
    )
    return LessonPipeline(llm, renderer, settings, tts=tts)


def build_container(settings: Settings) -> Container:
    prompts = PromptStore(settings.prompts_dir)
    jobs = JobRunner(settings.worker_threads)
    if not settings.api_key:
        return Container(
            settings, None, jobs, prompts, llm_error="GEMINI_API_KEY is not set"
        )
    transport = GoogleGenAITransport(
        api_key=settings.api_key,
        model=settings.gemini_model,
        temperature=settings.gemini_temperature,
        timeout_s=settings.gemini_timeout_s,
    )
    return Container(
        settings,
        build_pipeline(settings, transport, build_tts(settings)),
        jobs,
        prompts,
    )


def build_tts(settings: Settings) -> SpeechSynthesizer | None:
    """Build an Azure/local voice chain; every configured link falls back per scene."""
    if not settings.voiceover:
        return None
    if settings.tts_provider not in {"local", "azure", "piper"}:
        raise ValueError("TTS_PROVIDER must be one of: azure, local, piper")
    piper = None
    voices = dict(v.split(":", 1) for v in settings.piper_voices.split(",") if ":" in v)
    if any(
        (settings.piper_voices_dir / f"{name}.onnx").is_file()
        for name in voices.values()
    ):
        piper = PiperSpeech(settings.piper_voices_dir, voices)
    if settings.tts_provider == "piper":
        return piper
    chain: SpeechSynthesizer | None = piper
    if settings.tts_url:
        local = LocalNeuralSpeech(settings.tts_url)
        chain = FallbackSpeech(local, piper) if piper else local
    if settings.tts_provider == "azure" and settings.azure_speech_key:
        voices = dict(
            v.split(":", 1) for v in settings.azure_tts_voices.split(",") if ":" in v
        )
        azure = AzureSpeech(
            settings.azure_speech_key,
            settings.azure_speech_region,
            voices,
            rate=settings.azure_tts_rate,
        )
        chain = FallbackSpeech(azure, chain) if chain else azure
    return chain
