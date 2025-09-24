from __future__ import annotations

from dataclasses import dataclass, fields
from typing import List, Optional, Sequence

from manager.core.club import Club
from manager.core.fixtures import Match
from manager.core.history import SeasonRecord
from manager.core.player import Player, Trait
from manager.core.state import GameState
from manager.core.stats import (
    ClubCareerStats,
    ClubSeasonStats,
    PlayerCareerStats,
    PlayerSeasonStats,
)

BAR_FILLED = "█"
BAR_EMPTY = "·"


@dataclass(slots=True)
class FixturePreview:
    round: int
    opponent: str
    home: bool
    competition: str


@dataclass(slots=True)
class MatchSummary:
    competition: str
    round: int
    opponent: str
    home: bool
    score: str


@dataclass(slots=True)
class PlayerRow:
    player_id: int
    number: int
    name: str
    position: str
    skill_open: int
    skill_bar: str
    form_now: int
    form_now_bar: str
    form_season: float
    form_season_bar: str
    traits: str


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def ascii_bar(value: float, maximum: float, width: int) -> str:
    if maximum <= 0:
        return BAR_EMPTY * width
    value = _clamp(value, 0, maximum)
    filled = int(round((value / maximum) * width))
    filled = _clamp(filled, 0, width)
    return BAR_FILLED * int(filled) + BAR_EMPTY * (width - int(filled))


def _division_for_club(gs: GameState, club: Club):
    for div in gs.league.divisions:
        if club in div.clubs:
            return div
    return None


def upcoming_fixtures(gs: GameState, club: Club, *, limit: int = 5) -> List[FixturePreview]:
    division = _division_for_club(gs, club)
    if not division:
        return []
    fixtures: Sequence[Match] = gs.fixtures_by_division.get(division.name, []) or []
    upcoming: List[FixturePreview] = []
    for match in fixtures:
        if match.round < gs.current_round:
            continue
        if match.home is club:
            opponent = match.away.name
            home = True
        elif match.away is club:
            opponent = match.home.name
            home = False
        else:
            continue
        upcoming.append(
            FixturePreview(
                round=match.round,
                opponent=opponent,
                home=home,
                competition="league",
            )
        )
        if len(upcoming) >= limit:
            break
    return upcoming


def recent_results(
    gs: GameState,
    club: Club,
    *,
    limit: int = 5,
) -> List[MatchSummary]:
    summaries: List[MatchSummary] = []
    for record in reversed(gs.match_log or []):
        if record.home == club.name:
            home = True
            opponent = record.away
        elif record.away == club.name:
            home = False
            opponent = record.home
        else:
            continue
        score = f"{record.home_goals}-{record.away_goals}"
        if not home:
            score = f"{record.away_goals}-{record.home_goals}"
        summaries.append(
            MatchSummary(
                competition=record.competition,
                round=int(record.round),
                opponent=opponent,
                home=home,
                score=score,
            )
        )
        if len(summaries) >= limit:
            break
    return summaries


def _friendly_trait_name(trait: Trait) -> str:
    name = trait.name.replace("_", " ")
    return name.capitalize()


def _player_name(player: Player) -> str:
    full = getattr(player, "full_name", "").strip()
    if full:
        return full
    return f"{player.first_name} {player.last_name}".strip() or f"Spelare {player.id}"


def squad_rows(club: Club) -> List[PlayerRow]:
    rows: List[PlayerRow] = []
    for player in sorted(club.players, key=lambda p: (p.position.value, p.number)):
        traits = ", ".join(_friendly_trait_name(t) for t in getattr(player, "traits", []) or [])
        rows.append(
            PlayerRow(
                player_id=int(getattr(player, "id", 0)),
                number=int(getattr(player, "number", 0)),
                name=_player_name(player),
                position=getattr(player.position, "name", ""),
                skill_open=int(getattr(player, "skill_open", 0)),
                skill_bar=ascii_bar(getattr(player, "skill_open", 0), 30, 30),
                form_now=int(getattr(player, "form_now", 0)),
                form_now_bar=ascii_bar(getattr(player, "form_now", 0), 20, 20),
                form_season=float(getattr(player, "form_season", 0.0)),
                form_season_bar=ascii_bar(getattr(player, "form_season", 0.0), 20, 20),
                traits=traits,
            )
        )
    return rows


