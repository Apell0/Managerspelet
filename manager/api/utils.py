from __future__ import annotations

import re
from typing import Dict

_slug_re = re.compile(r"[^a-z0-9]+")


def slugify(value: str, prefix: str | None = None) -> str:
    base = value.strip().lower()
    base = _slug_re.sub("-", base).strip("-")
    if not base:
        base = "item"
    if prefix:
        return f"{prefix}-{base}"
    return base


def ensure_colors(colors: Dict[str, str | None] | None) -> Dict[str, str | None]:
    if not colors:
        return {"home": None, "away": None}
    out: Dict[str, str | None] = {"home": None, "away": None}
    for key in out:
        if key in colors and colors[key]:
            out[key] = colors[key]
    for key, value in colors.items():
        if key not in out:
            out[key] = value
    return out
