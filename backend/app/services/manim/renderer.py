"""Render untrusted Manim code in an isolated subprocess and collect the video."""

from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from app.core.logging import fields, get_logger

log = get_logger(__name__)

RUNNER = Path(__file__).with_name("sandbox_runner.py")
# Deterministic visual runtime imported by compiled scenes (copied into every sandbox).
VISUAL_RUNTIME = Path(__file__).resolve().parents[1] / "visuals" / "runtime" / "tutorly_visuals"


@dataclass
class RenderResult:
    success: bool
    stdout: str
    stderr: str
    video_path: Path | None = None
    duration_ms: int = 0
    error: str | None = None


_EVENT_LINE = re.compile(r"^[ \t]*#\s*EVENT:\s*([A-Za-z0-9_\-]+)\s*$", re.IGNORECASE)
EVENT_HOOK = "_ml_event"


def inject_event_hooks(code: str) -> str:
    """Turn `# EVENT: <id>` comment markers into `_ml_event("<id>")` calls so the sandbox can start
    the matching voiceover clip at that moment. The call takes the indentation of the next code line
    (comments may be indented arbitrarily). Falls back to the unmodified code if the result is invalid."""
    lines = code.splitlines()
    out: list[str] = []
    for i, line in enumerate(lines):
        m = _EVENT_LINE.match(line)
        if not m:
            out.append(line)
            continue
        indent = None
        for nxt in lines[i + 1 :]:
            if nxt.strip() and not nxt.strip().startswith("#"):
                indent = nxt[: len(nxt) - len(nxt.lstrip())]
                break
        if indent is None:
            indent = line[: len(line) - len(line.lstrip())]
        out.append(f'{indent}{EVENT_HOOK}("{m.group(1)}")')
    new = "\n".join(out) + "\n"
    try:
        ast.parse(new)
    except SyntaxError:
        log.warning("event hook injection produced invalid code; voiceover will not be synchronised")
        return code
    return new


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    half = limit // 2
    return text[:half] + f"\n... [{len(text) - limit} bytes truncated] ...\n" + text[-half:]


def _limits(cpu_s: int, max_file_mb: int):  # pragma: no cover - POSIX only
    def apply() -> None:
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (cpu_s, cpu_s))
        resource.setrlimit(resource.RLIMIT_FSIZE, (max_file_mb * 1024 * 1024,) * 2)
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        os.setsid()

    return apply


def _clean_env(sandbox: Path) -> dict[str, str]:
    # Deliberately minimal: no API keys or app configuration leak into generated code.
    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": str(sandbox),
        "TMPDIR": str(sandbox / "tmp"),
        "TEMP": str(sandbox / "tmp"),
        "TMP": str(sandbox / "tmp"),
        "XDG_CACHE_HOME": str(sandbox / ".cache"),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
    }
    if os.name == "nt":  # needed for Python to start on Windows dev machines
        for key in ("SYSTEMROOT", "WINDIR", "COMSPEC"):
            if key in os.environ:
                env[key] = os.environ[key]
    return env


