from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from .club import Club
from .match import EventType, MatchResult, PlayerEvent
from .player import Player, Position

# ---------- LIGATABELL ----------


@dataclass(slots=True)
class TableRow:
    club: Club
    mp: int = 0
    w: int = 0
    d: int = 0
    losses: int = 0
    gf: int = 0
    ga: int = 0
    pts: int = 0

    @property
    def gd(self) -> int:
        return self.gf - self.ga


def _ensure_row(table: Dict[str, TableRow], club: Club) -> TableRow:
    key = club.name  # använder klubbnamn som nyckel
    if key not in table:
        table[key] = TableRow(club=club)
    return table[key]


def apply_result_to_table(table: Dict[str, TableRow], res: MatchResult) -> None:
    h = _ensure_row(table, res.home)
    a = _ensure_row(table, res.away)

    h.mp += 1
    a.mp += 1

    h.gf += res.home_stats.goals
    h.ga += res.away_stats.goals

    a.gf += res.away_stats.goals
    a.ga += res.home_stats.goals

    if res.home_stats.goals > res.away_stats.goals:
        h.w += 1
        a.losses += 1
        h.pts += 3
    elif res.home_stats.goals < res.away_stats.goals:
        a.w += 1
        h.losses += 1
        a.pts += 3
    else:
        h.d += 1
        a.d += 1
        h.pts += 1
        a.pts += 1


def sort_table(table: Dict[str, TableRow]) -> List[TableRow]:
    # Sortera på poäng, målskillnad, gjorda mål, klubbenamn (stabilt)
    return sorted(
        table.values(),
        key=lambda r: (r.pts, r.gd, r.gf, r.club.name),
        reverse=True,
    )


# ---------- BÄSTA ELVAN (1–4–4–2) ----------


def _rating_from_events(
    events: List[PlayerEvent], player: Player, team_won: bool, draw: bool
) -> float:
    score = 0.0
    for ev in events:
        if ev.player is player:
            if ev.event is EventType.GOAL:
                score += 3.0
            elif ev.event is EventType.YELLOW:
                score -= 1.0
            elif ev.event is EventType.RED:
                score -= 3.0
    for ev in events:
        if ev.event is EventType.GOAL and ev.assist_by is player:
            score += 2.0

    if team_won:
        score += 0.5
    elif draw:
        score += 0.2

    if player.position is Position.GK:
        score += 0.3
    elif player.position is Position.DF:
        score += 0.2

    return score


def best_xi_442(
    results: List[MatchResult],
) -> Dict[Position, List[Tuple[Player, float]]]:
    candidates: Dict[Position, List[Tuple[Player, float]]] = {
        Position.GK: [],
        Position.DF: [],
        Position.MF: [],
        Position.FW: [],
    }

    for res in results:
        home_won = res.home_stats.goals > res.away_stats.goals
        away_won = res.away_stats.goals > res.home_stats.goals
        draw = res.home_stats.goals == res.away_stats.goals

        for p in res.home.players:
            r = _rating_from_events(res.events, p, team_won=home_won, draw=draw)
            candidates[p.position].append((p, r))
        for p in res.away.players:
            r = _rating_from_events(res.events, p, team_won=away_won, draw=draw)
            candidates[p.position].append((p, r))

    def top_n(pos: Position, n: int) -> List[Tuple[Player, float]]:
        pool = sorted(
            candidates[pos], key=lambda t: (t[1], t[0].skill_open), reverse=True
        )
        out: List[Tuple[Player, float]] = []
        seen_ids = set()
        for pl, score in pool:
            if pl.id in seen_ids:
                continue
            out.append((pl, score))
            seen_ids.add(pl.id)
            if len(out) == n:
                break
        return out

    return {
        Position.GK: top_n(Position.GK, 1),
        Position.DF: top_n(Position.DF, 4),
        Position.MF: top_n(Position.MF, 4),
        Position.FW: top_n(Position.FW, 2),
    }
