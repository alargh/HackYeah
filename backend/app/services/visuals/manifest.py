"""Typed access to manifest.yaml (the visual capability description)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

MANIFEST_PATH = Path(__file__).with_name("manifest.yaml")


class Entry(BaseModel):
    id: str
    meaning: str = ""


class TemplateSpec(BaseModel):
    id: str
    description: str
    good_for: list[str] = Field(default_factory=list)
    supports: list[str] = Field(default_factory=list)
    object_types: list[str] = Field(default_factory=list)
    default_layout: str
    default_camera: str
    general: bool = False


class Rule(BaseModel):
    value: Any
    severity: Literal["error", "warning"] = "error"


class Manifest(BaseModel):
    version: str
    emphasis: list[Entry]
    object_types: list[Entry]
    operations: list[Entry]
    common_operations: list[str]
    layouts: list[Entry]
    cameras: list[Entry]
    motion: list[Entry]
    templates: list[TemplateSpec]
    quality: dict[str, Rule]

    # --- lookups -----------------------------------------------------------------
    def template(self, template_id: str) -> TemplateSpec | None:
        return next((t for t in self.templates if t.id == template_id), None)

    def ids(self, section: str) -> set[str]:
        return {e.id for e in getattr(self, section)}

    def allowed_operations(self, template_ids: list[str]) -> set[str]:
        ops = set(self.common_operations)
        for tid in template_ids:
            t = self.template(tid)
            if t:
                ops.update(t.supports)
        return ops

    def rule(self, name: str) -> Rule:
        return self.quality[name]


def load_manifest(path: Path = MANIFEST_PATH) -> Manifest:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    manifest = Manifest.model_validate(data)
    _check_consistency(manifest)
    return manifest


def _check_consistency(m: Manifest) -> None:
    """Fail fast on a broken manifest (a typo would otherwise silently disable a template)."""
    ops, layouts, cameras, types = m.ids("operations"), m.ids("layouts"), m.ids("cameras"), m.ids("object_types")
    problems = [f"common op '{o}' unknown" for o in m.common_operations if o not in ops]
    for t in m.templates:
        problems += [f"{t.id}: unknown op '{o}'" for o in t.supports if o not in ops]
        problems += [f"{t.id}: unknown object type '{o}'" for o in t.object_types if o not in types]
        if t.default_layout not in layouts:
            problems.append(f"{t.id}: unknown layout '{t.default_layout}'")
        if t.default_camera not in cameras:
            problems.append(f"{t.id}: unknown camera '{t.default_camera}'")
    if len({t.id for t in m.templates}) != len(m.templates):
        problems.append("duplicate template ids")
    if problems:
        raise ValueError("invalid visual manifest: " + "; ".join(problems))


@lru_cache
def get_manifest() -> Manifest:
    return load_manifest()
