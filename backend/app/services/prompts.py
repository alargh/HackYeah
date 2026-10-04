"""Versioned prompt store. Prompts live in `prompts/*.md` with a small front-matter header:

    ---
    name: math_reasoner
    version: 1.2.0
    ---
    <system instruction markdown>
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Prompt:
    name: str
    version: str
    body: str


class PromptNotFound(FileNotFoundError):
    pass


def _parse(name: str, text: str) -> Prompt:
    meta: dict[str, str] = {}
    body = text
    if text.startswith("---"):
        _, header, body = text.split("---", 2)
        for line in header.strip().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
    return Prompt(name=meta.get("name", name), version=meta.get("version", "0.0.0"), body=body.strip())


class PromptStore:
    def __init__(self, directory: Path):
        self.directory = Path(directory)

    @lru_cache(maxsize=64)
    def get(self, name: str) -> Prompt:
        path = self.directory / f"{name}.md"
        if not path.is_file():
            raise PromptNotFound(f"prompt '{name}' not found in {self.directory}")
        return _parse(name, path.read_text(encoding="utf-8"))

    def versions(self) -> dict[str, str]:
        return {p.stem: self.get(p.stem).version for p in sorted(self.directory.glob("*.md"))}
