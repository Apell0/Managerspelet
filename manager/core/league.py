from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Literal

from .club import Club


@dataclass(slots=True)
class LeagueRules:
    format: Literal["pyramid", "rak"] = "rak"
    teams_per_div: int = 16
    levels: int = 1
    double_round: bool = True
    promote: int = 0
    relegate: int = 0
    divisions_per_level: List[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Säkra rimliga värden även om äldre sparfiler saknar fältet
        self.teams_per_div = max(1, int(self.teams_per_div))
        self.levels = max(1, int(self.levels))
        self.promote = max(0, int(self.promote))
        self.relegate = max(0, int(self.relegate))
        self.divisions_per_level = _normalise_division_layout(
            self.divisions_per_level, self.levels, self.format
        )
        self.levels = len(self.divisions_per_level)


def _normalise_division_layout(
    layout: Iterable[int] | None, levels: int, fmt: Literal["pyramid", "rak"]
) -> List[int]:
    values: List[int] = []
    if layout is not None:
        for raw in layout:
            try:
                values.append(max(1, int(raw)))
            except Exception:
                continue
    # Trimma/expandera efter önskat antal nivåer
    values = values[:levels]
    while len(values) < levels:
        if fmt == "pyramid":
            prev = values[-1] if values else 1
            values.append(max(1, prev * 2))
        else:
            values.append(1)
    if not values:
        values = [1] * max(1, levels)
    return values


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
