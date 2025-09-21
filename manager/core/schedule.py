from __future__ import annotations

from typing import Dict, List

from .fixtures import Match, round_robin
from .league import League


def build_league_schedule(league: League) -> Dict[str, List[Match]]:
    """Returnerar ett schema per divisions-namn baserat på league.rules.double_round."""
    schedules: Dict[str, List[Match]] = {}
    for div in league.divisions:
        matches = round_robin(div.clubs, double_round=league.rules.double_round)
        schedules[div.name] = matches
    return schedules
