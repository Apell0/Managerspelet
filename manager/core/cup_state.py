from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .club import Club
from .cup import CupRules
from .match import MatchResult, Referee, simulate_match
from .tactics import TACTICS, Aggression, TacticName, TacticProfile


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
