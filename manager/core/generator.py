from __future__ import annotations

import csv
import random
from dataclasses import asdict
from pathlib import Path
from typing import List, Sequence

from .club import Club
from .economy import calculate_player_value
from .league import Division, League, LeagueRules
from .player import Player, Position, Trait

# Rotmapp (två nivåer upp från denna fil)
ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "names"
GRAPHICS_ROOT = ROOT / "data" / "graphics"
EMBLEM_DIR = GRAPHICS_ROOT / "emblems"
KIT_DIR = GRAPHICS_ROOT / "kits"


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


def _list_asset_files(path: Path) -> List[Path]:
    if not path.exists() or not path.is_dir():
        return []
    return sorted(p for p in path.iterdir() if p.is_file())


EMBLEM_FILES = _list_asset_files(EMBLEM_DIR)
KIT_FILES = _list_asset_files(KIT_DIR)


def _pick_asset(files: List[Path], index: int) -> str | None:
    if not files:
        return None
    asset = files[index % len(files)]
    try:
        return str(asset.relative_to(ROOT))
    except ValueError:
        return str(asset)


def _rand_age() -> int:
    """Returnera en spelålder mellan 16 och 50 med fallande sannolikhet."""

    r = random.random()
    if r < 0.55:
        return random.randint(18, 27)
    if r < 0.80:
        return random.randint(16, 32)
    if r < 0.93:
        return random.randint(33, 37)
    if r < 0.985:
        return random.randint(38, 43)
    return random.randint(44, 50)


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
    hidden = random.randint(1, 99)
    player = Player(
        id=next_id,
        first_name=first,
        last_name=last,
        age=_rand_age(),
        position=position,
        number=_biased_shirt_number(position, taken_numbers),
        skill_open=_rand_skill_open(),
        skill_hidden=hidden,
        skill_xp=hidden,
        form_now=random.randint(8, 12),
        form_season=10,
        traits=_rand_traits(),
    )
    player.value_sek = calculate_player_value(player)
    return player


def generate_club(
    name: str,
    *,
    squad_size: int = 21,
    start_id: int = 1,
    emblem: str | None = None,
    kit: str | None = None,
    club_id: str | None = None,
) -> Club:
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
    club = Club(name=name, players=players, cash_sek=0)
    club.club_id = club_id
    if emblem is not None:
        club.emblem_path = emblem
    if kit is not None:
        club.kit_path = kit
    club.stadium_name = f"{name} Arena"
    club.manager_name = "AI Coach"
    club.colors = {"home": None, "away": None}
    return club


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


def _division_name(level: int, index: int, total_at_level: int) -> str:
    if total_at_level <= 1:
        return f"Division {level}"
    # A, B, C ... efter nivånumret. Efter Z börjar vi numrera.
    if index < 26:
        suffix = chr(ord("A") + index)
        return f"Division {level}{suffix}"
    return f"Division {level}-{index + 1}"


def generate_league(name: str, rules: LeagueRules) -> League:
    league = League(name=name, rules=rules, divisions=[])
    layout = list(getattr(rules, "divisions_per_level", []) or [])
    if len(layout) != rules.levels:
        # säkerhetsnät om äldre regler saknar layout → beräkna via helpern igen
        from .league import _normalise_division_layout

        layout = _normalise_division_layout(layout, rules.levels, rules.format)

    total_divisions = sum(layout)
    total_clubs = total_divisions * rules.teams_per_div
    team_names = _unique_team_names(total_clubs)
    name_index = 0

    asset_index = 0
    club_counter = 1
    for level, count in enumerate(layout, start=1):
        for div_idx in range(count):
            div_name = _division_name(level, div_idx, count)
            clubs: List[Club] = []
            for _ in range(rules.teams_per_div):
                club_name = team_names[name_index]
                name_index += 1
                clubs.append(
                    generate_club(
                        club_name,
                        emblem=_pick_asset(EMBLEM_FILES, asset_index),
                        kit=_pick_asset(KIT_FILES, asset_index),
                        club_id=f"t-{club_counter:04d}",
                    )
                )
                clubs[-1].club_id = clubs[-1].club_id or f"t-{club_counter:04d}"
                asset_index += 1
                club_counter += 1
            league.divisions.append(Division(name=div_name, level=level, clubs=clubs))
    return league


def to_preview_dict(league: League) -> dict:
    # Enkel struktur för konsolprint/tests
    return {
        "league": league.name,
        "levels": len(league.divisions),
        "teams_per_div": [len(d.clubs) for d in league.divisions],
        "first_team": asdict(league.divisions[0].clubs[0]) if league.divisions else {},
    }