class ManimRenderer:
    def __init__(self, quality: str = "l", timeout_s: int = 240, max_log_bytes: int = 20_000, max_file_mb: int = 200):
        self.quality = quality
        self.timeout_s = timeout_s
        self.max_log_bytes = max_log_bytes
        self.max_file_mb = max_file_mb

    def render(
        self, code: str, class_name: str, output_path: Path, voiceover: list[dict] | None = None, quality: str | None = None
    ) -> RenderResult:
        """Render `code`. `voiceover` is an ordered list of {id, visual_event, path, duration} clips;
        each clip starts at its visual event and the animation waits for it to finish."""
        t0 = time.perf_counter()
        sandbox = Path(tempfile.mkdtemp(prefix="tutorly_render_"))
        try:
            (sandbox / "tmp").mkdir()
            shutil.copytree(VISUAL_RUNTIME, sandbox / "tutorly_visuals", ignore=shutil.ignore_patterns("__pycache__"))
            plan = []
            if voiceover:
                (sandbox / "audio").mkdir()
                for i, seg in enumerate(voiceover):
                    src = Path(seg["path"])
                    if not src.is_file():
                        continue
                    rel = f"audio/{i:02d}.wav"
                    shutil.copyfile(src, sandbox / rel)
                    plan.append({"id": seg["id"], "event": seg["visual_event"], "file": rel, "duration": float(seg["duration"])})
                code = inject_event_hooks(code)
            (sandbox / "voice_plan.json").write_text(json.dumps({"segments": plan}), encoding="utf-8")
            (sandbox / "scene.py").write_text(code, encoding="utf-8")
            q = quality or self.quality
            timeout_s = self.timeout_s * {"l": 1, "m": 2, "h": 4}.get(q, 1)  # more pixels and frames take longer
            cmd = [sys.executable, "-I", "-B", str(RUNNER), str(sandbox), "scene.py", class_name, q]
            kwargs: dict = {}
            if os.name == "posix":
                kwargs["preexec_fn"] = _limits(timeout_s + 30, self.max_file_mb * (4 if q == "h" else 1))
            try:
                proc = subprocess.run(
                    cmd,
                    cwd=sandbox,
                    env=_clean_env(sandbox),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout_s,
                    stdin=subprocess.DEVNULL,
                    **kwargs,
                )
            except subprocess.TimeoutExpired as exc:
                return RenderResult(
                    success=False,
                    stdout=_truncate(_s(exc.stdout), self.max_log_bytes),
                    stderr=_truncate(_s(exc.stderr), self.max_log_bytes),
                    duration_ms=round((time.perf_counter() - t0) * 1000),
                    error=f"render timed out after {timeout_s}s",
                )
            stdout = _truncate(proc.stdout or "", self.max_log_bytes)
            stderr = _truncate(proc.stderr or "", self.max_log_bytes)
            videos = [p for p in (sandbox / "media").rglob("*.mp4") if "partial_movie_files" not in p.parts]
            if proc.returncode != 0 or not videos:
                return RenderResult(
                    success=False,
                    stdout=stdout,
                    stderr=stderr,
                    duration_ms=round((time.perf_counter() - t0) * 1000),
                    error=f"manim exited with code {proc.returncode}" + ("" if videos else " and produced no video"),
                )
            video = max(videos, key=lambda p: p.stat().st_mtime)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(video, output_path)
            return RenderResult(
                success=True,
                stdout=stdout,
                stderr=stderr,
                video_path=output_path,
                duration_ms=round((time.perf_counter() - t0) * 1000),
            )
        finally:
            shutil.rmtree(sandbox, ignore_errors=True)


def _s(v: bytes | str | None) -> str:
    if v is None:
        return ""
    return v.decode("utf-8", "replace") if isinstance(v, bytes) else v


def concat_videos(videos: list[Path], output: Path, timeout_s: int = 120) -> bool:
    """Concatenate scene videos (same codec/resolution) into one lesson video with FFmpeg."""
    if not videos or shutil.which("ffmpeg") is None:
        return False
    output.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="tutorly_concat_"))
    list_file = output.with_suffix(".txt")
    try:
        # Stream-copy concat needs identical streams: give every scene the same AAC track
        # (a silent one if the scene has no voiceover).
        normalized = []
        for i, v in enumerate(videos):
            n = work / f"{i:03d}.mp4"
            if not _normalize_audio(v, n, timeout_s):
                return False
            normalized.append(n)
        list_file.write_text("".join(f"file '{v.resolve().as_posix()}'\n" for v in normalized), encoding="utf-8")
        proc = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(output)],
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        if proc.returncode != 0:
            log.warning("video concat failed", extra=fields(stderr=proc.stderr[-500:]))
            return False
        return output.exists()
    except subprocess.TimeoutExpired:
        return False
    finally:
        list_file.unlink(missing_ok=True)
        shutil.rmtree(work, ignore_errors=True)


def has_audio(video: Path) -> bool:
    if shutil.which("ffprobe") is None:
        return False
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", str(video)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return bool(proc.stdout.strip())


def _normalize_audio(video: Path, out: Path, timeout_s: int) -> bool:
    if has_audio(video):
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-c:v", "copy", "-c:a", "aac", "-ar", "44100", "-ac", "1", str(out)]
    else:
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
            "-shortest", "-c:v", "copy", "-c:a", "aac", "-ar", "44100", "-ac", "1", str(out),
        ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        return False
    if proc.returncode != 0:
        log.warning("audio normalisation failed", extra=fields(stderr=proc.stderr[-500:]))
    return proc.returncode == 0
