from __future__ import annotations

from dataclasses import dataclass, field

from .club import Club


@dataclass(slots=True)
class TeamStats:
    """Basstatistik för ett lag (stubbar – fylls i senare)."""

    goals: int = 0
    shots_on_target: int = 0
    possession_pct: int = 50  # 0–100
    yellow_cards: int = 0
    red_cards: int = 0


@dataclass(slots=True)
class MatchResult:
    """Resultatobjekt för en match (utan händelser/simulering)."""

    home: Club
    away: Club
    home_stats: TeamStats = field(default_factory=TeamStats)
    away_stats: TeamStats = field(default_factory=TeamStats)

    @property
    def scoreline(self) -> str:
        return f"{self.home_stats.goals}–{self.away_stats.goals}"
