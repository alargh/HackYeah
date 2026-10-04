"""Voiceover: Azure/local synthesis and Piper fallback."""

import array
import math
import time
import wave
from pathlib import Path

import pytest

from app.services import tts
from app.services.tts import (
    FallbackSpeech,
    PiperSpeech,
    split_pcm_to_wavs,
    split_points,
    wav_duration,
)

RATE = 16000


def _tone(seconds: float) -> list[int]:
    return [
        int(8000 * math.sin(2 * math.pi * 220 * i / RATE))
        for i in range(int(seconds * RATE))
    ]


def _speech_with_pauses(parts: list[float], pause: float = 0.5) -> array.array:
    out = array.array("h")
    for i, p in enumerate(parts):
        out.extend(_tone(p))
        if i < len(parts) - 1:
            out.extend([0] * int(pause * RATE))
    return out


def test_split_points_land_in_the_pauses():
    samples = _speech_with_pauses([2.0, 3.0, 1.5])
    # weights deliberately a bit off (text length only estimates speaking time)
    cuts = split_points(samples, RATE, [2.4, 2.7, 1.4])
    pauses = [(2.0, 2.5), (5.5, 6.0)]
    for cut, (a, b) in zip(cuts, pauses):
        assert a <= cut / RATE <= b, (cut / RATE, a, b)


def test_scene_audio_is_split_into_one_wav_per_segment(tmp_path):
    samples = _speech_with_pauses([1.0, 2.0])
    paths = [tmp_path / "n1.wav", tmp_path / "n2.wav"]
    durations = split_pcm_to_wavs(
        samples.tobytes(), RATE, ["short one", "a longer second sentence here"], paths
    )
    assert len(durations) == 2 and all(p.is_file() for p in paths)
    assert durations[0] == pytest.approx(wav_duration(paths[0]))
    assert sum(durations) == pytest.approx(len(samples) / RATE, abs=0.01)
    assert 0.9 <= durations[0] <= 1.6


class _Broken:
    model_name, voice = "broken", "none"

    def synthesize_scene(self, texts, language, out_paths):
        raise tts.SpeechError("429 quota")


class _Working:
    model_name, voice = "piper", "pl_PL-gosia-medium"

    def synthesize_scene(self, texts, language, out_paths):
        for p in out_paths:
            p.write_bytes(tts.silent_wav(0.4))
        return [0.4] * len(out_paths)


def test_fallback_voice_is_used_and_reported(tmp_path):
    speech = FallbackSpeech(_Broken(), _Working())
    durations, model, voice = speech.synthesize_with_info(
        ["x", "y"], "pl", [tmp_path / "a.wav", tmp_path / "b.wav"]
    )
    assert durations == [0.4, 0.4] and model == "piper"
    with pytest.raises(tts.SpeechError):
        FallbackSpeech(_Broken(), None).synthesize_scene(
            ["x"], "pl", [tmp_path / "c.wav"]
        )


PIPER_DIR = Path("/opt/piper")


@pytest.mark.skipif(
    not (PIPER_DIR / "pl_PL-gosia-medium.onnx").is_file(),
    reason="Piper voices not installed",
)
def test_piper_speaks_polish_offline(tmp_path):
    piper = PiperSpeech(
        PIPER_DIR, {"pl": "pl_PL-gosia-medium", "en": "en_US-lessac-medium"}
    )
    paths = [tmp_path / "n1.wav", tmp_path / "n2.wav"]
    texts = [
        "Pięć silnia to sto dwadzieścia.",
        "Mnożymy przez dwa, bo A i B mogą zamienić się miejscami.",
    ]
    d = piper.synthesize_scene(texts, "pl", paths)
    assert all(x > 0.8 for x in d) and d[1] > d[0]
    with wave.open(str(paths[1])) as w:
        samples = array.array("h", w.readframes(w.getnframes()))
    assert max(abs(s) for s in samples) > 1000  # actual speech, not silence


# ---------------------------------------------------------------- local neural voice service


def _fake_service(handler_fn):
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            status, payload = handler_fn(body)
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def test_local_neural_voice_client(tmp_path, monkeypatch):
    import base64

    from app.services.tts import LocalNeuralSpeech

    monkeypatch.setattr(LocalNeuralSpeech, "_down_until", 0.0)
    seen = {}

    def ok(body):
        seen.update(body)
        return 200, {
            "sample_rate": 24000,
            "clips": [
                base64.b64encode(tts.silent_wav(0.5 + i)).decode()
                for i, _ in enumerate(body["texts"])
            ],
        }

    srv = _fake_service(ok)
    try:
        speech = LocalNeuralSpeech(f"http://127.0.0.1:{srv.server_port}")
        d = speech.synthesize_scene(
            ["raz", "dwa"], "pl", [tmp_path / "1.wav", tmp_path / "2.wav"]
        )
    finally:
        srv.shutdown()
    assert seen == {"texts": ["raz", "dwa"], "language": "pl"}  # one request per scene
    assert d == pytest.approx([0.5, 1.5], abs=0.01)


