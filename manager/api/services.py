from __future__ import annotations

import json
import uuid
import os
import random
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple, TypeVar

from manager.api.contracts import build_contract
from manager.api.utils import ensure_colors, slugify
from manager.core.club import Club, SubstitutionRule
from manager.core.economy import (
    accept_junior_offer,
    process_weekly_economy,
    purchase_listing,
    refresh_transfer_market,
    submit_transfer_bid,
    update_player_values,
)
from manager.core.generator import generate_league
from manager.core.league import LeagueRules
from manager.core.schedule import build_league_schedule
from manager.core.match import EventType, PlayerEvent, Referee, player_event_summary, simulate_match
from manager.core.player import Player, Position
from manager.core.season import Aggressiveness, Tactic
from manager.core.season_progression import end_season
from manager.core.state import GameState
from manager.core.stats import MatchRecord, update_stats_from_result
from manager.core.training import advance_week


T = TypeVar("T")


class ServiceError(RuntimeError):
    """Raised when a CLI operation fails in a controlled manner."""


@dataclass
class FeatureFlags:
    """Feature toggles that alter how the service layer behaves."""

    mock_mode: bool = False
    mock_data_path: Optional[Path] = None
    persist_changes: bool = True
    mock_seed: int = 1337
    mock_career_id: str = "c-mock"

    @classmethod
    def from_env(cls) -> "FeatureFlags":
        raw = os.getenv("MANAGER_FEATURES", "")
        tokens = {token.strip().lower() for token in raw.split(",") if token.strip()}
        mock_mode = "mock" in tokens or os.getenv("MANAGER_MOCK_MODE") == "1"
        mock_path = os.getenv("MANAGER_MOCK_PATH")
        mock_seed = os.getenv("MANAGER_MOCK_SEED")
        persist_env = os.getenv("MANAGER_PERSIST_CHANGES")
        disable_persist_env = os.getenv("MANAGER_DISABLE_PERSIST")

        flags = cls()
        if mock_mode:
            flags.mock_mode = True
            flags.persist_changes = False
        if mock_path:
            flags.mock_data_path = Path(mock_path)
        if mock_seed:
            try:
                flags.mock_seed = int(mock_seed)
            except ValueError:
                pass
        if persist_env == "1":
            flags.persist_changes = True
        if disable_persist_env == "1":
            flags.persist_changes = False
        return flags


@dataclass
class ServiceContext:
    """Holds paths used across CLI operations."""

    saves_dir: Path
    file_path: Path
    flags: FeatureFlags = field(default_factory=FeatureFlags)

    @classmethod
    def from_paths(
        cls,
        saves_dir: Path,
        file_path: Optional[Path] = None,
        *,
        flags: Optional[FeatureFlags] = None,
    ) -> "ServiceContext":
        base = Path(saves_dir)
        base.mkdir(parents=True, exist_ok=True)
        target = Path(file_path) if file_path else base / "career.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        return cls(saves_dir=base, file_path=target, flags=flags or FeatureFlags.from_env())


class CareerManager:
    """Utility helpers for dealing with save files."""

    def __init__(self, context: ServiceContext) -> None:
        self.context = context

    def list_careers(self) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        if self.context.flags.mock_mode:
            entries.append(
                {
                    "career_id": self.context.flags.mock_career_id,
                    "name": "Demo-karriär",
                    "season": 1,
                    "team_id": None,
                    "path": str(self.context.file_path),
                }
            )
        for file in sorted(self.context.saves_dir.glob("*.json")):
            try:
                with file.open("r", encoding="utf-8") as handle:
                    data = json.load(handle)
            except Exception:
                continue
            meta = data.get("meta", {}) or {}
            entries.append(
                {
                    "career_id": meta.get("career_id") or file.stem,
                    "name": meta.get("name") or file.stem,
                    "season": data.get("season"),
                    "team_id": meta.get("user_team_id"),
                    "path": str(file),
                }
            )
        return entries

    def resolve(self, career_id: str) -> Path:
        if self.context.flags.mock_mode and career_id == self.context.flags.mock_career_id:
            return self.context.file_path
        path = self.context.saves_dir / f"{career_id}.json"
        if not path.exists():
            raise ServiceError(f"Ingen sparfil hittades för id '{career_id}'.")
        return path


