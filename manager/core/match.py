from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional

from .club import Club
from .player import Player, Position


class EventType(Enum):
    GOAL = auto()
    YELLOW = auto()
    RED = auto()


@dataclass(slots=True)
class PlayerEvent:
    minute: int
    event: EventType
    player: Player
    assist_by: Optional[Player] = None


@dataclass(slots=True)
class TeamStats:
    goals: int = 0
    shots_on_target: int = 0
    possession_pct: int = 50  # 0–100
    yellow_cards: int = 0
    red_cards: int = 0


@dataclass(slots=True)
class MatchResult:
    home: Club
    away: Club
    home_stats: TeamStats
    away_stats: TeamStats
    events: List[PlayerEvent] = field(default_factory=list)

    @property
    def scoreline(self) -> str:
        return f"{self.home_stats.goals}–{self.away_stats.goals}"


@dataclass(slots=True)
class Referee:
    skill: int = 6  # 1–10 (högre = bättre bedömningar)
    hard: int = 5  # 1–10 (högre = fler kort)


# ------- Hjälpfunktioner -------


def _avg_skill(club: Club) -> float:
    return club.average_skill() or 5.0


def _pick_scorer(club: Club) -> Player:
    fws = [p for p in club.players if p.position is Position.FW]
    mfs = [p for p in club.players if p.position is Position.MF]
    dfs = [p for p in club.players if p.position is Position.DF]
    gks = [p for p in club.players if p.position is Position.GK]
    pool: List[Player] = fws * 5 + mfs * 3 + dfs * 1 + (gks or [])
    return random.choice(pool or club.players)


def _pick_assist(club: Club, scorer: Player) -> Optional[Player]:
    candidates = [p for p in club.players if p is not scorer]
    if not candidates:
        return None
    return random.choice(candidates) if random.random() < 0.6 else None


def _goal_minutes(total_goals: int) -> List[int]:
    return sorted(random.sample(range(1, 91), k=total_goals)) if total_goals > 0 else []


# ------- Minimal simulering -------


def simulate_match(
    home: Club,
    away: Club,
    referee: Optional[Referee] = None,
    seed: Optional[int] = None,
) -> MatchResult:
    if seed is not None:
        random.seed(seed)

    ref = referee or Referee()

    h_strength = _avg_skill(home) / 5.0
    a_strength = _avg_skill(away) / 5.0
    h_strength *= 1.10  # hemmafördel
    h_strength = max(0.2, min(2.5, h_strength))
    a_strength = max(0.2, min(2.5, a_strength))

    def _sample_goals(lmbd: float) -> int:
        probs = [
            0.3 * max(0.1, 1.0 - lmbd),
            0.3 * min(0.8, lmbd),
            0.2 * min(0.7, lmbd * 0.7),
            0.1 * min(0.6, lmbd * 0.5),
            0.06 * min(0.5, lmbd * 0.4),
            0.03 * min(0.4, lmbd * 0.3),
            0.01 * min(0.3, lmbd * 0.2),
        ]
        s = sum(probs)
        probs = [p / s for p in probs]
        r = random.random()
        acc = 0.0
        for i, p in enumerate(probs):
            acc += p
            if r <= acc:
                return i
        return 0

    home_goals = _sample_goals(h_strength)
    away_goals = _sample_goals(a_strength)

    home_stats = TeamStats(goals=home_goals)
    away_stats = TeamStats(goals=away_goals)
    res = MatchResult(
        home=home, away=away, home_stats=home_stats, away_stats=away_stats
    )

    for minute in _goal_minutes(home_goals):
        scorer = _pick_scorer(home)
        assist = _pick_assist(home, scorer)
        res.events.append(PlayerEvent(minute, EventType.GOAL, scorer, assist))

    for minute in _goal_minutes(away_goals):
        scorer = _pick_scorer(away)
        assist = _pick_assist(away, scorer)
        res.events.append(PlayerEvent(minute, EventType.GOAL, scorer, assist))

    home_stats.shots_on_target = max(
        home_goals, int(round(random.uniform(1.2, 2.8) * max(1, home_goals)))
    )
    away_stats.shots_on_target = max(
        away_goals, int(round(random.uniform(1.2, 2.8) * max(1, away_goals)))
    )

    h_poss = int(50 + (h_strength - a_strength) * 8 + random.randint(-5, 5))
    home_stats.possession_pct = max(30, min(70, h_poss))
    away_stats.possession_pct = 100 - home_stats.possession_pct

    base_cards = max(0, int(round(random.gauss(2.0 + (ref.hard - 5) * 0.4, 1.0))))
    for _ in range(base_cards):
        minute = random.randint(1, 90)
        side_home = random.random() < 0.5
        p = random.choice(home.players if side_home else away.players)
        etype = EventType.RED if random.randint(1, 6) == 1 else EventType.YELLOW
        res.events.append(PlayerEvent(minute, etype, p))
        if side_home:
            home_stats.red_cards += int(etype is EventType.RED)
            home_stats.yellow_cards += int(etype is EventType.YELLOW)
        else:
            away_stats.red_cards += int(etype is EventType.RED)
            away_stats.yellow_cards += int(etype is EventType.YELLOW)

    res.events.sort(key=lambda e: e.minute)
    return res