def _player_stats_map(gs: GameState, scope: str) -> dict:
    if scope == "career":
        return getattr(gs, "player_career_stats", {}) or {}
    return getattr(gs, "player_stats", {}) or {}


def _club_stats_map(gs: GameState, scope: str) -> dict:
    if scope == "career":
        return getattr(gs, "club_career_stats", {}) or {}
    return getattr(gs, "club_stats", {}) or {}


def _coerce_player_stats(entry, scope: str):
    if isinstance(entry, (PlayerCareerStats, PlayerSeasonStats)):
        return entry
    if isinstance(entry, dict):
        data = dict(entry)
        data.pop("rating_avg", None)
        target_cls = PlayerCareerStats if scope == "career" else PlayerSeasonStats
        try:
            return target_cls(**data)
        except TypeError:
            allowed = {f.name for f in fields(target_cls)}
            filtered = {key: data[key] for key in data if key in allowed}
            try:
                return target_cls(**filtered)
            except Exception:
                if target_cls is PlayerCareerStats:
                    fallback_allowed = {f.name for f in fields(PlayerSeasonStats)}
                    filtered = {key: data[key] for key in data if key in fallback_allowed}
                    try:
                        return PlayerSeasonStats(**filtered)
                    except Exception:
                        return None
        except Exception:
            return None
    return None


def _coerce_club_stats(entry, scope: str):
    if isinstance(entry, (ClubCareerStats, ClubSeasonStats)):
        return entry
    if isinstance(entry, dict):
        data = dict(entry)
        data.pop("points", None)
        target_cls = ClubCareerStats if scope == "career" else ClubSeasonStats
        try:
            return target_cls(**data)
        except TypeError:
            allowed = {f.name for f in fields(target_cls)}
            filtered = {key: data[key] for key in data if key in allowed}
            try:
                return target_cls(**filtered)
            except Exception:
                if target_cls is ClubCareerStats:
                    fallback_allowed = {f.name for f in fields(ClubSeasonStats)}
                    filtered = {key: data[key] for key in data if key in fallback_allowed}
                    try:
                        return ClubSeasonStats(**filtered)
                    except Exception:
                        return None
        except Exception:
            return None
    return None


def club_stats(gs: GameState, club: Club, scope: str = "season") -> Optional[ClubSeasonStats]:
    stats_map = _club_stats_map(gs, scope)
    stats = stats_map.get(club.name)
    obj = _coerce_club_stats(stats, scope)
    return obj


def player_stats_for_club(
    gs: GameState, club: Club, scope: str = "season"
) -> List[PlayerSeasonStats]:
    data: List[PlayerSeasonStats] = []
    stats_map = _player_stats_map(gs, scope)
    for entry in stats_map.values():
        obj = _coerce_player_stats(entry, scope)
        if obj is None:
            continue
        if getattr(obj, "club_name", None) == club.name:
            data.append(obj)
    return data


def player_stats_for_player(
    gs: GameState, player_id: int, scope: str = "season"
) -> Optional[PlayerSeasonStats]:
    stats_map = _player_stats_map(gs, scope)
    entry = stats_map.get(player_id)
    return _coerce_player_stats(entry, scope)


def club_history(gs: GameState, club: Club) -> List[SeasonRecord]:
    history = getattr(gs, "history", None)
    if history is None:
        return []
    if hasattr(history, "all_for"):
        return history.all_for(club.name)
    # Fallback för snapshot dict
    records = history.get(club.name, []) if isinstance(history, dict) else []
    result: List[SeasonRecord] = []
    for rec in records:
        if isinstance(rec, SeasonRecord):
            result.append(rec)
        elif isinstance(rec, dict):
            try:
                result.append(SeasonRecord(**rec))
            except Exception:
                continue
    return result


def team_form_values(club: Club) -> tuple[float, float]:
    players = club.players or []
    if not players:
        return (0.0, 0.0)
    now = sum(float(getattr(p, "form_now", 0)) for p in players) / len(players)
    season = sum(float(getattr(p, "form_season", 0)) for p in players) / len(players)
    return now, season


def division_for_club(gs: GameState, club: Club):
    return _division_for_club(gs, club)
