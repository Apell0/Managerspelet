from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .fixtures import Match, round_robin
from .league import Division, League
from .match import Referee, simulate_match

# ---------------------------
# Enkla taktiker & attityd
# ---------------------------


@dataclass(slots=True)
class Tactic:
    """Flaggor som matchsimulatorn förstår + TEMPO (0.8–1.2 typiskt)."""

    attacking: bool = False
    defending: bool = False
    offside_trap: bool = False
    dark_arts: bool = False
    tempo: float = 1.0


@dataclass(slots=True)
class Aggressiveness:
    """Aggressivitetsnivå: 'Aggressiv' | 'Medel' | 'Lugn'."""

    name: str = "Medel"


# ---------------------------
# Säsongskonfiguration
# ---------------------------


@dataclass(slots=True)
class SeasonConfig:
    """
    Global konfig för körning (domare + *fallback*-taktiker om klubb saknar).
    I praktiken använder vi klubbens egna taktik/aggressivitet om de finns.
    """

    referee: Referee = field(default_factory=lambda: Referee(skill=7, hardness=6))

    # Fallbacks (om en klubb inte har egna värden av någon anledning)
    home_tactic: Tactic = field(
        default_factory=lambda: Tactic(attacking=True, tempo=1.0)
    )
    away_tactic: Tactic = field(
        default_factory=lambda: Tactic(defending=True, tempo=1.0)
    )
    home_aggr: Aggressiveness = field(default_factory=lambda: Aggressiveness("Medel"))
    away_aggr: Aggressiveness = field(default_factory=lambda: Aggressiveness("Medel"))


# ---------------------------
# Spelschema
# ---------------------------


def build_league_schedule(league: League) -> Dict[str, List[Match]]:
    schedule: Dict[str, List[Match]] = {}
    for div in league.divisions:
        rounds = round_robin(
            div.clubs, double_round=getattr(league.rules, "double_round", True)
        )
        matches: List[Match] = []
        for r_index, pairs in enumerate(rounds, start=1):
            for home, away in pairs:
                matches.append(Match(home=home, away=away, round=r_index))
        schedule[div.name] = matches
    return schedule


# ---------------------------
# Spela matcher
# ---------------------------


def _simulate_fixture(m: Match, cfg: SeasonConfig):
    """Kör en fixture med klubbarnas egna taktik/aggressivitet om de finns."""
    home_tactic = getattr(m.home, "tactic", cfg.home_tactic) or cfg.home_tactic
    away_tactic = getattr(m.away, "tactic", cfg.away_tactic) or cfg.away_tactic
    home_aggr = getattr(m.home, "aggressiveness", cfg.home_aggr) or cfg.home_aggr
    away_aggr = getattr(m.away, "aggressiveness", cfg.away_aggr) or cfg.away_aggr

    return simulate_match(
        m.home,
        m.away,
        referee=cfg.referee,
        home_tactic=home_tactic,
        away_tactic=away_tactic,
        home_aggr=home_aggr,
        away_aggr=away_aggr,
    )


def play_round(fixtures: List[Match], round_no: int, cfg: SeasonConfig) -> List:
    todays = [m for m in fixtures if getattr(m, "round", 0) == int(round_no)]
    return [_simulate_fixture(m, cfg) for m in todays]


def play_league(div: Division, fixtures: List[Match], cfg: SeasonConfig) -> List:
    max_round = max((getattr(m, "round", 0) for m in fixtures), default=0)
    all_results = []
    for r in range(1, max_round + 1):
        todays = [m for m in fixtures if getattr(m, "round", 0) == r]
        for m in todays:
            all_results.append(_simulate_fixture(m, cfg))
    return all_results


def play_cup(fixtures: List[Match], cfg: SeasonConfig) -> List:
    return [_simulate_fixture(m, cfg) for m in fixtures]
