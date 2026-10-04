"""Tutorly local voice service: Chatterbox Multilingual (Resemble AI, MIT licence) on CPU.

Runs in its own container because its pinned dependencies (torch 2.6, numpy<2) conflict with Manim's.
The model is loaded once at startup; the backend sends all narration lines of a scene in one request.

POST /synthesize {"texts": [...], "language": "pl"} -> {"sample_rate": 24000, "clips": [base64 WAV, ...]}
GET  /health
"""

from __future__ import annotations

import base64
import io
import logging
import os
import threading
import time
import wave

import numpy as np
import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

log = logging.getLogger("tutorly-tts")
logging.basicConfig(level=logging.INFO)

torch.set_num_threads(int(os.environ.get("TTS_THREADS", "8")))
DEVICE = os.environ.get("TTS_DEVICE") or ("cuda" if torch.cuda.is_available() else "cpu")
SUPPORTED = {
    "ar", "da", "de", "el", "en", "es", "fi", "fr", "he", "hi", "it", "ja", "ko", "ms", "nl", "no", "pl", "pt", "ru",
    "sv", "sw", "tr", "zh",
}
EXAGGERATION = float(os.environ.get("TTS_EXAGGERATION", "0.45"))  # 0.5 = neutral; lower = calmer teacher voice
CFG_WEIGHT = float(os.environ.get("TTS_CFG_WEIGHT", "0.5"))
VOICE_PROMPT = os.environ.get("TTS_VOICE_PROMPT")  # optional reference WAV used for every language
VOICE_DIR = os.environ.get("TTS_VOICE_DIR", "/voices")  # per-language reference voices: <lang>.wav (e.g. pl.wav)


def voice_prompt(lang: str) -> str | None:
    """A native reference voice for the language (Chatterbox clones its timbre and accent); without one the
    model's default (English) speaker is used, which sounds flat and accented in other languages."""
    candidate = os.path.join(VOICE_DIR, f"{lang}.wav")
    if os.path.isfile(candidate):
        return candidate
    return VOICE_PROMPT

app = FastAPI(title="Tutorly TTS")
_model = None
_lock = threading.Lock()  # one generation at a time: the model is not thread-safe and uses all cores


def model():
    global _model
    if _model is None:
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS

        t = time.time()
        _model = ChatterboxMultilingualTTS.from_pretrained(device=DEVICE)
        gpu = torch.cuda.get_device_name(0) if DEVICE == "cuda" else "-"
        log.info("chatterbox loaded on %s (%s) in %.1fs", DEVICE, gpu, time.time() - t)
    return _model


@app.on_event("startup")
def _warm() -> None:
    model()


class Request(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=20)
    language: str = "en"


def _wav_b64(samples: np.ndarray, rate: int) -> str:
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return base64.b64encode(buf.getvalue()).decode()


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok", "model": "chatterbox-multilingual", "device": DEVICE,
        "gpu": torch.cuda.get_device_name(0) if DEVICE == "cuda" else None,
        "loaded": _model is not None, "languages": sorted(SUPPORTED),
        "reference_voices": sorted(f[:-4] for f in os.listdir(VOICE_DIR) if f.endswith(".wav")) if os.path.isdir(VOICE_DIR) else [],
    }


@app.post("/synthesize")
def synthesize(req: Request) -> dict:
    lang = req.language.lower()[:2]
    if lang not in SUPPORTED:
        raise HTTPException(422, f"language '{lang}' not supported")
    m = model()
    clips = []
    t0 = time.time()
    with _lock:
        for text in req.texts:
            kwargs = {"language_id": lang, "exaggeration": EXAGGERATION, "cfg_weight": CFG_WEIGHT}
            prompt = voice_prompt(lang)
            if prompt:
                kwargs["audio_prompt_path"] = prompt
            wav = m.generate(text.strip(), **kwargs)
            samples = wav.squeeze().detach().cpu().numpy().astype(np.float32)
            clips.append(_wav_b64(samples, m.sr))
    log.info("synthesised %d clip(s) on %s in %.1fs (voice: %s)", len(clips), DEVICE, time.time() - t0, voice_prompt(lang) or "default")
    return {"sample_rate": m.sr, "clips": clips}
