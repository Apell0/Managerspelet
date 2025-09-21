from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, List, Tuple

from .club import Club
from .match import EventType, MatchResult, PlayerEvent
from .player import Player, Position
from .ratings import player_match_rating

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
    events: List[PlayerEvent],
    player: Player,
    *,
    team_goals_for: int,
    team_goals_against: int,
    team_won: bool,
    draw: bool,
    minutes: int = 90,
) -> float:
    """
    Beräkna ett enkelt matchbetyg (0–10-ish) av:
    - Basrating från speltid (minuter)
    - Viktning med spelarens skicklighet (1–30)
    - Händelser (mål/assist/kort)
    - Liten bonus för vinst / oavgjort
    - Positionsbonus (clean sheet för GK/DF, insläppta många mål drar ner GK/DF)
    - Liten slumpvariation (dagsform)
    """

    # 1) Bas från speltid (6.0 vid 90 min, lite lägre vid färre)
    played = max(0, min(90, minutes))
    base = 6.0 * (played / 90.0) ** 0.7

    # 2) Skicklighet väger (kring ±0.4 på basen)
    #   5 ≈ normal i din generator → ~1.0, 30 → +0.4, 1 → ca -0.06
    skill_norm = (player.skill_open - 5) / 25.0
    base *= 1.0 + 0.4 * skill_norm

    rating = base

    # 3) Händelser
    #   Målbonus beroende på position (FW mest, sedan MF/DF/GK)
    goals = sum(
        1 for ev in events if ev.event is EventType.GOAL and ev.player is player
    )
    if player.position is Position.FW:
        rating += 1.0 * goals
    elif player.position is Position.MF:
        rating += 0.9 * goals
    elif player.position is Position.DF:
        rating += 0.7 * goals
    else:  # GK
        rating += 0.6 * goals

    # Assist
    assists = sum(
        1 for ev in events if ev.event is EventType.GOAL and ev.assist_by is player
    )
    rating += 0.6 * assists

    # Kort
    yellows = sum(
        1 for ev in events if ev.event is EventType.YELLOW and ev.player is player
    )
    reds = sum(1 for ev in events if ev.event is EventType.RED and ev.player is player)
    rating += -0.4 * yellows + -2.0 * reds

    # 4) Lagresultat
    if team_won:
        rating += 0.3
    elif draw:
        rating += 0.1

    # 5) Positionsberoende försvarsbonus / avdrag
    if player.position in (Position.GK, Position.DF):
        if team_goals_against == 0:
            rating += 0.5
        elif team_goals_against >= 3:
            rating -= 0.5

    # 6) Dagsform (liten)
    rating += random.gauss(0.0, 0.4)

    # Klipp rimligt intervall
    return max(3.0, min(10.0, rating))


def best_xi_442(
    results: List[MatchResult],
) -> Dict[Position, List[Tuple[Player, float]]]:
    """
    Väljer 1–4–4–2 baserat på samma rating som används i matchresultaten.
    Använder res.ratings när de finns; annars beräknas on-the-fly.
    """
    candidates: Dict[Position, List[Tuple[Player, float]]] = {
        Position.GK: [],
        Position.DF: [],
        Position.MF: [],
        Position.FW: [],
    }

    for res in results:
        # Om simuleringen redan räknat ut betyg: använd dem
        if res.ratings:
            for p in res.home.players:
                candidates[p.position].append((p, res.ratings.get(p.id, 6.0)))
            for p in res.away.players:
                candidates[p.position].append((p, res.ratings.get(p.id, 6.0)))
        else:
            # fallback – beräkna direkt (90 min antas)
            for p in res.home.players + res.away.players:
                r = player_match_rating(res, p, minutes=90)
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
