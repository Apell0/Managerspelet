from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .match import EventType, MatchResult, PlayerEvent
from .player import Player, Position

# -------- Spelar- & lagstatistik (per säsong) --------


@dataclass(slots=True)
class PlayerSeasonStats:
    player_id: int
    club_name: str
    appearances: int = 0
    minutes: int = 0
    goals: int = 0
    assists: int = 0
    shots: int = 0
    shots_on: int = 0
    offsides: int = 0
    yellows: int = 0
    reds: int = 0
    penalties_scored: int = 0
    penalties_missed: int = 0
    injuries: int = 0
    rating_sum: float = 0.0
    rating_count: int = 0
    clean_sheets: int = 0

    @property
    def rating_avg(self) -> float:
        return (self.rating_sum / self.rating_count) if self.rating_count else 0.0

    @property
    def points(self) -> int:
        return self.goals + self.assists


@dataclass(slots=True)
class PlayerCareerStats(PlayerSeasonStats):
    seasons: int = 0


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
    # extra lagvärden
    shots: int = 0
    shots_on: int = 0
    corners: int = 0
    offsides: int = 0
    fouls: int = 0
    saves: int = 0
    shots_against: int = 0
    shots_on_against: int = 0
    possession_for: int = 0
    possession_against: int = 0

    @property
    def points(self) -> int:
        return self.wins * 3 + self.draws

    @property
    def possession_avg(self) -> float:
        return (self.possession_for / self.played) if self.played else 0.0


# -------- Matchlogg (serialiserbar) --------


@dataclass(slots=True)
class ClubCareerStats(ClubSeasonStats):
    seasons: int = 0


@dataclass(slots=True)
class MatchRecord:
    competition: str  # "league" | "cup"
    round: int  # ligaomgång eller cuprunda-index (1..)
    home: str
    away: str
    home_goals: int
    away_goals: int
    events: List[dict]  # [{type, minute, player_id, assist_id}]
    ratings: Dict[int, float] = field(default_factory=dict)  # player.id -> rating
    lineup_home: List[int] = field(default_factory=list)
    lineup_away: List[int] = field(default_factory=list)
    bench_home: List[int] = field(default_factory=list)
    bench_away: List[int] = field(default_factory=list)
    formation_home: str | None = None
    formation_away: str | None = None
    minutes_home: Dict[int, int] = field(default_factory=dict)
    minutes_away: Dict[int, int] = field(default_factory=dict)
    stats: Dict[str, Any] = field(default_factory=dict)
    ratings_by_unit: Dict[str, Dict[str, int]] = field(default_factory=dict)
    tactic_report: Dict[str, Any] = field(default_factory=dict)
    awards: Dict[str, Any] = field(default_factory=dict)
    referee: Dict[str, Any] = field(default_factory=dict)
    halftime_home: int = 0
    halftime_away: int = 0
    dark_arts_home: bool = False
    dark_arts_away: bool = False


# -------- Hjälpare --------


def _ensure_ps(
    stats: Dict[int, PlayerSeasonStats], p: Player, club_name: str
) -> PlayerSeasonStats:
    if p.id not in stats:
        stats[p.id] = PlayerSeasonStats(player_id=p.id, club_name=club_name)
    return stats[p.id]


def _ensure_pc(
    stats: Optional[Dict[int, PlayerCareerStats]],
    p: Player,
    club_name: str,
) -> Optional[PlayerCareerStats]:
    if stats is None:
        return None
    obj = stats.get(p.id)
    if obj is None:
        obj = PlayerCareerStats(player_id=p.id, club_name=club_name)
        stats[p.id] = obj
    else:
        obj.club_name = club_name
    return obj


def _ensure_cs(stats: Dict[str, ClubSeasonStats], club_name: str) -> ClubSeasonStats:
    if club_name not in stats:
        stats[club_name] = ClubSeasonStats(club_name=club_name)
    return stats[club_name]


