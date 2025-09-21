from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List

from .player import Player

if TYPE_CHECKING:
    # Endast för type hints (körs inte vid runtime) → ingen cirkulär import
    from .season import Aggressiveness, Tactic


def _default_tactic():
    # Lazy import för att undvika cirkulär import vid runtime
    from .season import Tactic

    return Tactic(attacking=False, defending=False, offside_trap=False, tempo=1.0)


def _default_aggr():
    # Lazy import för att undvika cirkulär import vid runtime
    from .season import Aggressiveness

    return Aggressiveness("Medel")


@dataclass(slots=True)
class Club:
    name: str
    players: List[Player] = field(default_factory=list)
    cash_sek: int = 0

    # Per-klubb taktik & aggressivitet (persistenta)
    tactic: "Tactic" = field(default_factory=_default_tactic)
    aggressiveness: "Aggressiveness" = field(default_factory=_default_aggr)

    def average_skill(self) -> float:
        if not self.players:
            return 0.0
        return sum(getattr(p, "skill_open", 5) for p in self.players) / len(
            self.players
        )
