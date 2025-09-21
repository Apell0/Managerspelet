from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .match import EventType, MatchResult, PlayerEvent
from .player import Player

# -------- Spelar- & lagstatistik (per säsong) --------


@dataclass(slots=True)
class PlayerSeasonStats:
    player_id: int
    club_name: str
    appearances: int = 0
    minutes: int = 0
    goals: int = 0
    assists: int = 0
    yellows: int = 0
    reds: int = 0
    rating_sum: float = 0.0
    rating_count: int = 0

    @property
    def rating_avg(self) -> float:
        return (self.rating_sum / self.rating_count) if self.rating_count else 0.0


@dataclass(slots=True)
class ClubSeasonStats:
    club_name: str
    played: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    goals_for: int = 0
    goals_against: int = 0
    clean_sheets: int = 0
    yellows: int = 0
    reds: int = 0

    @property
    def points(self) -> int:
        return self.wins * 3 + self.draws


# -------- Matchlogg (serialiserbar) --------


@dataclass(slots=True)
class MatchRecord:
    competition: str  # "league" | "cup"
    round: int  # ligaomgång eller cuprunda-index (1..)
    home: str  # klubbnamn
    away: str
    home_goals: int
    away_goals: int
    events: List[dict]  # [{type, minute, player_id, assist_id}]
    ratings: Dict[int, float] = field(default_factory=dict)  # player.id -> rating


# -------- Hjälpare --------


def _ensure_ps(
    stats: Dict[int, PlayerSeasonStats], p: Player, club_name: str
) -> PlayerSeasonStats:
    if p.id not in stats:
        stats[p.id] = PlayerSeasonStats(player_id=p.id, club_name=club_name)
    return stats[p.id]


def _ensure_cs(stats: Dict[str, ClubSeasonStats], club_name: str) -> ClubSeasonStats:
    if club_name not in stats:
        stats[club_name] = ClubSeasonStats(club_name=club_name)
    return stats[club_name]


def _count_events(events: List[PlayerEvent], pred) -> int:
    return sum(1 for ev in events if pred(ev))


def update_stats_from_result(
    result: MatchResult,
    *,
    competition: str,  # "league" | "cup"
    round_no: int,
    # ackumulerade säsongsstats att uppdatera:
    player_stats: Dict[int, PlayerSeasonStats],
    club_stats: Dict[str, ClubSeasonStats],
) -> MatchRecord:
    """Uppdaterar stat-ackumulatorer och returnerar en serialiserbar MatchRecord."""
    hname = result.home.name
    aname = result.away.name

    # Lagstatistik
    hcs = _ensure_cs(club_stats, hname)
    acs = _ensure_cs(club_stats, aname)

    hcs.played += 1
    acs.played += 1
    hcs.goals_for += result.home_stats.goals
    hcs.goals_against += result.away_stats.goals
    acs.goals_for += result.away_stats.goals
    acs.goals_against += result.home_stats.goals

    if result.home_stats.goals > result.away_stats.goals:
        hcs.wins += 1
        acs.losses += 1
    elif result.home_stats.goals < result.away_stats.goals:
        acs.wins += 1
        hcs.losses += 1
    else:
        hcs.draws += 1
        acs.draws += 1

    # Clean sheets + kort
    if result.away_stats.goals == 0:
        hcs.clean_sheets += 1
    if result.home_stats.goals == 0:
        acs.clean_sheets += 1

    h_yellows = _count_events(
        result.events,
        lambda e: e.event is EventType.YELLOW and e.player in result.home.players,
    )
    a_yellows = _count_events(
        result.events,
        lambda e: e.event is EventType.YELLOW and e.player in result.away.players,
    )
    h_reds = _count_events(
        result.events,
        lambda e: e.event is EventType.RED and e.player in result.home.players,
    )
    a_reds = _count_events(
        result.events,
        lambda e: e.event is EventType.RED and e.player in result.away.players,
    )
    hcs.yellows += h_yellows
    acs.yellows += a_yellows
    hcs.reds += h_reds
    acs.reds += a_reds

    # Spelarstatistik (vi antar 90 minuter tills byten finns)
    for p in result.home.players:
        ps = _ensure_ps(player_stats, p, hname)
        ps.appearances += 1
        ps.minutes += 90
    for p in result.away.players:
        ps = _ensure_ps(player_stats, p, aname)
        ps.appearances += 1
        ps.minutes += 90

    for ev in result.events:
        if ev.event is EventType.GOAL and ev.player is not None:
            _ensure_ps(player_stats, ev.player, ev.player.club.name).goals += 1
            if ev.assist_by is not None:
                _ensure_ps(
                    player_stats, ev.assist_by, ev.assist_by.club.name
                ).assists += 1
        elif ev.event is EventType.YELLOW and ev.player is not None:
            _ensure_ps(player_stats, ev.player, ev.player.club.name).yellows += 1
        elif ev.event is EventType.RED and ev.player is not None:
            _ensure_ps(player_stats, ev.player, ev.player.club.name).reds += 1

    # Betyg
    for p in result.home.players + result.away.players:
        r = result.ratings.get(p.id, 0.0)
        ps = _ensure_ps(player_stats, p, p.club.name)
        if r > 0:
            ps.rating_sum += r
            ps.rating_count += 1

    # MatchRecord (serialiserbar)
    rec_events = []
    for ev in result.events:
        rec_events.append(
            {
                "type": ev.event.name,
                "minute": getattr(ev, "minute", None),
                "player_id": (ev.player.id if ev.player else None),
                "assist_id": (
                    ev.assist_by.id if getattr(ev, "assist_by", None) else None
                ),
            }
        )

    return MatchRecord(
        competition=competition,
        round=round_no,
        home=hname,
        away=aname,
        home_goals=result.home_stats.goals,
        away_goals=result.away_stats.goals,
        events=rec_events,
        ratings=result.ratings.copy(),
    )
