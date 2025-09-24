from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

from .club import Club
from .cup import CupRules
from .match import MatchResult, Referee, simulate_match
from .player import Player, Position
from .tactics import TACTICS, Aggression, TacticName, TacticProfile

if TYPE_CHECKING:  # pragma: no cover - endast type hints
    from .league import League
    from .stats import MatchRecord


@dataclass(slots=True)
class CupState:
    rules: CupRules
    current_clubs: List[Club]  # lag som står kvar och ska in i NÄSTA runda
    finished: bool = False
    winner: Optional[Club] = None  # sätts när finished=True


def _two_leg_tie(
    a: Club,
    b: Club,
    *,
    referee: Referee,
    home_tactic: TacticProfile,
    away_tactic: TacticProfile,
    home_aggr: Aggression,
    away_aggr: Aggression,
) -> Tuple[List[MatchResult], Club]:
    r1 = simulate_match(
        a,
        b,
        referee=referee,
        home_tactic=home_tactic,
        away_tactic=away_tactic,
        home_aggr=home_aggr,
        away_aggr=away_aggr,
    )
    r2 = simulate_match(
        b,
        a,
        referee=referee,
        home_tactic=home_tactic,
        away_tactic=away_tactic,
        home_aggr=home_aggr,
        away_aggr=away_aggr,
    )
    agg_a = r1.home_stats.goals + r2.away_stats.goals
    agg_b = r1.away_stats.goals + r2.home_stats.goals
    if agg_a > agg_b:
        return [r1, r2], a
    if agg_b > agg_a:
        return [r1, r2], b
    return [r1, r2], random.choice([a, b])


def _single_leg(
    a: Club,
    b: Club,
    *,
    referee: Referee,
    home_tactic: TacticProfile,
    away_tactic: TacticProfile,
    home_aggr: Aggression,
    away_aggr: Aggression,
) -> Tuple[MatchResult, Club]:
    r = simulate_match(
        a,
        b,
        referee=referee,
        home_tactic=home_tactic,
        away_tactic=away_tactic,
        home_aggr=home_aggr,
        away_aggr=away_aggr,
    )
    if r.home_stats.goals > r.away_stats.goals:
        return r, a
    if r.away_stats.goals > r.home_stats.goals:
        return r, b
    return r, random.choice([a, b])


def create_cup_state(entrants: List[Club], rules: CupRules) -> CupState:
    # Fyll upp till närmsta tvåpotens med byes (de som möter None avancerar direkt)
    n = len(entrants)
    power = 1
    while power < n:
        power *= 2
    byes = power - n
    current: List[Club] = entrants[:] + []  # kopia
    # Lägg till byes genom att direkt låta sista lagen avancera (slippa None i state)
    current += current[:byes] if byes > 0 else []
    return CupState(
        rules=rules,
        current_clubs=current,
        finished=(len(current) <= 1),
        winner=(current[0] if len(current) == 1 else None),
    )


def advance_cup_round(
    state: CupState,
    *,
    referee: Referee,
    home_tactic: TacticProfile = TACTICS[TacticName.BALANCED_442],
    away_tactic: TacticProfile = TACTICS[TacticName.ATTACKING_433],
    home_aggr: Aggression = Aggression.MEDEL,
    away_aggr: Aggression = Aggression.MEDEL,
) -> List[MatchResult]:
    """
    Spelar EN runda och uppdaterar state in-place.
    Returnerar matchresultaten för rundan.
    """
    if state.finished or len(state.current_clubs) <= 1:
        state.finished = True
        state.winner = state.current_clubs[0] if state.current_clubs else None
        return []

    pairs = []
    clubs = state.current_clubs
    for i in range(0, len(clubs), 2):
        a = clubs[i]
        b = clubs[i + 1] if i + 1 < len(clubs) else None
        if b is None:
            pairs.append((a, None))
        else:
            pairs.append((a, b))

    results: List[MatchResult] = []
    winners: List[Club] = []

    is_final = len(pairs) == 1
    legs = (
        1
        if (is_final and not state.rules.final_two_legged)
        else (2 if state.rules.two_legged else 1)
    )

    for a, b in pairs:
        if b is None:
            winners.append(a)
            continue
        if legs == 1:
            r, win = _single_leg(
                a,
                b,
                referee=referee,
                home_tactic=home_tactic,
                away_tactic=away_tactic,
                home_aggr=home_aggr,
                away_aggr=away_aggr,
            )
            results.append(r)
            winners.append(win)
        else:
            rs, win = _two_leg_tie(
                a,
                b,
                referee=referee,
                home_tactic=home_tactic,
                away_tactic=away_tactic,
                home_aggr=home_aggr,
                away_aggr=away_aggr,
            )
            results.extend(rs)
            winners.append(win)

    state.current_clubs = winners
    if len(winners) == 1:
        state.finished = True
        state.winner = winners[0]
    return results


def finish_cup(
    state: CupState,
    *,
    referee: Referee,
    home_tactic: TacticProfile = TACTICS[TacticName.BALANCED_442],
    away_tactic: TacticProfile = TACTICS[TacticName.ATTACKING_433],
    home_aggr: Aggression = Aggression.MEDEL,
    away_aggr: Aggression = Aggression.MEDEL,
) -> List[List[MatchResult]]:
    """Spelar klart turneringen från nuvarande state och returnerar resultat per runda."""
    all_rounds: List[List[MatchResult]] = []
    while not state.finished:
        rnd = advance_cup_round(
            state,
            referee=referee,
            home_tactic=home_tactic,
            away_tactic=away_tactic,
            home_aggr=home_aggr,
            away_aggr=away_aggr,
        )
        all_rounds.append(rnd)
    return all_rounds


