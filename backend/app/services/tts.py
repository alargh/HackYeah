"""Text-to-speech for the lesson voiceover.

Supported providers are Azure Speech and local neural/offline voices. The pipeline deliberately has no
Gemini voice path: mathematical generation and speech synthesis have separate quotas and failure modes.

The pipeline depends only on the `SpeechSynthesizer` protocol. Output is always mono 16-bit PCM WAV.
"""

from __future__ import annotations

import array
import io
import re
import threading
import time
import wave
from pathlib import Path
from typing import Protocol, runtime_checkable

from app.core.logging import fields, get_logger
from app.services.validation.language import (
    LETTER_CLOSE,
    LETTER_OPEN,
    NUM_CLOSE,
    NUM_OPEN,
    letters_as_words,
)

log = get_logger(__name__)


class SpeechError(RuntimeError):
    pass


@runtime_checkable
class SpeechSynthesizer(Protocol):
    model_name: str
    voice: str

    def synthesize_scene(
        self, texts: list[str], language: str, out_paths: list[Path]
    ) -> list[float]:
        """Write one WAV per narration segment; return their durations in seconds."""
        ...


# ----------------------------------------------------------------------------- WAV helpers


def write_wav(
    pcm: bytes,
    out_path: Path,
    rate: int = 24000,
    channels: int = 1,
    sample_width: int = 2,
) -> float:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(sample_width)
        w.setframerate(rate)
        w.writeframes(pcm)
    return len(pcm) / (rate * channels * sample_width)


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def silent_wav(seconds: float, rate: int = 24000) -> bytes:
    """Helper (tests / fallbacks): WAV bytes of silence."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(seconds * rate))
    return buf.getvalue()


def split_points(
    samples: array.array,
    rate: int,
    weights: list[float],
    window_s: float = 0.9,
    frame_s: float = 0.04,
) -> list[int]:
    """Sample indices where one long recording should be cut into len(weights) parts.

    The expected boundary is proportional to each segment's text length; the cut is moved to the quietest
    frame within ±window_s (the natural pause between sentences)."""
    n = len(samples)
    total = sum(weights) or 1.0
    frame = max(1, int(rate * frame_s))
    cuts, acc = [], 0.0
    for w in weights[:-1]:
        acc += w
        target = int(n * acc / total)
        lo, hi = (
            max(frame, target - int(rate * window_s)),
            min(n - frame, target + int(rate * window_s)),
        )
        best, best_energy = target, float("inf")
        for start in range(lo, max(lo + 1, hi), frame // 2 or 1):
            seg = samples[start : start + frame]
            energy = sum(abs(s) for s in seg) / max(len(seg), 1)
            # prefer the quietest frame, tie-break towards the expected position
            score = energy + abs(start - target) / rate * 50
            if score < best_energy:
                best, best_energy = start + frame // 2, score
        if cuts and best <= cuts[-1]:
            best = cuts[-1] + frame
        cuts.append(min(best, n - 1))
    return cuts


def split_pcm_to_wavs(
    pcm: bytes, rate: int, texts: list[str], out_paths: list[Path]
) -> list[float]:
    samples = array.array("h")
    samples.frombytes(pcm[: len(pcm) - len(pcm) % 2])
    cuts = [0, *split_points(samples, rate, [len(t) + 12 for t in texts]), len(samples)]
    return [
        write_wav(samples[a:b].tobytes(), path, rate)
        for (a, b), path in zip(zip(cuts, cuts[1:]), out_paths)
    ]


_LANG = {
    "pl": "Polish",
    "en": "English",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "uk": "Ukrainian",
}


# ----------------------------------------------------------------------------- Azure neural voices


def _say_letters(xml_text: str, language: str) -> str:
    """«H» -> <say-as interpret-as="characters">H</say-as>: the voice spells the variable."""
    xml_text = re.sub(
        f"{NUM_OPEN}([^{NUM_CLOSE}]*){NUM_CLOSE}",
        r"<say-as interpret-as='cardinal'>\1</say-as>",
        xml_text,
    )
    return re.sub(
        f"{LETTER_OPEN}(.){LETTER_CLOSE}",
        r"<say-as interpret-as='characters'>\1</say-as>",
        xml_text,
    )


class AzureSpeech:
    """Azure AI Speech neural TTS (REST). Native Polish voices: pl-PL-AgnieszkaNeural, -MarekNeural, -ZofiaNeural.
    Free tier F0: 0.5 M characters / month. One request per narration line (fast, ~1 s each)."""

    model_name = "azure-neural-tts"
    _blocked_until = 0.0  # quota exhausted / key rejected: skip Azure for a while

    def __init__(
        self,
        key: str,
        region: str,
        voices: dict[str, str],
        rate: str = "-4%",
        endpoint: str | None = None,
        timeout_s: float = 60.0,
    ):
        self.key = key
        self.voices = voices  # language -> voice name
        self.voice = ",".join(sorted(set(voices.values())))
        self.rate = rate
        self.endpoint = (
            endpoint
            or f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
        )
        self.timeout_s = timeout_s

    def _ssml(self, text: str, language: str) -> bytes:
        from xml.sax.saxutils import escape

        voice = (
            self.voices.get(language)
            or self.voices.get("en")
            or next(iter(self.voices.values()))
        )
        locale = "-".join(voice.split("-")[:2])
        return (
            f"<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='{locale}'>"
            f"<voice name='{voice}'><prosody rate='{self.rate}'>{_say_letters(escape(text.strip()), language)}</prosody></voice></speak>"
        ).encode("utf-8")

    def synthesize_scene(
        self, texts: list[str], language: str, out_paths: list[Path]
    ) -> list[float]:
        import urllib.error
        import urllib.request

        if time.time() < AzureSpeech._blocked_until:
            raise SpeechError("Azure TTS temporarily disabled (quota or key problem)")
        durations = []
        for text, path in zip(texts, out_paths):
            req = urllib.request.Request(
                self.endpoint,
                data=self._ssml(text, language),
                headers={
                    "Ocp-Apim-Subscription-Key": self.key,
                    "Content-Type": "application/ssml+xml",
                    "X-Microsoft-OutputFormat": "riff-24khz-16bit-mono-pcm",
                    "User-Agent": "Tutorly",
                },
            )
            for attempt in range(3):
                try:
                    with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                        audio = resp.read()
                    break
                except urllib.error.HTTPError as exc:
                    if exc.code == 429 and attempt < 2:  # per-second rate limit on F0
                        time.sleep(1.5 * (attempt + 1))
                        continue
                    if exc.code in (
                        401,
                        403,
                    ):  # bad key, or the free monthly quota is used up
                        AzureSpeech._blocked_until = time.time() + 600
                    raise SpeechError(
                        f"Azure TTS error {exc.code}: {exc.read()[:200]!r}"
                    ) from exc
                except (urllib.error.URLError, TimeoutError) as exc:
                    raise SpeechError(f"Azure TTS unreachable: {exc}") from exc
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(audio)
            durations.append(wav_duration(path))
        return durations


# ----------------------------------------------------------------------------- local neural voice (service)


class LocalNeuralSpeech:
    """Chatterbox Multilingual running in the `tts` service (offline, natural voice, Polish + 22 languages)."""

    model_name = "chatterbox-multilingual"
    voice = "chatterbox"
    _down_until = 0.0  # don't wait for a service that is not there

    def __init__(self, url: str, timeout_s: float = 900.0):
        self.url = url.rstrip("/")
        self.timeout_s = timeout_s

    def synthesize_scene(
        self, texts: list[str], language: str, out_paths: list[Path]
    ) -> list[float]:
        texts = [letters_as_words(t, language) for t in texts]
        import base64
        import json
        import urllib.error
        import urllib.request

        if time.time() < LocalNeuralSpeech._down_until:
            raise SpeechError("local voice service unavailable (recently unreachable)")
        body = json.dumps({"texts": texts, "language": language}).encode()
        req = urllib.request.Request(
            f"{self.url}/synthesize",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            raise SpeechError(
                f"local voice error {exc.code}: {exc.read()[:200]!r}"
            ) from exc
        except (urllib.error.URLError, ConnectionError, TimeoutError) as exc:
            LocalNeuralSpeech._down_until = time.time() + 60
            raise SpeechError(f"local voice service unreachable: {exc}") from exc
        durations = []
        for clip, path in zip(data["clips"], out_paths):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(base64.b64decode(clip))
            durations.append(wav_duration(path))
        if len(durations) != len(texts):
            raise SpeechError("local voice returned a different number of clips")
        return durations


# ----------------------------------------------------------------------------- Piper (offline)


class PiperSpeech:
    """Offline neural voice (Piper). Voices are baked into the Docker image (PIPER_VOICES_DIR)."""

    model_name = "piper"

    def __init__(self, voices_dir: Path, voices: dict[str, str]):
        self.voices_dir = Path(voices_dir)
        self.voice_names = voices  # language -> voice file stem
        self.voice = ",".join(sorted(set(voices.values())))
        self._loaded: dict[str, object] = {}
        self._lock = threading.Lock()

    def _voice_for(self, language: str):
        name = self.voice_names.get(language) or self.voice_names.get("en")
        path = self.voices_dir / f"{name}.onnx"
        if not path.is_file():
            raise SpeechError(f"Piper voice not installed: {path}")
        with self._lock:
            if name not in self._loaded:
                from piper import PiperVoice

                self._loaded[name] = PiperVoice.load(str(path))
            return self._loaded[name]

    def synthesize_scene(
        self, texts: list[str], language: str, out_paths: list[Path]
    ) -> list[float]:
        texts = [letters_as_words(t, language) for t in texts]
        voice = self._voice_for(language)
        durations = []
        for text, path in zip(texts, out_paths):
            path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock, wave.open(str(path), "wb") as w:
                voice.synthesize_wav(text, w)
            durations.append(wav_duration(path))
        return durations


class FallbackSpeech:
    """Try the primary voice, fall back per scene. Records which voice was actually used."""

    def __init__(
        self, primary: SpeechSynthesizer | None, fallback: SpeechSynthesizer | None
    ):
        if primary is None and fallback is None:
            raise ValueError("no speech synthesizer configured")
        self.primary, self.fallback = primary, fallback
        self.model_name = (primary or fallback).model_name
        self.voice = (primary or fallback).voice

    def synthesize_with_info(
        self, texts: list[str], language: str, out_paths: list[Path]
    ) -> tuple[list[float], str, str]:
        """Durations plus the model/voice actually used (thread-safe: scenes are voiced in parallel)."""
        if self.primary is not None:
            try:
                return (
                    self.primary.synthesize_scene(texts, language, out_paths),
                    self.primary.model_name,
                    self.primary.voice,
                )
            except Exception as exc:  # noqa: BLE001
                if self.fallback is None:
                    raise
                log.warning(
                    "primary voice failed; using fallback",
                    extra=fields(error=str(exc)[:200]),
                )
        if hasattr(
            self.fallback, "synthesize_with_info"
        ):  # nested chain reports the voice it really used
            return self.fallback.synthesize_with_info(texts, language, out_paths)
        d = self.fallback.synthesize_scene(texts, language, out_paths)
        return d, self.fallback.model_name, self.fallback.voice

    def synthesize_scene(
        self, texts: list[str], language: str, out_paths: list[Path]
    ) -> list[float]:
        return self.synthesize_with_info(texts, language, out_paths)[0]
