from __future__ import annotations

import random
from typing import Dict

from .match import EventType, MatchResult
from .player import Player, Position


def _events_for_player(result: MatchResult, player: Player):
    goals = sum(
        1 for ev in result.events if ev.event is EventType.GOAL and ev.player is player
    )
    assists = sum(
        1
        for ev in result.events
        if ev.event is EventType.GOAL and ev.assist_by is player
    )
    yellows = sum(
        1
        for ev in result.events
        if ev.event is EventType.YELLOW and ev.player is player
    )
    reds = sum(
        1 for ev in result.events if ev.event is EventType.RED and ev.player is player
    )
    return goals, assists, yellows, reds


def player_match_rating(
    result: MatchResult,
    player: Player,
    *,
    minutes: int = 90,
    rng: random.Random | None = None,
) -> float:
    """
    Beräknar en 0–10-ish rating baserad på samma variabler som Best XI:
    - speltid (minuter)
    - skicklighet (1–30)
    - händelser (mål/assist/kort)
    - lagresultat (vinst/oavgjort)
    - positionsbonus (clean sheet / många insläppta)
    - liten dagsform (slump)
    """
    rnd = rng or random

    # 1) Bas från speltid
    played = max(0, min(90, minutes))
    base = 6.0 * (played / 90.0) ** 0.7

    # 2) Skicklighet viktar basen
    skill_norm = (player.skill_open - 5) / 25.0
    rating = base * (1.0 + 0.4 * skill_norm)

    # 3) Händelser
    goals, assists, yellows, reds = _events_for_player(result, player)
    if player.position is Position.FW:
        rating += 1.0 * goals
    elif player.position is Position.MF:
        rating += 0.9 * goals
    elif player.position is Position.DF:
        rating += 0.7 * goals
    else:
        rating += 0.6 * goals
    rating += 0.6 * assists
    rating += -0.4 * yellows + -2.0 * reds

    # 4) Lagresultat
    home = player in result.home.players
    team_goals_for = result.home_stats.goals if home else result.away_stats.goals
    team_goals_against = result.away_stats.goals if home else result.home_stats.goals
    team_won = team_goals_for > team_goals_against
    draw = team_goals_for == team_goals_against

    if team_won:
        rating += 0.3
    elif draw:
        rating += 0.1

    # 5) Positionsberoende defensiv justering
    if player.position in (Position.GK, Position.DF):
        if team_goals_against == 0:
            rating += 0.5
        elif team_goals_against >= 3:
            rating -= 0.5

    # 6) Dagsform
    rating += rnd.gauss(0.0, 0.4)

    return max(3.0, min(10.0, rating))


def compute_ratings_for_match(
    result: MatchResult, default_minutes: int = 90
) -> Dict[int, float]:
    """
    Skapar ett dict {player.id: rating} för alla spelare i matchen.
    (Tills vi har byten använder vi 90 minuter för alla.)
    """
    rng = random.Random()
    ratings: Dict[int, float] = {}
    for p in result.home.players + result.away.players:
        ratings[p.id] = player_match_rating(result, p, minutes=default_minutes, rng=rng)
    return ratings
