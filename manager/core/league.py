from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Literal

from .club import Club


@dataclass(slots=True)
class LeagueRules:
    format: Literal["pyramid", "rak"] = "rak"
    teams_per_div: int = 16
    levels: int = 1


@dataclass(slots=True)
class Division:
    name: str
    level: int
    clubs: List[Club] = field(default_factory=list)


@dataclass(slots=True)
class League:
    name: str
    rules: LeagueRules
    divisions: List[Division] = field(default_factory=list)