class GameService:
    """High level operations for manipulating GameState instances."""

    def __init__(self, context: ServiceContext) -> None:
        self.context = context
        self.careers = CareerManager(context)
        self._mock_state: Optional[GameState] = None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _load_state(self, path: Optional[Path] = None) -> GameState:
        target = path or self.context.file_path
        flags = self.context.flags
        if flags.mock_mode and path is None:
            if self._mock_state is None:
                self._mock_state = _initialise_mock_state(flags)
            return self._mock_state
        if flags.mock_mode:
            source = flags.mock_data_path or target
            if source.exists():
                gs = GameState.load(source)
                gs.ensure_containers()
                self._mock_state = gs
                return gs
            if self._mock_state is None:
                self._mock_state = _initialise_mock_state(flags)
            return self._mock_state
        if not target.exists():
            raise ServiceError(f"Sparfilen '{target}' finns inte.")
        gs = GameState.load(target)
        gs.ensure_containers()
        return gs

    def _save_state(self, gs: GameState, path: Optional[Path] = None) -> Path:
        target = path or self.context.file_path
        flags = self.context.flags
        if flags.mock_mode:
            self._mock_state = gs
            if flags.persist_changes:
                destination = flags.mock_data_path or target
                destination.parent.mkdir(parents=True, exist_ok=True)
                gs.save(destination)
            return target
        target.parent.mkdir(parents=True, exist_ok=True)
        gs.save(target)
        return target

    # ------------------------------------------------------------------
    # Creation / persistence
    # ------------------------------------------------------------------

    def create(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        structure = payload.get("league_structure", "pyramid")
        divisions = int(payload.get("divisions", 1))
        teams_per_div = int(payload.get("teams_per_division", 12))

        rules = LeagueRules(
            format="pyramid" if structure == "pyramid" else "rak",
            levels=max(1, divisions),
            teams_per_div=max(2, teams_per_div),
            promote=int(payload.get("promote", 2)),
            relegate=int(payload.get("relegate", 2)),
        )
        league = generate_league(payload.get("league_name", "Karriär"), rules)
        fixtures = build_league_schedule(league)

        gs = GameState(season=1, league=league, fixtures_by_division=fixtures)
        gs.ensure_containers()
        gs.current_round = 1
        gs.season_phase = "preseason"
        gs.calendar_week = 1
        gs.meta.setdefault("version", "1.0")
        gs.meta.setdefault("career_id", f"c-{uuid.uuid4().hex[:8]}")
        gs.meta["name"] = payload.get("name", gs.meta.get("name", "Karriär"))
        if payload.get("options"):
            options = payload.get("options", {})
            if isinstance(options, dict):
                gs.options.update(options)

        user_team_payload = payload.get("user_team", {}) or {}
        manager_payload = payload.get("manager", {}) or {}
        user_division = league.divisions[0] if league.divisions else None
        user_club: Optional[Club] = user_division.clubs[0] if (user_division and user_division.clubs) else None
        if user_club is not None:
            if user_team_payload.get("name"):
                user_club.name = user_team_payload["name"]
            if user_team_payload.get("stadium"):
                user_club.stadium_name = user_team_payload["stadium"]
            if user_team_payload.get("emblem"):
                user_club.emblem_path = user_team_payload["emblem"]
            colors_payload = user_team_payload.get("colors")
            if colors_payload:
                user_club.colors = ensure_colors(colors_payload)
            user_club.manager_name = manager_payload.get("name", user_club.manager_name)
            gs.meta["user_team_id"] = getattr(user_club, "club_id", None)
        if "user_team_id" not in gs.meta and league.divisions:
            gs.meta["user_team_id"] = league.divisions[0].clubs[0].club_id

        gs.options.setdefault("youth_preference", "MF")
        update_player_values(gs)
        refresh_transfer_market(gs)

        career_id = gs.meta.get("career_id") or f"c-{uuid.uuid4().hex[:8]}"
        target = self.context.saves_dir / f"{career_id}.json"
        self._save_state(gs, target)
        self.context = ServiceContext.from_paths(
            self.context.saves_dir, target, flags=self.context.flags
        )

        return {
            "career_id": career_id,
            "path": str(target),
            "game": build_contract(gs),
        }

    def dump(self, path: Optional[Path] = None) -> Dict[str, Any]:
        gs = self._load_state(path)
        return build_contract(gs)

    def load_career(self, career_id: str) -> Dict[str, Any]:
        if self.context.flags.mock_mode and career_id == self.context.flags.mock_career_id:
            gs = self._load_state()
            return build_contract(gs)
        path = self.careers.resolve(career_id)
        return self.dump(path)

    def save_as(self, name: str, path: Optional[Path] = None) -> Dict[str, Any]:
        gs = self._load_state(path)
        safe = slugify(name or "save")
        career_id = f"c-{safe}"
        gs.meta["career_id"] = career_id
        gs.meta["name"] = name
        target = self.context.saves_dir / f"{career_id}.json"
        self._save_state(gs, target)
        return {"career_id": career_id, "path": str(target)}

    @contextmanager
    def readonly_state(self, path: Optional[Path] = None) -> Iterator[GameState]:
        """Yield the current state without persisting any changes."""

        gs = self._load_state(path)
        yield gs

    @contextmanager
    def transaction(
        self, path: Optional[Path] = None, *, persist: bool = True
    ) -> Iterator[GameState]:
        """Context manager that loads, yields and optionally saves the state."""

        gs = self._load_state(path)
        try:
            yield gs
        finally:
            if persist:
                self._save_state(gs, path)

    def apply(
        self,
        func: Callable[[GameState], T],
        *,
        path: Optional[Path] = None,
        persist: bool = True,
    ) -> T:
        """Run ``func`` with the current GameState and optionally persist updates."""

        gs = self._load_state(path)
        result = func(gs)
        if persist:
            self._save_state(gs, path)
        return result

    # ------------------------------------------------------------------
    # Mutating helpers
    # ------------------------------------------------------------------

    def update_options(self, updates: Dict[str, Any], path: Optional[Path] = None) -> Dict[str, Any]:
        gs = self._load_state(path)
        gs.options.update(updates or {})
        self._save_state(gs, path)
        return {"ok": True, "options": gs.options}

    def set_youth_preference(self, preference: str, path: Optional[Path] = None) -> Dict[str, Any]:
        gs = self._load_state(path)
        gs.options["youth_preference"] = preference
        self._save_state(gs, path)
        return {"ok": True, "preference": preference}

    def buy_from_market(self, club_name: str, index: int, path: Optional[Path] = None) -> Dict[str, Any]:
        gs = self._load_state(path)
        message, player = purchase_listing(gs, club_name, index)
        self._save_state(gs, path)
        return {"ok": True, "message": message, "player_id": player.id}

    def submit_transfer_bid(self, payload: Dict[str, Any], path: Optional[Path] = None) -> Dict[str, Any]:
        gs = self._load_state(path)
        buyer = payload.get("buyer")
        seller = payload.get("seller")
        player_id = payload.get("player_id")
        price = int(payload.get("price", 0))
        if not all([buyer, seller, player_id]):
            raise ServiceError("buyer, seller och player_id måste anges.")
        message = submit_transfer_bid(gs, buyer, seller, int(player_id), price)
        self._save_state(gs, path)
        return {"ok": True, "message": message}

    def accept_junior(self, club_name: str, index: int, path: Optional[Path] = None) -> Dict[str, Any]:
        gs = self._load_state(path)
        player = accept_junior_offer(gs, club_name, index)
        self._save_state(gs, path)
        return {"ok": True, "player_id": player.id}

    def start_season(self, path: Optional[Path] = None) -> Dict[str, Any]:
        gs = self._load_state(path)
        gs.season_phase = "in_progress"
        refresh_transfer_market(gs)
        self._save_state(gs, path)
        return {"ok": True, "phase": gs.season_phase}

    def end_season(self, path: Optional[Path] = None) -> Dict[str, Any]:
        gs = self._load_state(path)
        report = end_season(gs)
        gs.season_phase = "postseason"
        gs.current_round = 1
        gs.calendar_week = 1
        self._save_state(gs, path)
        return {"ok": True, "report": report}

    def next_week(self, path: Optional[Path] = None) -> Dict[str, Any]:
        gs = self._load_state(path)
        logs = advance_week(gs)
        logs.extend(process_weekly_economy(gs))
        gs.calendar_week += 1
        self._save_state(gs, path)
        return {"ok": True, "week": gs.calendar_week, "logs": logs}

    def sponsor_activity(self, club_name: str, amount: int = 1_000_000, path: Optional[Path] = None) -> Dict[str, Any]:
        gs = self._load_state(path)
        for division in gs.league.divisions:
            for club in division.clubs:
                if club.name.lower() == club_name.lower():
                    club.cash_sek += amount
                    self._save_state(gs, path)
                    return {"ok": True, "balance": club.cash_sek}
        raise ServiceError(f"Klubben '{club_name}' hittades inte.")

    def mark_mail_read(self, mail_id: str, path: Optional[Path] = None) -> Dict[str, Any]:
        gs = self._load_state(path)
        for mail in getattr(gs, "mailbox", []) or []:
            if mail.get("id") == mail_id:
                mail["unread"] = False
                self._save_state(gs, path)
                return {"ok": True}
        raise ServiceError(f"Meddelandet '{mail_id}' hittades inte.")

    def set_tactics(self, team_id: str, data: Dict[str, Any], path: Optional[Path] = None) -> Dict[str, Any]:
        gs = self._load_state(path)
        club = self._club_by_team_id(gs, team_id)
        if club is None:
            raise ServiceError(f"Lag '{team_id}' hittades inte.")
        self._apply_tactics(club, data)
        self._save_state(gs, path)
        return {"ok": True}

    def set_match_result(
        self, match_id: str, payload: Dict[str, Any], path: Optional[Path] = None
    ) -> Dict[str, Any]:
        gs = self._load_state(path)
        updated = False
        for idx, rec in enumerate(getattr(gs, "match_log", []) or []):
            record_obj = _ensure_match_record_obj(rec)
            if _match_record_id(record_obj) != match_id:
                continue
            if not isinstance(rec, MatchRecord):
                gs.match_log[idx] = record_obj
            if "home_goals" in payload:
                record_obj.home_goals = int(
                    payload.get("home_goals", record_obj.home_goals)
                )
            if "away_goals" in payload:
                record_obj.away_goals = int(
                    payload.get("away_goals", record_obj.away_goals)
                )
            if "events" in payload and isinstance(payload["events"], list):
                record_obj.events = list(payload["events"])
            if "ratings" in payload and isinstance(payload["ratings"], dict):
                ratings: Dict[int, float] = {}
                for key, value in payload["ratings"].items():
                    try:
                        pid = int(str(key).split("-")[-1])
                        ratings[pid] = float(value)
                    except (TypeError, ValueError):
                        continue
                record_obj.ratings = ratings
            updated = True
            break
        if not updated:
            raise ServiceError(f"Match '{match_id}' hittades inte i matchloggen.")
        self._save_state(gs, path)
        return {"ok": True, "match_id": match_id}

    def get_match_details(self, match_id: str, path: Optional[Path] = None) -> Dict[str, Any]:
        gs = self._load_state(path)
        return _build_match_details(gs, match_id)

    def simulate_match(
        self, match_id: str, mode: str = "quick", path: Optional[Path] = None
    ) -> Dict[str, Any]:
        gs = self._load_state(path)
        fixture = _find_fixture(gs, match_id)
        if fixture is None:
            raise ServiceError(f"Match '{match_id}' hittades inte bland schemalagda matcher.")

        competition, division, match = fixture
        home = match.home
        away = match.away

        result = simulate_match(
            home,
            away,
            referee=Referee(),
            home_tactic=getattr(home, "tactic", Tactic()),
            away_tactic=getattr(away, "tactic", Tactic()),
            home_aggr=getattr(home, "aggressiveness", Aggressiveness("Medel")),
            away_aggr=getattr(away, "aggressiveness", Aggressiveness("Medel")),
        )

        record = update_stats_from_result(
            result,
            competition=competition,
            round_no=getattr(match, "round", 0),
            player_stats=gs.player_stats,
            club_stats=gs.club_stats,
            player_career_stats=gs.player_career_stats,
            club_career_stats=gs.club_career_stats,
        )

        existing: List[MatchRecord] = []
        for rec in getattr(gs, "match_log", []) or []:
            candidate = _ensure_match_record_obj(rec)
            if _match_record_id(candidate) != match_id:
                existing.append(candidate)
        existing.append(record)
        gs.match_log = existing

        _rebuild_league_table(gs)
        self._save_state(gs, path)
        return {"ok": True, "match_id": match_id, "status": "final", "mode": mode}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_tactics(club: Club, data: Dict[str, Any]) -> None:
        tactic_data = data.get("tactic", {}) or {}
        club.tactic = Tactic(
            attacking=bool(tactic_data.get("attacking", club.tactic.attacking)),
            defending=bool(tactic_data.get("defending", club.tactic.defending)),
            offside_trap=bool(tactic_data.get("offside_trap", club.tactic.offside_trap)),
            dark_arts=bool(tactic_data.get("dark_arts", getattr(club.tactic, "dark_arts", False))),
            tempo=float(tactic_data.get("tempo", club.tactic.tempo)),
        )
        aggr = data.get("aggressiveness")
        if aggr:
            club.aggressiveness = Aggressiveness(aggr)
        if "captain_id" in data:
            club.captain_id = int(data.get("captain_id") or 0) or None
        if "preferred_lineup" in data:
            club.preferred_lineup = [int(pid) for pid in data.get("preferred_lineup", [])]
        if "bench_order" in data:
            club.bench_order = [int(pid) for pid in data.get("bench_order", [])]
        if "substitution_plan" in data:
            club.substitution_plan = []
            for rule in data.get("substitution_plan", []):
                try:
                    club.substitution_plan.append(
                        SubstitutionRule(
                            minute=int(rule.get("minute", 60)),
                            player_in=int(rule.get("player_in")) if rule.get("player_in") else None,
                            player_out=int(rule.get("player_out")) if rule.get("player_out") else None,
                            position=rule.get("position"),
                            on_injury=bool(rule.get("on_injury", False)),
                        )
                    )
                except Exception:
                    continue

    @staticmethod
    def _club_by_team_id(gs: GameState, team_id: str) -> Optional[Club]:
        for division in gs.league.divisions:
            for club in division.clubs:
                if getattr(club, "club_id", None) == team_id:
                    return club
        return None


def _coerce_player_id(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value)
    if text.startswith("p-"):
        text = text.split("-", 1)[-1]
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def _coerce_int_map(data: Any) -> Dict[int, int]:
    out: Dict[int, int] = {}
    if isinstance(data, dict):
        for key, value in data.items():
            pid = _coerce_player_id(key)
            if pid is None:
                continue
            try:
                out[pid] = int(value)
            except (TypeError, ValueError):
                continue
    return out


def _coerce_int_list(data: Any) -> List[int]:
    out: List[int] = []
    if isinstance(data, list):
        for value in data:
            pid = _coerce_player_id(value)
            if pid is None:
                continue
            out.append(pid)
    return out


def _ensure_match_record_obj(rec: Any) -> MatchRecord:
    if isinstance(rec, MatchRecord):
        return rec
    if isinstance(rec, dict):
        data = dict(rec)
        ratings_raw = data.get("ratings", {}) or {}
        ratings: Dict[int, float] = {}
        if isinstance(ratings_raw, dict):
            for key, value in ratings_raw.items():
                pid = _coerce_player_id(key)
                if pid is None:
                    continue
                try:
                    ratings[pid] = float(value)
                except (TypeError, ValueError):
                    continue
        return MatchRecord(
            competition=data.get("competition", "league"),
            round=int(data.get("round", 0) or 0),
            home=data.get("home", ""),
            away=data.get("away", ""),
            home_goals=int(data.get("home_goals", 0) or 0),
            away_goals=int(data.get("away_goals", 0) or 0),
            events=list(data.get("events", []) or []),
            ratings=ratings,
            lineup_home=_coerce_int_list(data.get("lineup_home")),
            lineup_away=_coerce_int_list(data.get("lineup_away")),
            bench_home=_coerce_int_list(data.get("bench_home")),
            bench_away=_coerce_int_list(data.get("bench_away")),
            formation_home=data.get("formation_home"),
            formation_away=data.get("formation_away"),
            minutes_home=_coerce_int_map(data.get("minutes_home")),
            minutes_away=_coerce_int_map(data.get("minutes_away")),
            stats=dict(data.get("stats", {}) or {}),
            ratings_by_unit=dict(data.get("ratings_by_unit", {}) or {}),
            tactic_report=dict(data.get("tactic_report", {}) or {}),
            awards=dict(data.get("awards", {}) or {}),
            referee=dict(data.get("referee", {}) or {}),
            halftime_home=int(data.get("halftime_home", 0) or 0),
            halftime_away=int(data.get("halftime_away", 0) or 0),
            dark_arts_home=bool(data.get("dark_arts_home", False)),
            dark_arts_away=bool(data.get("dark_arts_away", False)),
        )
    # Fall back to a minimal record if data is malformed
    return MatchRecord(
        competition="league",
        round=0,
        home="",
        away="",
        home_goals=0,
        away_goals=0,
        events=[],
    )


def _match_record_id(rec: Any) -> str:
    record = _ensure_match_record_obj(rec)
    prefix = "c" if getattr(record, "competition", "league") == "cup" else "l"
    home = getattr(record, "home", "")
    away = getattr(record, "away", "")
    return f"{prefix}-{getattr(record, 'round', 0):02d}-{slugify(home)}-{slugify(away)}"


def _make_match_id(prefix: str, round_no: int, home: str, away: str) -> str:
    return f"{prefix}-{round_no:02d}-{slugify(home)}-{slugify(away)}"


def _team_identifier(club: Club) -> str:
    club_id = getattr(club, "club_id", None)
    if club_id:
        return club_id
    return slugify(club.name, prefix="t")


def _club_indexes(
    gs: GameState,
) -> Tuple[Dict[str, Club], Dict[int, Player], Dict[str, str], Dict[str, Any]]:
    clubs: Dict[str, Club] = {}
    players: Dict[int, Player] = {}
    team_ids: Dict[str, str] = {}
    divisions: Dict[str, Any] = {}
    for division in gs.league.divisions:
        for club in division.clubs:
            clubs[club.name] = club
            team_ids[club.name] = _team_identifier(club)
            divisions[club.name] = division
            for player in getattr(club, "players", []) or []:
                pid = getattr(player, "id", None)
                if pid is not None:
                    players[pid] = player
    return clubs, players, team_ids, divisions


def _initialise_mock_state(flags: FeatureFlags) -> GameState:
    if flags.mock_data_path and flags.mock_data_path.exists():
        try:
            with flags.mock_data_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception:
            data = None
        if isinstance(data, dict):
            gs = GameState.from_dict(data)
            gs.ensure_containers()
            return gs
    return _build_mock_state(flags)


def _build_mock_state(flags: FeatureFlags) -> GameState:
    random_state = random.getstate()
    try:
        random.seed(flags.mock_seed)
        rules = LeagueRules(format="pyramid", levels=1, teams_per_div=6, promote=2, relegate=2)
        league = generate_league("Demo League", rules)
    finally:
        random.setstate(random_state)

    fixtures = build_league_schedule(league)
    gs = GameState(season=1, league=league, fixtures_by_division=fixtures)
    gs.ensure_containers()
    gs.meta.setdefault("version", "1.0")
    gs.meta["career_id"] = flags.mock_career_id
    gs.meta.setdefault("name", "Demo-karriär")
    if league.divisions and league.divisions[0].clubs:
        gs.meta.setdefault("user_team_id", getattr(league.divisions[0].clubs[0], "club_id", None))
    gs.options.setdefault("mock_mode", True)
    gs.season_phase = "in_progress"
    gs.calendar_week = 1
    gs.current_round = 1

    update_player_values(gs)
    refresh_transfer_market(gs)

    if league.divisions:
        division = league.divisions[0]
        matches = fixtures.get(division.name, []) or []
        to_simulate = min(len(matches), max(1, len(division.clubs) // 2))
        for match in matches[:to_simulate]:
            result = simulate_match(
                match.home,
                match.away,
                referee=Referee(skill=7, hardness=5),
                home_tactic=getattr(match.home, "tactic", Tactic()),
                away_tactic=getattr(match.away, "tactic", Tactic()),
                home_aggr=getattr(match.home, "aggressiveness", Aggressiveness("Medel")),
                away_aggr=getattr(match.away, "aggressiveness", Aggressiveness("Medel")),
            )
            record = update_stats_from_result(
                result,
                competition="league",
                round_no=getattr(match, "round", 1),
                player_stats=gs.player_stats,
                club_stats=gs.club_stats,
                player_career_stats=gs.player_career_stats,
                club_career_stats=gs.club_career_stats,
            )
            gs.match_log.append(record)
            gs.current_round = max(gs.current_round, getattr(match, "round", 1) + 1)

    _rebuild_league_table(gs)
    if not gs.economy_ledger:
        gs.economy_ledger.extend(process_weekly_economy(gs))
    gs.ensure_containers()
    return gs


def _player_name(player: Optional[Player], pid: Optional[int] = None) -> str:
    if player is None:
        return f"Spelare {pid}" if pid is not None else "Okänd spelare"
    full = getattr(player, "full_name", "").strip()
    if full:
        return full
    first = getattr(player, "first_name", "")
    last = getattr(player, "last_name", "")
    combo = f"{first} {last}".strip()
    return combo or f"Spelare {getattr(player, 'id', pid)}"


def _ensure_summary_entry(summary: Dict[int, Dict[str, Any]], pid: int) -> Dict[str, Any]:
    if pid not in summary:
        summary[pid] = {
            "goals": 0,
            "goal_minutes": [],
            "assists": 0,
            "assist_minutes": [],
            "yellows": [],
            "reds": [],
            "pens_missed": [],
            "injury": False,
            "sub_in": None,
            "sub_out": None,
        }
    return summary[pid]


def _record_event_summary(
    record: MatchRecord, players: Dict[int, Player]
) -> Tuple[Dict[int, Dict[str, Any]], List[PlayerEvent]]:
    event_objects: List[PlayerEvent] = []
    for ev in getattr(record, "events", []) or []:
        type_name = ev.get("type")
        try:
            event_type = EventType[type_name]
        except Exception:
            continue
        minute = int(ev.get("minute") or 0)
        player = players.get(ev.get("player_id"))
        assist = players.get(ev.get("assist_id"))
        note = ev.get("note")
        event_objects.append(
            PlayerEvent(event_type, minute, player, assist_by=assist, note=note)
        )
    summary = player_event_summary(event_objects)
    return summary, event_objects


def _icons_from_summary(entry: Dict[str, Any]) -> List[str]:
    icons: List[str] = []
    if entry.get("goals"):
        icons.append("goal")
    if entry.get("assists"):
        icons.append("assist")
    if entry.get("yellows"):
        icons.append("yc")
    if entry.get("reds"):
        icons.append("rc")
    if entry.get("pens_missed"):
        icons.append("pen_missed")
    if entry.get("injury"):
        icons.append("injury")
    if entry.get("sub_in") is not None:
        icons.append("sub_in")
    if entry.get("sub_out") is not None:
        icons.append("sub_out")
    return icons


def _bookings_from_summary(entry: Dict[str, Any]) -> List[Dict[str, Any]]:
    bookings: List[Dict[str, Any]] = []
    for minute in entry.get("yellows", []) or []:
        bookings.append({"type": "yc", "minute": minute})
    for minute in entry.get("reds", []) or []:
        bookings.append({"type": "rc", "minute": minute})
    return bookings


def _build_player_row(
    pid: int,
    player: Optional[Player],
    entry: Dict[str, Any],
    ratings: Dict[int, float],
    club: Club,
) -> Dict[str, Any]:
    minutes = int(entry.get("minutes", 0))
    subs = None
    if entry.get("sub_in") is not None or entry.get("sub_out") is not None:
        subs = {"in": entry.get("sub_in"), "out": entry.get("sub_out")}
    position = "MF"
    if player is not None and getattr(player, "position", None) is not None:
        position = getattr(getattr(player.position, "value", None), "upper", lambda: None)() or getattr(
            player.position, "name", "MF"
        )
    return {
        "player_id": f"p-{pid}",
        "name": _player_name(player, pid),
        "pos": position,
        "minutes": minutes,
        "captain": bool(getattr(club, "captain_id", None) == pid),
        "injured": bool(entry.get("injury")),
        "bookings": _bookings_from_summary(entry),
        "subs": subs,
        "rating": ratings.get(pid),
        "icons": _icons_from_summary(entry),
    }


def _lineup_rows(
    club: Club,
    players: Dict[int, Player],
    lineup_ids: List[int],
    bench_ids: List[int],
    minutes_map: Dict[int, int],
    ratings: Dict[int, float],
    summary: Dict[int, Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    ordered: List[int] = []
    seen: set[int] = set()
    for pid in lineup_ids:
        if pid is not None and pid not in seen:
            ordered.append(pid)
            seen.add(pid)
    for pid in minutes_map.keys():
        if pid not in seen:
            ordered.append(pid)
            seen.add(pid)
    rows: List[Dict[str, Any]] = []
    for pid in ordered:
        if pid is None:
            continue
        entry = _ensure_summary_entry(summary, pid)
        entry["minutes"] = int(minutes_map.get(pid, entry.get("minutes", 0)))
        player = players.get(pid)
        rows.append(_build_player_row(pid, player, entry, ratings, club))
    bench = [f"p-{pid}" for pid in bench_ids if pid is not None]
    return rows, bench


def _event_type_slug(type_name: str) -> str:
    mapping = {
        "GOAL": "goal",
        "PENALTY_SCORED": "pen_scored",
        "PENALTY_MISSED": "pen_missed",
        "YELLOW": "yc",
        "RED": "rc",
        "SUBSTITUTION": "sub",
        "INJURY": "injury",
        "OFFSIDE": "offside",
        "FOUL": "foul",
        "WOODWORK": "woodwork",
        "CORNER": "corner",
    }
    return mapping.get(type_name, type_name.lower())


def _build_event_list(
    record: MatchRecord,
    home_team_id: str,
    away_team_id: str,
    home_ids: set[int],
    away_ids: set[int],
) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    existing_markers: set[tuple[str, int]] = set()
    for ev in getattr(record, "events", []) or []:
        type_name = str(ev.get("type", ""))
        minute = ev.get("minute")
        player_id = ev.get("player_id")
        assist_id = ev.get("assist_id")
        team_id = None
        if player_id in home_ids or assist_id in home_ids:
            team_id = home_team_id
        elif player_id in away_ids or assist_id in away_ids:
            team_id = away_team_id
        entry: Dict[str, Any] = {
            "minute": minute,
            "type": _event_type_slug(type_name),
            "team_id": team_id,
            "player_id": f"p-{player_id}" if player_id is not None else None,
            "assist_id": f"p-{assist_id}" if assist_id is not None else None,
            "detail": ev.get("note"),
        }
        if type_name == "SUBSTITUTION":
            if player_id is not None:
                entry["sub_in_id"] = f"p-{player_id}"
            if assist_id is not None:
                entry["sub_out_id"] = f"p-{assist_id}"
        events.append(entry)
        if minute is not None:
            existing_markers.add((_event_type_slug(type_name), int(minute)))

    def _ensure_marker(slug: str, minute: int, detail: str | None) -> None:
        key = (slug, minute)
        if key in existing_markers:
            return
        events.append(
            {
                "minute": minute,
                "type": slug,
                "team_id": None,
                "player_id": None,
                "assist_id": None,
                "detail": detail,
            }
        )
        existing_markers.add(key)

    _ensure_marker(
        "ht",
        45,
        f"{int(getattr(record, 'halftime_home', 0))}-{int(getattr(record, 'halftime_away', 0))}",
    )
    _ensure_marker(
        "ft",
        90,
        f"{int(getattr(record, 'home_goals', 0))}-{int(getattr(record, 'away_goals', 0))}",
    )
    events.sort(key=lambda item: (item.get("minute") or 0, item.get("type")))
    return events


def _default_stats() -> Dict[str, Dict[str, int]]:
    return {
        "possession": {"home": 50, "away": 50, "ht_home": 50, "ht_away": 50},
        "chances": {"home": 0, "away": 0, "ht_home": 0, "ht_away": 0},
    }


def _stats_with_defaults(record: MatchRecord) -> Dict[str, Dict[str, int]]:
    stats = record.stats or {}
    if not stats:
        return _default_stats()
    possession = stats.get("possession", {}) or {}
    chances = stats.get("chances", {}) or {}
    return {
        "possession": {
            "home": int(possession.get("home", 50)),
            "away": int(possession.get("away", 50)),
            "ht_home": int(possession.get("ht_home", possession.get("home", 50))),
            "ht_away": int(possession.get("ht_away", possession.get("away", 50))),
        },
        "chances": {
            "home": int(chances.get("home", 0)),
            "away": int(chances.get("away", 0)),
            "ht_home": int(chances.get("ht_home", chances.get("home", 0))),
            "ht_away": int(chances.get("ht_away", chances.get("away", 0))),
        },
    }


def _tactics_with_defaults(
    record: MatchRecord, home: Club, away: Club, players: Dict[int, Player]
) -> Dict[str, Any]:
    report = record.tactic_report or {}
    if report:
        return {
            "home": report.get("home", {}),
            "away": report.get("away", {}),
        }
    home_lineup = [players.get(pid) for pid in record.lineup_home if pid is not None]
    away_lineup = [players.get(pid) for pid in record.lineup_away if pid is not None]
    return {
        "home": _snapshot_for_club(home, home_lineup),
        "away": _snapshot_for_club(away, away_lineup),
    }


def _snapshot_for_club(club: Club, lineup: List[Optional[Player]]) -> Dict[str, Any]:
    lineup_clean = [p for p in lineup if p is not None]
    tactic = getattr(club, "tactic", Tactic())
    aggr = getattr(club, "aggressiveness", Aggressiveness("Medel"))
    tempo = float(getattr(tactic, "tempo", 1.0) or 1.0)
    if tempo >= 1.1:
        style = "Offensiv"
    elif tempo <= 0.9:
        style = "Lugn"
    else:
        style = "Normal"

    aggr_name = str(getattr(aggr, "name", "Medel")).lower()
    if "aggressiv" in aggr_name:
        aggr_label = "Hårt"
    elif "lugn" in aggr_name:
        aggr_label = "Lugnt"
    else:
        aggr_label = "Normal"

    counts = {Position.DF: 0, Position.MF: 0, Position.FW: 0}
    for player in lineup_clean:
        pos = getattr(player, "position", None)
        if pos in counts:
            counts[pos] += 1
    formation = f"{counts[Position.DF]}-{counts[Position.MF]}-{counts[Position.FW]}"

    return {
        "formation": formation,
        "style": style,
        "attack_strategy": "Varierat",
        "defense_strategy": "Normalt" if not getattr(tactic, "defending", False) else "Defensivt",
        "aggressiveness": aggr_label,
        "long_balls": tempo >= 1.1,
        "pressing": bool(getattr(tactic, "attacking", False)),
        "offside_trap": bool(getattr(tactic, "offside_trap", False)),
        "dark_arts": bool(getattr(tactic, "dark_arts", False)),
        "gameplan_vs": "Ingen",
        "playmaker_id": None,
        "captain_id": (
            f"p-{club.captain_id}" if getattr(club, "captain_id", None) else None
        ),
        "freekick_taker_id": None,
        "penalty_taker_id": None,
    }


def _awards_with_defaults(record: MatchRecord) -> Dict[str, Any]:
    awards = record.awards or {}
    return {
        "mom_home": awards.get("mom_home"),
        "mom_away": awards.get("mom_away"),
    }


def _referee_with_defaults(record: MatchRecord) -> Dict[str, Any]:
    ref = record.referee or {}
    if ref:
        return ref
    return {"name": None, "skill": None, "hardness": None, "grade": None}


def _match_details_from_record(
    gs: GameState,
    match_id: str,
    record: MatchRecord,
    clubs: Dict[str, Club],
    players: Dict[int, Player],
    team_ids: Dict[str, str],
) -> Dict[str, Any]:
    home_club = clubs.get(record.home)
    away_club = clubs.get(record.away)
    if home_club is None or away_club is None:
        raise ServiceError("Matchens lag saknas i ligan.")

    home_team_id = team_ids.get(record.home, _team_identifier(home_club))
    away_team_id = team_ids.get(record.away, _team_identifier(away_club))

    summary, event_objects = _record_event_summary(record, players)
    for pid, mins in (record.minutes_home or {}).items():
        entry = _ensure_summary_entry(summary, pid)
        entry["minutes"] = int(mins)
    for pid, mins in (record.minutes_away or {}).items():
        entry = _ensure_summary_entry(summary, pid)
        entry["minutes"] = int(mins)

    home_rows, bench_home = _lineup_rows(
        home_club,
        players,
        record.lineup_home,
        record.bench_home,
        record.minutes_home or {},
        record.ratings or {},
        summary,
    )
    away_rows, bench_away = _lineup_rows(
        away_club,
        players,
        record.lineup_away,
        record.bench_away,
        record.minutes_away or {},
        record.ratings or {},
        summary,
    )

    home_ids = set(pid for pid in record.lineup_home if pid is not None)
    home_ids.update(pid for pid in (record.minutes_home or {}).keys())
    home_ids.update(pid for pid in record.bench_home if pid is not None)
    away_ids = set(pid for pid in record.lineup_away if pid is not None)
    away_ids.update(pid for pid in (record.minutes_away or {}).keys())
    away_ids.update(pid for pid in record.bench_away if pid is not None)

    events = _build_event_list(record, home_team_id, away_team_id, home_ids, away_ids)

    return {
        "match": {
            "id": match_id,
            "league": {
                "id": slugify(gs.league.name, prefix="L"),
                "name": gs.league.name,
                "season": gs.season,
                "round": int(getattr(record, "round", 0)),
            },
            "venue": {
                "stadium": getattr(home_club, "stadium_name", f"{home_club.name} Arena"),
                "city": None,
            },
            "datetime_utc": None,
            "referee": _referee_with_defaults(record),
            "status": "final",
            "score": {
                "home": record.home_goals,
                "away": record.away_goals,
                "ht_home": getattr(record, "halftime_home", 0),
                "ht_away": getattr(record, "halftime_away", 0),
            },
        },
        "teams": {
            "home": {
                "id": home_team_id,
                "name": home_club.name,
                "shirt": {"home": True, "colors": ensure_colors(getattr(home_club, "colors", None))},
            },
            "away": {
                "id": away_team_id,
                "name": away_club.name,
                "shirt": {"home": False, "colors": ensure_colors(getattr(away_club, "colors", None))},
            },
        },
        "lineups": {
            "home": home_rows,
            "away": away_rows,
            "bench_home": bench_home,
            "bench_away": bench_away,
            "formation_home": record.formation_home,
            "formation_away": record.formation_away,
        },
        "events": events,
        "stats": _stats_with_defaults(record),
        "ratings_by_unit": record.ratings_by_unit or {
            "home": {},
            "away": {},
        },
        "tactics_report": _tactics_with_defaults(record, home_club, away_club, players),
        "awards": _awards_with_defaults(record),
    }


def _project_lineup_for_club(club: Club) -> Tuple[List[int], List[int]]:
    lineup: List[int] = []
    for pid in getattr(club, "preferred_lineup", []) or []:
        if pid and pid not in lineup:
            lineup.append(pid)
        if len(lineup) == 11:
            break
    roster_ids = [getattr(p, "id", None) for p in getattr(club, "players", []) or []]
    for pid in roster_ids:
        if pid and pid not in lineup and len(lineup) < 11:
            lineup.append(pid)
    bench = [pid for pid in roster_ids if pid and pid not in lineup]
    return lineup[:11], bench


def _match_details_for_fixture(
    gs: GameState,
    match_id: str,
    fixture: Tuple[str, Any, Any],
    clubs: Dict[str, Club],
    players: Dict[int, Player],
    team_ids: Dict[str, str],
) -> Dict[str, Any]:
    competition, division, match = fixture
    home = match.home
    away = match.away
    home_id = team_ids.get(home.name, _team_identifier(home))
    away_id = team_ids.get(away.name, _team_identifier(away))

    home_lineup, home_bench = _project_lineup_for_club(home)
    away_lineup, away_bench = _project_lineup_for_club(away)

    summary: Dict[int, Dict[str, Any]] = {}
    home_minutes = {pid: 0 for pid in home_lineup}
    away_minutes = {pid: 0 for pid in away_lineup}
    for pid in home_lineup:
        entry = _ensure_summary_entry(summary, pid)
        entry["minutes"] = 0
    for pid in away_lineup:
        entry = _ensure_summary_entry(summary, pid)
        entry["minutes"] = 0

    home_rows, bench_home = _lineup_rows(
        home,
        players,
        home_lineup,
        home_bench,
        home_minutes,
        {},
        summary,
    )
    away_rows, bench_away = _lineup_rows(
        away,
        players,
        away_lineup,
        away_bench,
        away_minutes,
        {},
        summary,
    )

    tactics = {
        "home": _snapshot_for_club(home, [players.get(pid) for pid in home_lineup]),
        "away": _snapshot_for_club(away, [players.get(pid) for pid in away_lineup]),
    }

    return {
        "match": {
            "id": match_id,
            "league": {
                "id": slugify(gs.league.name, prefix="L"),
                "name": gs.league.name,
                "season": gs.season,
                "round": int(getattr(match, "round", 0)),
            },
            "venue": {
                "stadium": getattr(home, "stadium_name", f"{home.name} Arena"),
                "city": None,
            },
            "datetime_utc": None,
            "referee": {"name": None, "skill": None, "hardness": None, "grade": None},
            "status": "scheduled",
            "score": {"home": 0, "away": 0, "ht_home": 0, "ht_away": 0},
        },
        "teams": {
            "home": {
                "id": home_id,
                "name": home.name,
                "shirt": {"home": True, "colors": ensure_colors(getattr(home, "colors", None))},
            },
            "away": {
                "id": away_id,
                "name": away.name,
                "shirt": {"home": False, "colors": ensure_colors(getattr(away, "colors", None))},
            },
        },
        "lineups": {
            "home": home_rows,
            "away": away_rows,
            "bench_home": bench_home,
            "bench_away": bench_away,
            "formation_home": tactics["home"].get("formation"),
            "formation_away": tactics["away"].get("formation"),
        },
        "events": [],
        "stats": _default_stats(),
        "ratings_by_unit": {"home": {}, "away": {}},
        "tactics_report": tactics,
        "awards": {"mom_home": None, "mom_away": None},
    }


def _build_match_details(gs: GameState, match_id: str) -> Dict[str, Any]:
    clubs, players, team_ids, divisions = _club_indexes(gs)
    record: Optional[MatchRecord] = None
    for idx, rec in enumerate(getattr(gs, "match_log", []) or []):
        candidate = _ensure_match_record_obj(rec)
        if _match_record_id(candidate) == match_id:
            record = candidate
            if not isinstance(rec, MatchRecord):
                # Uppdatera den inlästa listan så framtida användning
                # arbetar mot dataklassen.
                gs.match_log[idx] = candidate
            break
    if record is not None:
        return _match_details_from_record(gs, match_id, record, clubs, players, team_ids)

    fixture = _find_fixture(gs, match_id)
    if fixture is not None:
        return _match_details_for_fixture(gs, match_id, fixture, clubs, players, team_ids)

    raise ServiceError(f"Match '{match_id}' hittades inte.")


def _find_fixture(gs: GameState, match_id: str) -> Optional[Tuple[str, Any, Any]]:
    if not match_id:
        return None
    prefix = match_id.split("-", 1)[0]
    if prefix == "l":
        for division in gs.league.divisions:
            for match in gs.fixtures_by_division.get(division.name, []) or []:
                mid = _make_match_id("l", getattr(match, "round", 0), match.home.name, match.away.name)
                if mid == match_id:
                    return ("league", division, match)
    return None


def _rebuild_league_table(gs: GameState) -> None:
    table: Dict[str, Dict[str, int]] = {}
    for rec in getattr(gs, "match_log", []) or []:
        if getattr(rec, "competition", "league") != "league":
            continue
        home_row = table.setdefault(
            rec.home,
            {"mp": 0, "w": 0, "d": 0, "losses": 0, "gf": 0, "ga": 0, "pts": 0},
        )
        away_row = table.setdefault(
            rec.away,
            {"mp": 0, "w": 0, "d": 0, "losses": 0, "gf": 0, "ga": 0, "pts": 0},
        )
        home_row["mp"] += 1
        away_row["mp"] += 1
        home_row["gf"] += rec.home_goals
        home_row["ga"] += rec.away_goals
        away_row["gf"] += rec.away_goals
        away_row["ga"] += rec.home_goals
        if rec.home_goals > rec.away_goals:
            home_row["w"] += 1
            home_row["pts"] += 3
            away_row["losses"] += 1
        elif rec.home_goals < rec.away_goals:
            away_row["w"] += 1
            away_row["pts"] += 3
            home_row["losses"] += 1
        else:
            home_row["d"] += 1
            away_row["d"] += 1
            home_row["pts"] += 1
            away_row["pts"] += 1
    gs.table_snapshot = table
