from __future__ import annotations

import csv
import random
from dataclasses import asdict
from pathlib import Path
from typing import List, Sequence

from .club import Club
from .league import Division, League, LeagueRules
from .player import Player, Position, Trait

# Rotmapp (två nivåer upp från denna fil)
ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "names"


def _load_csv_column(path: Path, column: str) -> List[str]:
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [row[column].strip() for row in reader if row.get(column, "").strip()]


# Ladda namnlistor (tom lista om fil saknas)
FIRST_NAMES = (
    _load_csv_column(DATA / "first_names.csv", "first_name")
    if (DATA / "first_names.csv").exists()
    else []
)
LAST_NAMES = (
    _load_csv_column(DATA / "last_names.csv", "last_name")
    if (DATA / "last_names.csv").exists()
    else []
)
TEAM_NAMES = (
    _load_csv_column(DATA / "team_names.csv", "team_name")
    if (DATA / "team_names.csv").exists()
    else []
)


def _rand_age() -> int:
    # 18–28 vanligast, 16–34 normalt, 35+ ovanligt
    r = random.random()
    if r < 0.65:
        return random.randint(18, 28)
    if r < 0.90:
        return random.randint(16, 34)
    return random.randint(35, 40)


def _rand_skill_open() -> int:
    # Medelvärde 5, spridning runt 1.6
    val = int(round(random.gauss(5, 1.6)))
    return max(1, min(30, val))


def _rand_traits() -> List[Trait]:
    traits: List[Trait] = []
    pool: Sequence[Trait] = list(Trait)
    k = random.choices([0, 1, 2, 3], weights=[40, 35, 20, 5], k=1)[0]
    for _ in range(k):
        t = random.choice(pool)
        if t not in traits:
            traits.append(t)
    return traits


def _biased_shirt_number(position: Position, taken: set[int]) -> int:
    preferred_fw = [7, 8, 9, 10, 11]
    if position is Position.FW and random.random() < 0.7:
        for n in preferred_fw:
            if n not in taken:
                taken.add(n)
                return n
    # annars 1–99, unikt
    while True:
        n = random.randint(1, 99)
        if n not in taken:
            taken.add(n)
            return n


def _gen_player(next_id: int, position: Position, taken_numbers: set[int]) -> Player:
    first = random.choice(FIRST_NAMES) if FIRST_NAMES else f"First{next_id}"
    last = random.choice(LAST_NAMES) if LAST_NAMES else f"Last{next_id}"
    return Player(
        id=next_id,
        first_name=first,
        last_name=last,
        age=_rand_age(),
        position=position,
        number=_biased_shirt_number(position, taken_numbers),
        skill_open=_rand_skill_open(),
        skill_xp=random.randint(1, 99),
        form_now=random.randint(8, 12),
        form_season=10,
        traits=_rand_traits(),
    )


def generate_club(name: str, *, squad_size: int = 21, start_id: int = 1) -> Club:
    # Fördelning för 21 spelare
    layout = [
        (Position.GK, 2),
        (Position.DF, 7),
        (Position.MF, 7),
        (Position.FW, 5),
    ]
    players: List[Player] = []
    taken_numbers: set[int] = set()
    nid = start_id
    for pos, count in layout:
        for _ in range(count):
            players.append(_gen_player(nid, pos, taken_numbers))
            nid += 1
    return Club(name=name, players=players, cash_sek=0)


def _unique_team_names(n: int) -> List[str]:
    if not TEAM_NAMES:
        return [f"Club {i+1}" for i in range(n)]
    base = TEAM_NAMES.copy()
    out: List[str] = []
    i = 0
    while len(out) < n:
        name = base[i % len(base)]
        suffix = i // len(base)
        out.append(name if suffix == 0 else f"{name} {suffix+1}")
        i += 1
    return out


def generate_league(name: str, rules: LeagueRules) -> League:
    league = League(name=name, rules=rules, divisions=[])
    for lvl in range(1, rules.levels + 1):
        div_name = f"Division {lvl}"
        clubs: List[Club] = []
        for team_name in _unique_team_names(rules.teams_per_div):
            clubs.append(generate_club(team_name))
        league.divisions.append(Division(name=div_name, level=lvl, clubs=clubs))
    return league


def to_preview_dict(league: League) -> dict:
    # Enkel struktur för konsolprint/tests
    return {
        "league": league.name,
        "levels": len(league.divisions),
        "teams_per_div": [len(d.clubs) for d in league.divisions],
        "first_team": asdict(league.divisions[0].clubs[0]) if league.divisions else {},
    }
