"""Turn Pydantic models into JSON schemas that Gemini's structured output accepts reliably."""

from __future__ import annotations

import copy
from typing import Any

from pydantic import BaseModel

_DROP_KEYS = {"title", "default", "examples"}


def _inline(node: Any, defs: dict[str, Any], depth: int = 0) -> Any:
    if depth > 30:
        raise ValueError("schema nesting too deep / recursive")
    if isinstance(node, dict):
        if "$ref" in node:
            name = node["$ref"].split("/")[-1]
            resolved = _inline(copy.deepcopy(defs[name]), defs, depth + 1)
            extra = {k: v for k, v in node.items() if k != "$ref" and k not in _DROP_KEYS}
            return {**resolved, **extra}
        out: dict[str, Any] = {}
        for k, v in node.items():
            if k in _DROP_KEYS or k == "$defs":
                continue
            if k == "properties" and isinstance(v, dict):
                # property names may legitimately be "title"/"default" etc.
                out[k] = {pk: _inline(pv, defs, depth + 1) for pk, pv in v.items()}
                continue
            out[k] = _inline(v, defs, depth + 1)
        # Optional[X] is emitted as anyOf [X, null] -> keep X, allow null via type list where simple.
        if "anyOf" in out:
            non_null = [s for s in out["anyOf"] if s.get("type") != "null"]
            has_null = len(non_null) != len(out["anyOf"])
            if len(non_null) == 1:
                merged = {**{k: v for k, v in out.items() if k != "anyOf"}, **non_null[0]}
                if has_null and isinstance(merged.get("type"), str):
                    merged["type"] = [merged["type"], "null"]
                return merged
        return out
    if isinstance(node, list):
        return [_inline(x, defs, depth + 1) for x in node]
    return node


def gemini_schema(model: type[BaseModel]) -> dict[str, Any]:
    raw = model.model_json_schema()
    return _inline(raw, raw.get("$defs", {}))