def test_unreachable_local_voice_falls_back_fast(tmp_path, monkeypatch):
    from app.services.tts import LocalNeuralSpeech

    monkeypatch.setattr(LocalNeuralSpeech, "_down_until", 0.0)
    chain = FallbackSpeech(
        LocalNeuralSpeech("http://127.0.0.1:9", timeout_s=2), _Working()
    )
    d, model, _ = chain.synthesize_with_info(["x"], "pl", [tmp_path / "a.wav"])
    assert (
        model == "piper" and LocalNeuralSpeech._down_until > time.time()
    )  # skipped for a minute afterwards


def test_voice_chain_order(tmp_path):
    from app.core.config import Settings
    from app.core.container import build_tts
    from app.services.tts import LocalNeuralSpeech

    base = dict(DATA_DIR=tmp_path, PIPER_VOICES_DIR=PIPER_DIR, GEMINI_API_KEY="k")
    local = build_tts(Settings(**base, TTS_PROVIDER="local"))
    assert isinstance(
        local.primary if isinstance(local, FallbackSpeech) else local, LocalNeuralSpeech
    )
    with pytest.raises(ValueError, match="TTS_PROVIDER"):
        build_tts(Settings(**base, TTS_PROVIDER="gemini"))
    assert build_tts(Settings(**base, VOICEOVER=False)) is None


# ---------------------------------------------------------------- Azure neural voices


def _fake_azure(status=200):
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    seen = []

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"])).decode()
            seen.append(
                {
                    "ssml": body,
                    "key": self.headers["Ocp-Apim-Subscription-Key"],
                    "fmt": self.headers["X-Microsoft-OutputFormat"],
                }
            )
            data = tts.silent_wav(0.7) if status == 200 else b"denied"
            self.send_response(status)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, seen


def test_azure_speech_sends_polish_ssml(tmp_path, monkeypatch):
    from app.services.tts import AzureSpeech

    monkeypatch.setattr(AzureSpeech, "_blocked_until", 0.0)
    srv, seen = _fake_azure()
    try:
        az = AzureSpeech(
            "secret",
            "swedencentral",
            {"pl": "pl-PL-AgnieszkaNeural"},
            endpoint=f"http://127.0.0.1:{srv.server_port}/v1",
        )
        d = az.synthesize_scene(
            ["Gdy a < b & b > 0, to…", "Drugie zdanie."],
            "pl",
            [tmp_path / "1.wav", tmp_path / "2.wav"],
        )
    finally:
        srv.shutdown()
    assert d == pytest.approx([0.7, 0.7], abs=0.01) and len(seen) == 2
    assert (
        "name='pl-PL-AgnieszkaNeural'" in seen[0]["ssml"]
        and "xml:lang='pl-PL'" in seen[0]["ssml"]
    )
    assert "a &lt; b &amp; b &gt; 0" in seen[0]["ssml"]  # maths text is XML-escaped
    assert seen[0]["key"] == "secret" and seen[0]["fmt"] == "riff-24khz-16bit-mono-pcm"


def test_azure_bad_key_falls_back_and_pauses(tmp_path, monkeypatch):
    from app.services.tts import AzureSpeech

    monkeypatch.setattr(AzureSpeech, "_blocked_until", 0.0)
    srv, _ = _fake_azure(status=401)
    try:
        az = AzureSpeech(
            "bad",
            "x",
            {"pl": "pl-PL-MarekNeural"},
            endpoint=f"http://127.0.0.1:{srv.server_port}/v1",
        )
        d, model, _ = FallbackSpeech(az, _Working()).synthesize_with_info(
            ["x"], "pl", [tmp_path / "a.wav"]
        )
    finally:
        srv.shutdown()
    assert model == "piper" and AzureSpeech._blocked_until > time.time()


def test_azure_chain(tmp_path):
    from app.core.config import Settings
    from app.core.container import build_tts
    from app.services.tts import AzureSpeech, LocalNeuralSpeech

    chain = build_tts(
        Settings(
            DATA_DIR=tmp_path,
            PIPER_VOICES_DIR=PIPER_DIR,
            TTS_PROVIDER="azure",
            AZURE_SPEECH_KEY="k",
            AZURE_TTS_VOICES="pl:pl-PL-ZofiaNeural",
        )
    )
    assert isinstance(chain.primary, AzureSpeech) and chain.primary.voices == {
        "pl": "pl-PL-ZofiaNeural"
    }
    nxt = (
        chain.fallback.primary
        if isinstance(chain.fallback, FallbackSpeech)
        else chain.fallback
    )
    assert isinstance(nxt, LocalNeuralSpeech)
    # without a key Azure is simply skipped
    no_key = build_tts(
        Settings(
            DATA_DIR=tmp_path,
            PIPER_VOICES_DIR=PIPER_DIR,
            TTS_PROVIDER="azure",
            AZURE_SPEECH_KEY="",
        )
    )
    assert not isinstance(getattr(no_key, "primary", no_key), AzureSpeech)
