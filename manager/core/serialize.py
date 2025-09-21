from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from . import stats as stats_mod  # Player/Club stats dataklasser (om finns)
from .club import Club
from .cup import CupRules
from .fixtures import Match
from .league import Division, League, LeagueRules
from .player import Player, Position, Trait
from .season import Aggressiveness, Tactic

# -------------------------------------------------------------------
# PLAYER
# -------------------------------------------------------------------


def player_to_dict(p: Player) -> Dict[str, Any]:
    return {
        "id": int(getattr(p, "id", 0)),
        "first_name": getattr(p, "first_name", ""),
        "last_name": getattr(p, "last_name", ""),
        "position": getattr(getattr(p, "position", None), "name", None)
        or getattr(p, "position", None)
        or "MF",
        "traits": [
            t.name if isinstance(t, Trait) else str(t)
            for t in (getattr(p, "traits", []) or [])
        ],
        "skill_open": int(getattr(p, "skill_open", 5)),
        "skill_hidden": int(getattr(p, "skill_hidden", 50)),
        "age": int(getattr(p, "age", 22)),
        # stöd för både number och jersey_number
        "number": int(getattr(p, "number", getattr(p, "jersey_number", 0))),
        "jersey_number": int(getattr(p, "jersey_number", getattr(p, "number", 0))),
        "value_sek": int(getattr(p, "value_sek", 0)),
        # formfält om de finns
        "form_now": int(getattr(p, "form_now", 10)),
        "form_season": int(getattr(p, "form_season", 10)),
    }


def player_from_dict(d: Dict[str, Any]) -> Player:
    # Position
    pos_raw = d.get("position", "MF")
    try:
        pos = Position[pos_raw] if isinstance(pos_raw, str) else Position(pos_raw)
    except Exception:
        pos = Position.MF

    # Traits
    traits_raw = d.get("traits", []) or []
    traits: List[Trait] = []
    for x in traits_raw:
        try:
            name = x if isinstance(x, str) else getattr(x, "name", str(x))
            traits.append(Trait[name])
        except Exception:
            pass  # okända traits ignoreras

    # Tröjnummer (stöd både 'number' och 'jersey_number')
    number = int(d.get("number", d.get("jersey_number", 0)))

    # Skapa spelaren med fält som __init__ säkert accepterar
    p = Player(
        id=int(d.get("id", 0)),
        first_name=d.get("first_name", ""),
        last_name=d.get("last_name", ""),
        position=pos,
        traits=traits,
        skill_open=int(d.get("skill_open", 5)),
        age=int(d.get("age", 22)),
        number=number,  # VIKTIGT: din Player kräver 'number'
    )

    # Sätt extra fält EFTER init – endast om de finns på Player
    if hasattr(p, "skill_hidden"):
        setattr(
            p,
            "skill_hidden",
            int(d.get("skill_hidden", getattr(p, "skill_hidden", 50))),
        )
    if hasattr(p, "jersey_number"):
        setattr(
            p,
            "jersey_number",
            int(d.get("jersey_number", getattr(p, "jersey_number", number))),
        )
    if hasattr(p, "value_sek"):
        setattr(p, "value_sek", int(d.get("value_sek", getattr(p, "value_sek", 0))))
    if hasattr(p, "form_now"):
        setattr(p, "form_now", int(d.get("form_now", getattr(p, "form_now", 10))))
    if hasattr(p, "form_season"):
        setattr(
            p, "form_season", int(d.get("form_season", getattr(p, "form_season", 10)))
        )

    return p


# -------------------------------------------------------------------
# CLUB
# -------------------------------------------------------------------


def club_to_dict(c: Club) -> Dict[str, Any]:
    return {
        "name": c.name,
        "cash_sek": int(getattr(c, "cash_sek", 0)),
        "players": [player_to_dict(p) for p in (getattr(c, "players", []) or [])],
        "tactic": {
            "attacking": bool(getattr(getattr(c, "tactic", None), "attacking", False)),
            "defending": bool(getattr(getattr(c, "tactic", None), "defending", False)),
            "offside_trap": bool(
                getattr(getattr(c, "tactic", None), "offside_trap", False)
            ),
            "tempo": float(getattr(getattr(c, "tactic", None), "tempo", 1.0)),
        },
        "aggressiveness": {
            "name": getattr(getattr(c, "aggressiveness", None), "name", "Medel"),
        },
    }


