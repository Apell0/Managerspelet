from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .player import Player


@dataclass(slots=True)
class Club:
    name: str
    players: List[Player] = field(default_factory=list)
    cash_sek: int = 0  # ekonomi i kronor, placeholder

    def average_skill(self) -> float:
        if not self.players:
            return 0.0
        return sum(p.skill_open for p in self.players) / len(self.players)