# ---------------------------------------------------------------
# Bracket- och statistik-hjälpare
# ---------------------------------------------------------------


def _rec_get(record, name: str, default=None):
    if isinstance(record, dict):
        return record.get(name, default)
    return getattr(record, name, default)


def match_records_by_competition(
    match_log: List["MatchRecord"], competition: str
) -> Dict[int, List["MatchRecord"]]:
    target = str(competition or "").lower()
    grouped: Dict[int, List["MatchRecord"]] = {}
    for rec in match_log or []:
        comp = str(_rec_get(rec, "competition", "")).lower()
        if comp != target:
            continue
        rnd = int(_rec_get(rec, "round", 0))
        grouped.setdefault(rnd, []).append(rec)
    for rnd, records in grouped.items():
        records.sort(key=lambda r: (_rec_get(r, "home", ""), _rec_get(r, "away", "")))
    return dict(sorted(grouped.items()))


def cup_match_records_by_round(match_log: List["MatchRecord"]) -> Dict[int, List["MatchRecord"]]:
    return match_records_by_competition(match_log, "cup")


def _player_index(league: "League") -> Dict[int, Tuple[Player, Club]]:
    index: Dict[int, Tuple[Player, Club]] = {}
    if not league:
        return index
    for div in getattr(league, "divisions", []) or []:
        for club in getattr(div, "clubs", []) or []:
            for player in getattr(club, "players", []) or []:
                pid = getattr(player, "id", None)
                if pid is None:
                    continue
                index[int(pid)] = (player, club)
    return index


def competition_round_best_xi(
    league: "League",
    match_log: List["MatchRecord"],
    competition: str,
    round_no: Optional[int] = None,
) -> Tuple[Optional[int], Dict[Position, List[Tuple[Player, float, int, str]]]]:
    groups = match_records_by_competition(match_log, competition)
    if not groups:
        return None, {
            Position.GK: [],
            Position.DF: [],
            Position.MF: [],
            Position.FW: [],
        }

    if round_no is None:
        round_no = max(groups)
    records = groups.get(round_no, [])

    player_map = _player_index(league)
    totals: Dict[int, Tuple[float, int, str]] = {}

    for rec in records:
        ratings = _rec_get(rec, "ratings", {}) or {}
        items = ratings.items() if isinstance(ratings, dict) else list(ratings or [])
        for pid, rating in items:
            try:
                pid_int = int(pid)
            except (TypeError, ValueError):
                continue
            info = player_map.get(pid_int)
            if not info:
                continue
            player, club = info
            try:
                rating_val = float(rating)
            except (TypeError, ValueError):
                continue
            if rating_val <= 0:
                continue
            total, count, club_name = totals.get(pid_int, (0.0, 0, club.name))
            totals[pid_int] = (total + rating_val, count + 1, club_name)

    result: Dict[Position, List[Tuple[Player, float, int, str]]] = {
        Position.GK: [],
        Position.DF: [],
        Position.MF: [],
        Position.FW: [],
    }

    for pid, (total, count, club_name) in totals.items():
        player_info = player_map.get(pid)
        if not player_info or count == 0:
            continue
        player, _club = player_info
        avg = total / count
        pos = getattr(player, "position", None)
        if pos in result:
            result[pos].append((player, avg, count, club_name))

    def _top(pos: Position, limit: int) -> List[Tuple[Player, float, int, str]]:
        pool = sorted(
            result[pos],
            key=lambda item: (item[1], getattr(item[0], "skill_open", 0)),
            reverse=True,
        )
        return pool[:limit]

    return round_no, {
        Position.GK: _top(Position.GK, 1),
        Position.DF: _top(Position.DF, 4),
        Position.MF: _top(Position.MF, 4),
        Position.FW: _top(Position.FW, 2),
    }


def cup_round_best_xi(
    league: "League",
    match_log: List["MatchRecord"],
    round_no: Optional[int] = None,
) -> Tuple[Optional[int], Dict[Position, List[Tuple[Player, float, int, str]]]]:
    return competition_round_best_xi(league, match_log, "cup", round_no)


def build_cup_bracket(
    state: Optional[CupState], match_log: List["MatchRecord"]
) -> Dict[str, object]:
    grouped = cup_match_records_by_round(match_log)
    rounds: List[Dict[str, object]] = []
    for rnd, records in grouped.items():
        matches = []
        for rec in records:
            matches.append(
                {
                    "home": _rec_get(rec, "home", ""),
                    "away": _rec_get(rec, "away", ""),
                    "home_goals": _rec_get(rec, "home_goals", None),
                    "away_goals": _rec_get(rec, "away_goals", None),
                }
            )
        rounds.append({"round": rnd, "matches": matches, "status": "played"})

    if state and not state.finished and state.current_clubs:
        next_round = max(grouped.keys(), default=0) + 1
        matches = []
        clubs = state.current_clubs
        for i in range(0, len(clubs), 2):
            a = clubs[i]
            b = clubs[i + 1] if i + 1 < len(clubs) else None
            matches.append(
                {
                    "home": getattr(a, "name", None),
                    "away": getattr(b, "name", None) if b else None,
                    "home_goals": None,
                    "away_goals": None,
                }
            )
        rounds.append({"round": next_round, "matches": matches, "status": "upcoming"})

    return {
        "rounds": rounds,
        "finished": bool(state and state.finished),
        "winner": getattr(getattr(state, "winner", None), "name", None)
        if state
        else None,
    }