def club_from_dict(d: Dict[str, Any]) -> Club:
    c = Club(
        name=d["name"],
        players=[player_from_dict(x) for x in d.get("players", [])],
        cash_sek=int(d.get("cash_sek", 0)),
    )
    # tactic
    t = d.get("tactic", {}) or {}
    c.tactic = Tactic(
        attacking=bool(t.get("attacking", False)),
        defending=bool(t.get("defending", False)),
        offside_trap=bool(t.get("offside_trap", False)),
        tempo=float(t.get("tempo", 1.0)),
    )
    # aggressiveness
    a = d.get("aggressiveness", {}) or {}
    c.aggressiveness = Aggressiveness(a.get("name", "Medel"))
    return c


# -------------------------------------------------------------------
# LEAGUE / DIVISIONS
# -------------------------------------------------------------------


def league_rules_to_dict(rules: LeagueRules) -> dict:
    return {
        "format": rules.format,
        "teams_per_div": rules.teams_per_div,
        "levels": rules.levels,
        "promote": rules.promote,
        "relegate": rules.relegate,
    }


def league_rules_from_dict(d: dict) -> LeagueRules:
    return LeagueRules(
        format=d.get("format", "rak"),
        teams_per_div=d.get("teams_per_div", 16),
        levels=d.get("levels", 1),
        promote=d.get("promote", 0),
        relegate=d.get("relegate", 0),
    )


def division_to_dict(div: Division) -> Dict[str, Any]:
    return {
        "name": div.name,
        "level": int(getattr(div, "level", 1)),
        "clubs": [club_to_dict(c) for c in div.clubs],
    }


def division_from_dict(d: Dict[str, Any]) -> Division:
    return Division(
        name=d["name"],
        level=int(d.get("level", 1)),
        clubs=[club_from_dict(x) for x in d.get("clubs", [])],
    )


def league_to_dict(league: League) -> Dict[str, Any]:
    return {
        "name": league.name,
        "rules": league_rules_to_dict(league.rules),
        "divisions": [division_to_dict(div) for div in league.divisions],
    }


def league_from_dict(d: Dict[str, Any]) -> League:
    return League(
        name=d["name"],
        rules=league_rules_from_dict(d.get("rules", {})),
        divisions=[division_from_dict(x) for x in d.get("divisions", [])],
    )


# -------------------------------------------------------------------
# FIXTURES (per division)
# -------------------------------------------------------------------