def _ensure_cc(
    stats: Optional[Dict[str, ClubCareerStats]],
    club_name: str,
) -> Optional[ClubCareerStats]:
    if stats is None:
        return None
    obj = stats.get(club_name)
    if obj is None:
        obj = ClubCareerStats(club_name=club_name)
        stats[club_name] = obj
    return obj


def _count_events(events: List[PlayerEvent], pred) -> int:
    return sum(1 for ev in events if pred(ev))


# -------- Uppdatera stats från en match --------


def update_stats_from_result(
    result: MatchResult,
    *,
    competition: str,  # "league" | "cup"
    round_no: int,
    player_stats: Dict[int, PlayerSeasonStats],
    club_stats: Dict[str, ClubSeasonStats],
    player_career_stats: Optional[Dict[int, PlayerCareerStats]] = None,
    club_career_stats: Optional[Dict[str, ClubCareerStats]] = None,
) -> MatchRecord:
    hname = result.home.name
    aname = result.away.name

    # Lagstatistik
    hcs = _ensure_cs(club_stats, hname)
    acs = _ensure_cs(club_stats, aname)
    hcc = _ensure_cc(club_career_stats, hname)
    acc = _ensure_cc(club_career_stats, aname)

    for cs, cc, gf, ga in (
        (hcs, hcc, result.home_stats.goals, result.away_stats.goals),
        (acs, acc, result.away_stats.goals, result.home_stats.goals),
    ):
        for target in filter(None, (cs, cc)):
            target.played += 1
            target.goals_for += gf
            target.goals_against += ga

    # seger/oavgjort/förlust (kräver separat logik för hemma/borta)
    if result.home_stats.goals > result.away_stats.goals:
        for target in filter(None, (hcs, hcc)):
            target.wins += 1
        for target in filter(None, (acs, acc)):
            target.losses += 1
    elif result.home_stats.goals < result.away_stats.goals:
        for target in filter(None, (acs, acc)):
            target.wins += 1
        for target in filter(None, (hcs, hcc)):
            target.losses += 1
    else:
        for target in filter(None, (hcs, hcc)):
            target.draws += 1
        for target in filter(None, (acs, acc)):
            target.draws += 1

    # lagaggregat från matchstats
    club_pairs = (
        (hcs, hcc, result.home_stats, result.away_stats),
        (acs, acc, result.away_stats, result.home_stats),
    )
    for cs, cc, ts, opp in club_pairs:
        for target in filter(None, (cs, cc)):
            target.shots += ts.shots
            target.shots_on += ts.shots_on
            target.corners += ts.corners
            target.offsides += ts.offsides
            target.fouls += ts.fouls
            target.saves += ts.saves
            target.shots_against += opp.shots
            target.shots_on_against += opp.shots_on
            target.possession_for += ts.possession_pct
            target.possession_against += opp.possession_pct
    if result.away_stats.goals == 0:
        for target in filter(None, (hcs, hcc)):
            target.clean_sheets += 1
    if result.home_stats.goals == 0:
        for target in filter(None, (acs, acc)):
            target.clean_sheets += 1

    home_roster = {getattr(p, "id", None): p for p in result.home.players}
    away_roster = {getattr(p, "id", None): p for p in result.away.players}

    home_minutes = result.home_minutes or {}
    if not home_minutes:
        fallback_home = list(home_roster.values())[:11]
        home_minutes = {getattr(p, "id", 0): 90 for p in fallback_home if getattr(p, "id", None) is not None}

    away_minutes = result.away_minutes or {}
    if not away_minutes:
        fallback_away = list(away_roster.values())[:11]
        away_minutes = {getattr(p, "id", 0): 90 for p in fallback_away if getattr(p, "id", None) is not None}

    home_ids = set(home_minutes.keys())
    away_ids = set(away_minutes.keys())

    for pid, minutes in home_minutes.items():
        player = home_roster.get(pid)
        if not player or minutes <= 0:
            continue
        ps = _ensure_ps(player_stats, player, hname)
        ps.appearances += 1
        ps.minutes += int(minutes)
        pc = _ensure_pc(player_career_stats, player, hname)
        if pc is not None:
            pc.appearances += 1
            pc.minutes += int(minutes)

    for pid, minutes in away_minutes.items():
        player = away_roster.get(pid)
        if not player or minutes <= 0:
            continue
        ps = _ensure_ps(player_stats, player, aname)
        ps.appearances += 1
        ps.minutes += int(minutes)
        pc = _ensure_pc(player_career_stats, player, aname)
        if pc is not None:
            pc.appearances += 1
            pc.minutes += int(minutes)

    def _apply_clean_sheet(
        roster: Dict[int, Player], minutes_map: Dict[int, int], conceded: int, club_name: str
    ) -> None:
        if conceded != 0:
            return
        for pid, player in roster.items():
            if getattr(player, "position", None) == Position.GK:
                minutes_played = int(minutes_map.get(pid, 0))
                if minutes_played > 0:
                    ps = _ensure_ps(player_stats, player, club_name)
                    ps.clean_sheets += 1
                    pc = _ensure_pc(player_career_stats, player, club_name)
                    if pc is not None:
                        pc.clean_sheets += 1

    _apply_clean_sheet(home_roster, home_minutes, result.away_stats.goals, hname)
    _apply_clean_sheet(away_roster, away_minutes, result.home_stats.goals, aname)

    # Hjälpare för klubbnamn utifrån elvorna i resultatet
    def _club_of(player: Player) -> str:
        pid = getattr(player, "id", None)
        if pid in home_ids:
            return hname
        if pid in away_ids:
            return aname
        return hname if player in result.home.players else aname

    # spelarevents
    for ev in result.events:
        p = ev.player
        if ev.event is EventType.GOAL and p is not None:
            club = _club_of(p)
            ps = _ensure_ps(player_stats, p, club)
            ps.goals += 1
            pc = _ensure_pc(player_career_stats, p, club)
            if pc is not None:
                pc.goals += 1
            if ev.assist_by is not None:
                assist_club = _club_of(ev.assist_by)
                aps = _ensure_ps(player_stats, ev.assist_by, assist_club)
                aps.assists += 1
                apc = _ensure_pc(player_career_stats, ev.assist_by, assist_club)
                if apc is not None:
                    apc.assists += 1
        elif ev.event is EventType.SHOT_ON and p is not None:
            club = _club_of(p)
            s = _ensure_ps(player_stats, p, club)
            s.shots += 1
            s.shots_on += 1
            sc = _ensure_pc(player_career_stats, p, club)
            if sc is not None:
                sc.shots += 1
                sc.shots_on += 1
        elif ev.event is EventType.SHOT_OFF and p is not None:
            club = _club_of(p)
            s = _ensure_ps(player_stats, p, club)
            s.shots += 1
            sc = _ensure_pc(player_career_stats, p, club)
            if sc is not None:
                sc.shots += 1
        elif ev.event is EventType.PENALTY_SCORED and p is not None:
            club = _club_of(p)
            ps = _ensure_ps(player_stats, p, club)
            ps.penalties_scored += 1
            pc = _ensure_pc(player_career_stats, p, club)
            if pc is not None:
                pc.penalties_scored += 1
        elif ev.event is EventType.PENALTY_MISSED and p is not None:
            club = _club_of(p)
            ps = _ensure_ps(player_stats, p, club)
            ps.penalties_missed += 1
            pc = _ensure_pc(player_career_stats, p, club)
            if pc is not None:
                pc.penalties_missed += 1
        elif ev.event is EventType.OFFSIDE and p is not None:
            club = _club_of(p)
            ps = _ensure_ps(player_stats, p, club)
            ps.offsides += 1
            pc = _ensure_pc(player_career_stats, p, club)
            if pc is not None:
                pc.offsides += 1
        elif ev.event is EventType.YELLOW and p is not None:
            club = _club_of(p)
            ps = _ensure_ps(player_stats, p, club)
            ps.yellows += 1
            pc = _ensure_pc(player_career_stats, p, club)
            if pc is not None:
                pc.yellows += 1
        elif ev.event is EventType.RED and p is not None:
            club = _club_of(p)
            ps = _ensure_ps(player_stats, p, club)
            ps.reds += 1
            pc = _ensure_pc(player_career_stats, p, club)
            if pc is not None:
                pc.reds += 1
        elif ev.event is EventType.INJURY and p is not None:
            club = _club_of(p)
            ps = _ensure_ps(player_stats, p, club)
            ps.injuries += 1
            pc = _ensure_pc(player_career_stats, p, club)
            if pc is not None:
                pc.injuries += 1

    # betyg → summera
    for p in result.home.players + result.away.players:
        r = result.ratings.get(p.id, 0.0)
        if r > 0:
            club = _club_of(p)
            ps = _ensure_ps(player_stats, p, club)
            ps.rating_sum += r
            ps.rating_count += 1
            pc = _ensure_pc(player_career_stats, p, club)
            if pc is not None:
                pc.rating_sum += r
                pc.rating_count += 1

    # MatchRecord (serialiserbar)
    rec_events: List[dict] = []
    for ev in result.events:
        rec_events.append(
            {
                "type": ev.event.name,
                "minute": getattr(ev, "minute", None),
                "player_id": (ev.player.id if ev.player else None),
                "assist_id": (
                    ev.assist_by.id if getattr(ev, "assist_by", None) else None
                ),
                "note": getattr(ev, "note", None),
            }
        )

    lineup_home = [getattr(p, "id", None) for p in getattr(result, "home_lineup", [])]
    lineup_away = [getattr(p, "id", None) for p in getattr(result, "away_lineup", [])]
    bench_home = [getattr(p, "id", None) for p in getattr(result, "home_bench", [])]
    bench_away = [getattr(p, "id", None) for p in getattr(result, "away_bench", [])]

    tactic_snapshot = getattr(result, "tactic_snapshot", {}) or {}
    stats_extra = getattr(result, "stats_extra", {}) or {}
    ratings_by_unit = getattr(result, "ratings_by_unit", {}) or {}
    awards = getattr(result, "awards", {}) or {}

    referee = getattr(result, "referee", None)
    referee_data: Dict[str, Any] = {}
    if referee is not None:
        skill = int(getattr(referee, "skill", 0) or 0)
        hardness = int(getattr(referee, "hardness", 0) or 0)
        grade = f"S{max(1, min(10, skill))} H{max(1, min(10, hardness))}"
        referee_data = {
            "name": getattr(referee, "name", None),
            "skill": skill,
            "hardness": hardness,
            "grade": grade,
        }

    return MatchRecord(
        competition=competition,
        round=round_no,
        home=hname,
        away=aname,
        home_goals=result.home_stats.goals,
        away_goals=result.away_stats.goals,
        events=rec_events,
        ratings=result.ratings.copy(),
        lineup_home=[pid for pid in lineup_home if pid is not None],
        lineup_away=[pid for pid in lineup_away if pid is not None],
        bench_home=[pid for pid in bench_home if pid is not None],
        bench_away=[pid for pid in bench_away if pid is not None],
        formation_home=(
            tactic_snapshot.get("home", {}).get("formation")
            if tactic_snapshot
            else None
        ),
        formation_away=(
            tactic_snapshot.get("away", {}).get("formation")
            if tactic_snapshot
            else None
        ),
        minutes_home={pid: int(mins) for pid, mins in result.home_minutes.items()},
        minutes_away={pid: int(mins) for pid, mins in result.away_minutes.items()},
        stats=stats_extra,
        ratings_by_unit=ratings_by_unit,
        tactic_report=tactic_snapshot,
        awards=awards,
        referee=referee_data,
        halftime_home=int(getattr(result, "home_ht_goals", 0) or 0),
        halftime_away=int(getattr(result, "away_ht_goals", 0) or 0),
        dark_arts_home=bool(getattr(result, "home_dark_arts", False)),
        dark_arts_away=bool(getattr(result, "away_dark_arts", False)),
    )
