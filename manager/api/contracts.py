from __future__ import annotations

from typing import Any, Dict, Iterable, List

from manager.core.club import Club
from manager.core.cup_state import build_cup_bracket, match_records_by_competition
from manager.core.history import SeasonRecord
from manager.core.state import GameState
from manager.core.stats import ClubSeasonStats, MatchRecord, PlayerSeasonStats
from manager.core.transfer import JuniorOffer, TransferListing

from .utils import ensure_colors, slugify


def _team_id(club: Club, fallback: str) -> str:
    club_id = getattr(club, "club_id", None)
    if club_id:
        return club_id
    return slugify(club.name, prefix="t") or fallback


def _player_id(player: Player) -> str:
    return f"p-{getattr(player, 'id', 0)}"


def _player_name(player: Player) -> str:
    full = getattr(player, "full_name", "").strip()
    if full:
        return full
    first = getattr(player, "first_name", "")
    last = getattr(player, "last_name", "")
    combo = f"{first} {last}".strip()
    return combo or f"#{getattr(player, 'number', 0)}"


def _player_traits(player: Player) -> List[str]:
    traits = []
    for trait in getattr(player, "traits", []) or []:
        name = getattr(trait, "name", str(trait))
        traits.append(name.lower())
    return traits


def _player_attrs(player: Player) -> Dict[str, int]:
    # Enkel projektion: skala 1-30 till 1-100 intervall
    base = int(getattr(player, "skill_open", 5))
    scale = max(1, min(30, base)) / 30.0
    rating = int(round(scale * 100))
    return {
        "pace": rating,
        "shot": rating,
        "pass": rating,
        "def": rating,
        "phy": rating,
    }


def _player_status(player: Player) -> Dict[str, bool]:
    # Skador/avstängningar saknas → default False
    return {"injured": False, "suspended": False}


def _club_summary(club: Club, division_id: str) -> Dict[str, Any]:
    colors = ensure_colors(getattr(club, "colors", None))
    return {
        "id": _team_id(club, slugify(club.name, prefix="t")),
        "name": club.name,
        "stadium": getattr(club, "stadium_name", f"{club.name} Arena"),
        "manager": getattr(club, "manager_name", "Bot Manager"),
        "division_id": division_id,
        "colors": colors,
        "emblem": getattr(club, "emblem_path", None),
    }


def _build_divisions(gs: GameState) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    divisions: List[Dict[str, Any]] = []
    teams: Dict[str, Dict[str, Any]] = {}
    existing_ids: set[str] = set()

    for idx, division in enumerate(gs.league.divisions, start=1):
        division_id = f"d-{division.level}-{idx:02d}"
        entry = {"id": division_id, "name": division.name, "teams": []}
        for club in division.clubs:
            team_summary = _club_summary(club, division_id)
            if team_summary["id"] in existing_ids:
                # säkerställ unikhet
                suffix = 1
                base_id = team_summary["id"]
                while f"{base_id}-{suffix}" in existing_ids:
                    suffix += 1
                team_summary["id"] = f"{base_id}-{suffix}"
            existing_ids.add(team_summary["id"])
            teams[club.name] = team_summary
            entry["teams"].append(team_summary["id"])
        divisions.append(entry)
    return divisions, teams