def fixtures_to_dict(fixtures_by_div: Dict[str, List[Match]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for div_name, matches in (fixtures_by_div or {}).items():
        out[div_name] = [
            {
                "home": m.home.name,
                "away": m.away.name,
                "round": int(getattr(m, "round", 0)),
            }
            for m in matches
        ]
    return out


def fixtures_from_dict(d: Dict[str, Any], league: League) -> Dict[str, List[Match]]:
    # Bygg index för klubbar via namn
    club_index: Dict[str, Club] = {}
    for div in league.divisions:
        for c in div.clubs:
            club_index[c.name] = c

    out: Dict[str, List[Match]] = {}
    for div_name, items in (d or {}).items():
        arr: List[Match] = []
        for it in items:
            h = club_index.get(it["home"])
            a = club_index.get(it["away"])
            if not (h and a):
                continue
            arr.append(Match(home=h, away=a, round=int(it.get("round", 0))))
        out[div_name] = arr
    return out


# -------------------------------------------------------------------
# CUP STATE (minimal men tillräcklig för att fortsätta)
# -------------------------------------------------------------------


def cup_rules_to_dict(r: CupRules) -> Dict[str, Any]:
    return {
        "two_legged": bool(getattr(r, "two_legged", True)),
        "final_two_legged": bool(getattr(r, "final_two_legged", False)),
    }


def cup_rules_from_dict(d: Dict[str, Any]) -> CupRules:
    return CupRules(
        two_legged=bool(d.get("two_legged", True)),
        final_two_legged=bool(d.get("final_two_legged", False)),
    )


def cup_state_to_dict(cs) -> Optional[Dict[str, Any]]:
    if not cs:
        return None
    return {
        "rules": cup_rules_to_dict(getattr(cs, "rules", CupRules(True, False))),
        "current_clubs": [c.name for c in (getattr(cs, "current_clubs", []) or [])],
        "finished": bool(getattr(cs, "finished", False)),
        "winner": getattr(getattr(cs, "winner", None), "name", None),
        "round_index": int(getattr(cs, "round_index", 0)),
        "queued_fixtures": [
            {"home": f.home.name, "away": f.away.name}
            for f in (getattr(cs, "queued_fixtures", []) or [])
        ],
    }


def cup_state_from_dict(d: Optional[Dict[str, Any]], league: League):
    if not d:
        return None
    from .cup_state import CupState  # undvik cirkulär import

    rules = cup_rules_from_dict(d.get("rules", {}))
    club_index: Dict[str, Club] = {
        c.name: c for div in league.divisions for c in div.clubs
    }

    cs = CupState(rules=rules)
    cs.current_clubs = [
        club_index[name] for name in d.get("current_clubs", []) if name in club_index
    ]
    cs.finished = bool(d.get("finished", False))
    wname = d.get("winner")
    cs.winner = club_index.get(wname) if wname else None
    cs.round_index = int(d.get("round_index", 0))

    qf = []
    for item in d.get("queued_fixtures", []) or []:
        h = club_index.get(item.get("home"))
        a = club_index.get(item.get("away"))
        if h and a:
            qf.append(Match(home=h, away=a, round=0))
    cs.queued_fixtures = qf

    return cs


# -------------------------------------------------------------------
# TRAINING ORDERS (Steg 9.3)
# -------------------------------------------------------------------


def training_orders_to_list(gs) -> list:
    arr = []
    for o in getattr(gs, "training_orders", []) or []:
        arr.append(
            {
                "id": int(getattr(o, "id", 0)),
                "club_name": getattr(o, "club_name", ""),
                "player_id": int(getattr(o, "player_id", 0)),
                "weeks_left": int(getattr(o, "weeks_left", 0)),
                "cost_sek": int(getattr(o, "cost_sek", 200_000)),
                "status": getattr(o, "status", "active"),
                "note": getattr(o, "note", ""),
            }
        )
    return arr


def training_orders_from_list(arr: list):
    from .training import TrainingOrder  # lokal import

    out = []
    for d in arr or []:
        out.append(
            TrainingOrder(
                id=int(d.get("id", 0)),
                club_name=d.get("club_name", ""),
                player_id=int(d.get("player_id", 0)),
                weeks_left=int(d.get("weeks_left", 0)),
                cost_sek=int(d.get("cost_sek", 200_000)),
                status=d.get("status", "active"),
                note=d.get("note", ""),
            )
        )
    return out


# -------------------------------------------------------------------
# STATS & MATCHLOGG
# -------------------------------------------------------------------


def player_stats_to_dict_map(pmap: Dict[int, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for pid, s in (pmap or {}).items():
        if hasattr(s, "__dict__"):
            d = dict(s.__dict__)
        else:
            d = {
                "player_id": getattr(s, "player_id", pid),
                "club_name": getattr(s, "club_name", ""),
                "appearances": getattr(s, "appearances", 0),
                "minutes": getattr(s, "minutes", 0),
                "goals": getattr(s, "goals", 0),
                "assists": getattr(s, "assists", 0),
                "yellows": getattr(s, "yellows", 0),
                "reds": getattr(s, "reds", 0),
                "rating_sum": getattr(s, "rating_sum", 0.0),
                "rating_avg": getattr(s, "rating_avg", 0.0),
            }
        out[str(pid)] = d
    return out


def player_stats_from_dict_map(d: Dict[str, Any]) -> Dict[int, Any]:
    out: Dict[int, Any] = {}
    for k, v in (d or {}).items():
        pid = int(k)
        if hasattr(stats_mod, "PlayerStats"):
            cls = getattr(stats_mod, "PlayerStats")
            obj = cls(**v)
        else:
            obj = v
        out[pid] = obj
    return out


def club_stats_to_dict_map(cmap: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for name, s in (cmap or {}).items():
        if hasattr(s, "__dict__"):
            d = dict(s.__dict__)
        else:
            d = {
                "club_name": getattr(s, "club_name", name),
                "played": getattr(s, "played", 0),
                "wins": getattr(s, "wins", 0),
                "draws": getattr(s, "draws", 0),
                "losses": getattr(s, "losses", 0),
                "goals_for": getattr(s, "goals_for", 0),
                "goals_against": getattr(s, "goals_against", 0),
                "clean_sheets": getattr(s, "clean_sheets", 0),
                "yellows": getattr(s, "yellows", 0),
                "reds": getattr(s, "reds", 0),
                "points": getattr(s, "points", 0),
            }
        out[name] = d
    return out


def club_stats_from_dict_map(d: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for name, v in (d or {}).items():
        if hasattr(stats_mod, "ClubStats"):
            cls = getattr(stats_mod, "ClubStats")
            obj = cls(**v)
        else:
            obj = v
        out[name] = obj
    return out


def match_log_to_dict_list(log: List[Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for mr in log or []:
        if hasattr(mr, "__dict__"):
            d = dict(mr.__dict__)
        else:
            d = {
                "competition": getattr(mr, "competition", "league"),
                "round": getattr(mr, "round", 0),
                "home": getattr(mr, "home", ""),
                "away": getattr(mr, "away", ""),
                "home_goals": getattr(mr, "home_goals", 0),
                "away_goals": getattr(mr, "away_goals", 0),
            }
        out.append(d)
    return out


def match_log_from_dict_list(arr: List[Dict[str, Any]]) -> List[Any]:
    out: List[Any] = []
    if hasattr(stats_mod, "MatchRecord"):
        cls = getattr(stats_mod, "MatchRecord")
        for d in arr or []:
            out.append(cls(**d))
    else:
        out = arr or []
    return out


# -------------------------------------------------------------------
# GAME STATE (top)
# -------------------------------------------------------------------


def game_state_to_dict(gs) -> Dict[str, Any]:
    data = {
        "season": int(getattr(gs, "season", 1)),
        "league": league_to_dict(gs.league),
        "fixtures_by_division": fixtures_to_dict(
            getattr(gs, "fixtures_by_division", {})
        ),
        "current_round": int(getattr(gs, "current_round", 1)),
        "cup_state": cup_state_to_dict(getattr(gs, "cup_state", None)),
        "table_snapshot": getattr(gs, "table_snapshot", {}) or {},
        "player_stats": player_stats_to_dict_map(getattr(gs, "player_stats", {}) or {}),
        "club_stats": club_stats_to_dict_map(getattr(gs, "club_stats", {}) or {}),
        "match_log": match_log_to_dict_list(getattr(gs, "match_log", []) or []),
        "training_orders": training_orders_to_list(gs),  # <-- NYTT
    }
    hist = getattr(gs, "history", None)
    if hist is not None:
        if hasattr(hist, "to_dict"):
            data["history"] = hist.to_dict()
        else:
            data["history"] = getattr(hist, "__dict__", {})
    return data


def game_state_from_dict(d: Dict[str, Any]):
    from .history import HistoryStore
    from .state import GameState  # undvik cirkulär import

    league = league_from_dict(d["league"])
    fixtures = fixtures_from_dict(d.get("fixtures_by_division", {}), league)

    hist_d = d.get("history")
    if isinstance(hist_d, dict) and hasattr(HistoryStore, "from_dict"):
        history = HistoryStore.from_dict(hist_d)
    else:
        history = HistoryStore()

    gs = GameState(
        season=int(d.get("season", 1)),
        league=league,
        fixtures_by_division=fixtures,
        current_round=int(d.get("current_round", 1)),
        history=history,
        cup_state=None,
    )
    gs.ensure_containers()

    # återställ övrigt
    gs.cup_state = cup_state_from_dict(d.get("cup_state"), league)
    gs.table_snapshot = d.get("table_snapshot") or {}
    gs.player_stats = player_stats_from_dict_map(d.get("player_stats", {}))
    gs.club_stats = club_stats_from_dict_map(d.get("club_stats", {}))
    gs.match_log = match_log_from_dict_list(d.get("match_log", []))
    gs.training_orders = training_orders_from_list(
        d.get("training_orders", [])
    )  # <-- NYTT

    return gs


# Alias
serialize_game_state = game_state_to_dict
deserialize_game_state = game_state_from_dict


# -------------------------------------------------------------------
# Disk I/O helpers (frivilligt)
# -------------------------------------------------------------------


def dump_game_state(gs, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(game_state_to_dict(gs), f, ensure_ascii=False, indent=2)


def load_game_state(path: str):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return game_state_from_dict(data)
