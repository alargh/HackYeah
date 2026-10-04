"""Sandboxed Manim runner. Executed as a separate process:

    python -I -B sandbox_runner.py <sandbox_dir> <scene_file> <class_name> <quality>

This file is deliberately standalone (stdlib + manim only). Before any generated code runs it
installs a Python audit hook (PEP 578) that cannot be removed and that:
  * blocks all socket operations (no network),
  * blocks process creation except the LaTeX/FFmpeg tools Manim needs,
  * blocks writes, deletes and renames outside the sandbox directory,
  * blocks ctypes / dynamic code loading helpers.
"""

from __future__ import annotations

import os
import sys

ALLOWED_EXECUTABLES = {"latex", "pdflatex", "xelatex", "lualatex", "dvisvgm", "ffmpeg", "ffprobe", "kpsewhich"}
QUALITY = {"l": "low_quality", "m": "medium_quality", "h": "high_quality"}
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC


def _install_hook(sandbox: str) -> None:
    sandbox = os.path.realpath(sandbox)
    allowed_write_roots = (sandbox, "/dev/null", os.devnull)

    def inside(path: object) -> bool:
        if isinstance(path, int):
            return True  # file descriptors already opened
        try:
            real = os.path.realpath(os.fsdecode(path))  # type: ignore[arg-type]
        except Exception:
            return False
        return any(real == r or real.startswith(r.rstrip(os.sep) + os.sep) for r in allowed_write_roots)

    def hook(event: str, args: tuple) -> None:
        if event.startswith("socket."):
            raise PermissionError(f"sandbox: network access blocked ({event})")
        if event == "subprocess.Popen":
            # audit args: (executable, args, cwd, env); executable is usually None
            program = args[0]
            if program is None:
                argv = args[1]
                if isinstance(argv, (str, bytes)):
                    parts = os.fsdecode(argv).split()
                    program = parts[0] if parts else ""
                else:
                    program = argv[0] if argv else ""
            exe = os.path.basename(os.fsdecode(program)).removesuffix(".exe")
            if exe not in ALLOWED_EXECUTABLES:
                raise PermissionError(f"sandbox: process '{exe}' blocked")
        elif event in ("os.system", "os.exec", "os.spawn", "os.posix_spawn", "os.fork", "os.forkpty", "pty.spawn"):
            raise PermissionError(f"sandbox: {event} blocked")
        elif event == "open":
            path, mode, flags = (args + (None, None, 0))[:3]
            writing = bool(mode and any(c in str(mode) for c in "wax+")) or bool((flags or 0) & _WRITE_FLAGS)
            if writing and not inside(path):
                raise PermissionError(f"sandbox: write outside sandbox blocked ({path})")
        elif event in ("os.remove", "os.rmdir", "os.rename", "os.mkdir", "shutil.rmtree", "os.chmod", "os.chown", "os.truncate", "os.symlink", "os.link"):
            paths = [a for a in args if isinstance(a, (str, bytes, os.PathLike))]
            if any(not inside(p) for p in paths):
                raise PermissionError(f"sandbox: {event} outside sandbox blocked")
        elif event == "ctypes.dlopen":
            raise PermissionError(f"sandbox: {event} blocked")

    sys.addaudithook(hook)


class Voiceover:
    """Plays voiceover clips at `_ml_event("<id>")` hooks (injected from `# EVENT:` markers).

    The voice drives the pacing: before a clip starts, the scene waits until the previous clip has
    finished, and after construct() it waits for the last clip. Clips whose events never fire are
    played in order at the next hook (or at the end), so no narration is ever lost.
    """

    GAP = 0.15  # seconds of breathing room between clips

    def __init__(self, sandbox: str):
        import json

        path = os.path.join(sandbox, "voice_plan.json")
        self.sandbox = sandbox
        self.segments = json.load(open(path, encoding="utf-8"))["segments"] if os.path.exists(path) else []
        self.scene = None
        self.next = 0
        self.busy_until = 0.0

    def _now(self) -> float:
        return float(self.scene.renderer.time)

    def _wait_for_voice(self) -> None:
        remaining = self.busy_until - self._now()
        if remaining > 0.01:
            self.scene.wait(remaining)

    def _play_next(self) -> None:
        seg = self.segments[self.next]
        self.next += 1
        self._wait_for_voice()
        self.scene.add_sound(os.path.join(self.sandbox, seg["file"]))
        self.busy_until = self._now() + seg["duration"] + self.GAP

    def event(self, event_id: str) -> None:
        if self.scene is None:
            return
        pending = [s["event"] for s in self.segments[self.next :]]
        if event_id not in pending:
            return
        target = self.next + pending.index(event_id)
        while self.next <= target:
            self._play_next()

    def finish(self) -> None:
        if self.scene is None:
            return
        while self.next < len(self.segments):
            self._play_next()
        if self.segments:
            self._wait_for_voice()
            self.scene.wait(0.3)


def main() -> int:
    sandbox, scene_file, class_name, quality = sys.argv[1:5]
    os.chdir(sandbox)

    import importlib.util

    from manim import tempconfig  # import Manim before the hook so its own init is unaffected

    voice = Voiceover(sandbox)  # reads the plan before the hook restricts anything
    sys.path.insert(0, sandbox)  # the copied tutorly_visuals runtime (python -I excludes the cwd)
    _install_hook(sandbox)

    options = {
        "media_dir": os.path.join(sandbox, "media"),
        "quality": QUALITY.get(quality, "low_quality"),
        "disable_caching": True,
        "output_file": "scene",
        "format": "mp4",
        "verbosity": "WARNING",
        "progress_bar": "none",
        "preview": False,
    }
    with tempconfig(options):
        spec = importlib.util.spec_from_file_location("generated_scene", os.path.join(sandbox, scene_file))
        if spec is None or spec.loader is None:
            print("cannot load scene file", file=sys.stderr)
            return 2
        module = importlib.util.module_from_spec(spec)
        module.__dict__["_ml_event"] = voice.event
        spec.loader.exec_module(module)
        scene_cls = getattr(module, class_name, None)
        if scene_cls is None:
            print(f"class {class_name} not found", file=sys.stderr)
            return 3
        scene = scene_cls()
        voice.scene = scene
        construct = scene.construct

        def construct_with_voice() -> None:
            construct()
            voice.finish()

        scene.construct = construct_with_voice
        scene.render()
    print("RENDER_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