def _build_players(gs: GameState, club_index: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    players: List[Dict[str, Any]] = []
    for division in gs.league.divisions:
        for club in division.clubs:
            team_id = club_index[club.name]["id"]
            for player in club.players:
                players.append(
                    {
                        "id": _player_id(player),
                        "numeric_id": getattr(player, "id", 0),
                        "team_id": team_id,
                        "name": _player_name(player),
                        "age": getattr(player, "age", 0),
                        "pos": getattr(getattr(player, "position", None), "value", "MF"),
                        "ovr": int(getattr(player, "skill_open", 5) * 3),
                        "special": _player_traits(player),
                        "status": _player_status(player),
                        "number": getattr(player, "number", 0),
                        "form": getattr(player, "form_now", 10),
                        "season_form": getattr(player, "form_season", 10),
                        "portrait": getattr(player, "portrait", None),
                    }
                )
    return players


def _build_squads(gs: GameState, club_index: Dict[str, Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    squads: Dict[str, List[Dict[str, Any]]] = {}
    for division in gs.league.divisions:
        for club in division.clubs:
            team_id = club_index[club.name]["id"]
            rows: List[Dict[str, Any]] = []
            for player in club.players:
                rows.append(
                    {
                        "player_id": _player_id(player),
                        "number": getattr(player, "number", 0),
                        "position": getattr(getattr(player, "position", None), "value", "MF"),
                        "skill": getattr(player, "skill_open", 5),
                        "form": [getattr(player, "form_now", 10)],
                        "season_form": getattr(player, "form_season", 10),
                        "traits": _player_traits(player),
                        "status": _player_status(player),
                        "value_sek": getattr(player, "value_sek", 0),
                        "attrs": _player_attrs(player),
                    }
                )
            squads[team_id] = rows
    return squads


def _table_rows(gs: GameState, club_index: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    snapshot = getattr(gs, "table_snapshot", {}) or {}
    for club_name, stats in snapshot.items():
        team = club_index.get(club_name)
        if not team:
            continue
        rows.append(
            {
                "team_id": team["id"],
                "played": stats.get("mp", 0),
                "wins": stats.get("w", 0),
                "draws": stats.get("d", 0),
                "losses": stats.get("losses", 0),
                "goals_for": stats.get("gf", 0),
                "goals_against": stats.get("ga", 0),
                "points": stats.get("pts", 0),
            }
        )
    rows.sort(key=lambda r: (r["points"], r["goals_for"] - r["goals_against"], r["goals_for"]), reverse=True)
    return rows


def _build_standings(gs: GameState, club_index: Dict[str, Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    total = _table_rows(gs, club_index)
    return {"total": total, "home": [], "away": []}


def _match_id(prefix: str, round_no: int, home: str, away: str) -> str:
    return f"{prefix}-{round_no:02d}-{slugify(home)}-{slugify(away)}"


def _build_match_index(records: Iterable[MatchRecord], club_index: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    by_id: Dict[str, Dict[str, Any]] = {}
    for rec in records:
        match_id = _match_id("c" if rec.competition == "cup" else "l", rec.round, rec.home, rec.away)
        home_id = club_index.get(rec.home, {}).get("id")
        away_id = club_index.get(rec.away, {}).get("id")
        by_id[match_id] = {
            "id": match_id,
            "competition": rec.competition,
            "round": rec.round,
            "home_id": home_id,
            "away_id": away_id,
            "score": {"home": rec.home_goals, "away": rec.away_goals},
            "events": rec.events,
            "ratings": {f"p-{pid}": rating for pid, rating in rec.ratings.items()},
            "lineups": {
                "home": [f"p-{pid}" for pid in rec.lineup_home],
                "away": [f"p-{pid}" for pid in rec.lineup_away],
            },
            "bench": {
                "home": [f"p-{pid}" for pid in rec.bench_home],
                "away": [f"p-{pid}" for pid in rec.bench_away],
            },
        }
    return by_id


def _build_fixtures(gs: GameState, club_index: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    fixtures: List[Dict[str, Any]] = []

    for division in gs.league.divisions:
        comp_prefix = "l"
        for match in gs.fixtures_by_division.get(division.name, []):
            match_id = _match_id(comp_prefix, match.round, match.home.name, match.away.name)
            home_id = club_index.get(match.home.name, {}).get("id")
            away_id = club_index.get(match.away.name, {}).get("id")
            fixtures.append(
                {
                    "match_id": match_id,
                    "round": match.round,
                    "competition": "league",
                    "division": division.name,
                    "home_id": home_id,
                    "away_id": away_id,
                    "status": "scheduled",
                    "score": {"home": 0, "away": 0},
                    "date": None,
                }
            )
    return fixtures


def _merge_results_into_fixtures(
    fixtures: List[Dict[str, Any]],
    match_records: Dict[str, Dict[str, Any]],
) -> None:
    for match_id, data in match_records.items():
        for fixture in fixtures:
            if fixture["match_id"] == match_id:
                fixture["status"] = "played"
                fixture["score"] = data["score"]
                break


def _junior_offer_entry(offer: JuniorOffer) -> Dict[str, Any]:
    snapshot = offer.player_snapshot or {}
    return {
        "player_id": f"p-{snapshot.get('id', 0)}",
        "age": snapshot.get("age"),
        "ovr": snapshot.get("skill_open"),
        "price": offer.price_sek,
        "expires_season": offer.expires_season,
        "traits": snapshot.get("traits", []),
    }


def _transfer_listing_entry(listing: TransferListing) -> Dict[str, Any]:
    snap = listing.player_snapshot or {}
    return {
        "player_id": f"p-{snap.get('id', listing.player_id)}",
        "club_name": listing.club_name,
        "price": listing.price_sek,
        "age": snap.get("age"),
        "pos": snap.get("position"),
        "ovr": snap.get("skill_open"),
        "traits": snap.get("traits", []),
        "note": listing.note,
    }


def _build_stats_payload(gs: GameState, player_meta: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    player_stats = []
    for stat in (getattr(gs, "player_stats", {}) or {}).values():
        if not isinstance(stat, PlayerSeasonStats):
            continue
        player_stats.append(
            {
                "player_id": f"p-{stat.player_id}",
                "club": stat.club_name,
                "appearances": stat.appearances,
                "minutes": stat.minutes,
                "goals": stat.goals,
                "assists": stat.assists,
                "points": stat.points,
                "yellows": stat.yellows,
                "reds": stat.reds,
                "clean_sheets": getattr(stat, "clean_sheets", 0),
                "rating_avg": stat.rating_avg,
            }
        )
    club_stats = []
    for stat in (getattr(gs, "club_stats", {}) or {}).values():
        if not isinstance(stat, ClubSeasonStats):
            continue
        club_stats.append(
            {
                "club": stat.club_name,
                "played": stat.played,
                "wins": stat.wins,
                "draws": stat.draws,
                "losses": stat.losses,
                "goals_for": stat.goals_for,
                "goals_against": stat.goals_against,
                "clean_sheets": stat.clean_sheets,
                "yellows": stat.yellows,
                "reds": stat.reds,
                "possession_avg": stat.possession_avg,
            }
        )
    meta_lookup = player_meta

    def _top(scope: str, key: str) -> List[Dict[str, Any]]:
        sorted_players = sorted(player_stats, key=lambda row: row.get(key, 0), reverse=True)
        top = []
        for row in sorted_players[:10]:
            top.append({"player_id": row["player_id"], key: row.get(key, 0)})
        return top

    leaders = {
        "scorers": _top("players", "goals"),
        "assists": _top("players", "assists"),
        "points": _top("players", "points"),
        "clean_sheets": _top("players", "clean_sheets"),
    }

    buckets = {"GK": [], "DF": [], "MF": [], "FW": []}
    for row in player_stats:
        meta = meta_lookup.get(row["player_id"], {})
        pos = meta.get("pos", "MF")
        rating = row.get("rating_avg", 0.0)
        buckets.setdefault(pos, []).append((row["player_id"], rating))

    def _pick(position: str, count: int) -> List[str]:
        entries = sorted(buckets.get(position, []), key=lambda t: t[1], reverse=True)
        return [pid for pid, _ in entries[:count]]

    xi_players: List[str] = []
    xi_players.extend(_pick("GK", 1))
    xi_players.extend(_pick("DF", 4))
    xi_players.extend(_pick("MF", 4))
    xi_players.extend(_pick("FW", 2))
    captain = None
    if xi_players:
        captain = max(xi_players, key=lambda pid: next((row["rating_avg"] for row in player_stats if row["player_id"] == pid), 0.0))

    return {
        "players_current": player_stats,
        "players_all": list(player_stats),
        "club_current": club_stats,
        "club_all": list(club_stats),
        "leaders": leaders,
        "best_eleven": (
            [
                {
                    "round": None,
                    "team": xi_players,
                    "captain": captain,
                }
            ]
            if xi_players
            else []
        ),
    }


def _build_history(gs: GameState, club_index: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    history = {}
    if not getattr(gs, "history", None):
        return history
    snapshot = gs.history.snapshot()
    for club_name, records in (snapshot or {}).items():
        team = club_index.get(club_name)
        if not team:
            continue
        history[team["id"]] = {
            "seasons": [
                {
                    "year": getattr(rec, "season", None),
                    "league_position": getattr(rec, "league_position", None),
                    "cup_result": getattr(rec, "cup_result", None),
                }
                for rec in records
                if isinstance(rec, SeasonRecord) or isinstance(rec, dict)
            ],
        }
    return history


def build_contract(gs: GameState) -> Dict[str, Any]:
    gs.ensure_containers()
    divisions, teams = _build_divisions(gs)
    players = _build_players(gs, teams)
    player_meta = {player["id"]: player for player in players}
    squads = _build_squads(gs, teams)
    standings = _build_standings(gs, teams)
    fixtures = _build_fixtures(gs, teams)
    match_records = _build_match_index(getattr(gs, "match_log", []) or [], teams)
    _merge_results_into_fixtures(fixtures, match_records)

    youth_state = {
        club_name: [_junior_offer_entry(offer) for offer in offers]
        for club_name, offers in (getattr(gs, "junior_offers", {}) or {}).items()
    }

    transfer_market = [
        _transfer_listing_entry(listing) for listing in (getattr(gs, "transfer_list", []) or [])
    ]

    club_lookup = {
        club.name: club for division in gs.league.divisions for club in division.clubs
    }

    meta = dict(getattr(gs, "meta", {}) or {"version": "1.0"})
    available_team_ids = [summary["id"] for summary in teams.values()]
    user_team_id = meta.get("user_team_id")
    if not user_team_id or user_team_id not in available_team_ids:
        user_team_id = available_team_ids[0] if available_team_ids else None
        if user_team_id:
            meta["user_team_id"] = user_team_id

    def _club_from_team(team_id: str | None) -> Club | None:
        if not team_id:
            return None
        for name, summary in teams.items():
            if summary["id"] == team_id:
                return club_lookup.get(name)
        return None

    user_club = _club_from_team(user_team_id)
    balance = getattr(user_club, "cash_sek", None) if user_club else None

    contract = {
        "meta": meta,
        "options": dict(getattr(gs, "options", {}) or {}),
        "season": {
            "year": getattr(gs, "season", 1),
            "phase": getattr(gs, "season_phase", "in_progress"),
            "round_current": getattr(gs, "current_round", 1),
            "calendar_week": getattr(gs, "calendar_week", 1),
        },
        "league": {
            "name": getattr(gs.league, "name", ""),
            "structure": "pyramid" if getattr(gs.league.rules, "format", "rak") == "pyramid" else "single_division",
            "divisions": divisions,
        },
        "teams": list(teams.values()),
        "players": players,
        "standings": standings,
        "fixtures": fixtures,
        "matches": {"by_id": match_records},
        "squads": squads,
        "youth": {
            "offers": youth_state,
            "accepted": [],
            "preference": (getattr(gs, "options", {}) or {}).get("youth_preference", "MF"),
        },
        "transfers": {
            "market": transfer_market,
            "arrivals": [],
            "departures": [],
        },
        "stats": _build_stats_payload(gs, player_meta),
        "economy": {
            "team_id": user_team_id,
            "balance": balance,
            "ledger": list(getattr(gs, "economy_ledger", []) or []),
        },
        "mail": list(getattr(gs, "mailbox", []) or []),
        "cups": {
            "by_id": {
                "primary": {
                    "bracket": build_cup_bracket(getattr(gs, "cup_state", None), getattr(gs, "match_log", []) or []),
                    "fixtures": [],
                    "stats": {},
                }
            }
            if getattr(gs, "cup_state", None)
            else {}
        },
        "history": _build_history(gs, teams),
    }

    return contract
