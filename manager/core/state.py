from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .fixtures import Match
from .history import HistoryStore
from .league import League
from .transfer import JuniorOffer, TransferListing

# serialize.py som källa
from .serialize import (
    fixtures_from_dict,
    league_from_dict,
)
from .serialize import (
    game_state_from_dict as deserialize_game_state,
)
from .serialize import (
    game_state_to_dict as serialize_game_state,
    junior_offers_from_dict,
    junior_offers_to_dict,
    match_log_from_dict_list,
    transfer_list_from_dict,
    transfer_list_to_dict,
)


@dataclass(slots=True)
class GameState:
    season: int
    league: League
    fixtures_by_division: Dict[str, List[Match]]
    current_round: int = 1

    cup_state: Optional[Any] = None
    history: HistoryStore = field(default_factory=HistoryStore)

    meta: Dict[str, Any] = field(
        default_factory=lambda: {"version": "1.0", "career_id": f"c-{uuid4().hex[:8]}"}
    )
    options: Dict[str, Any] = field(
        default_factory=lambda: {"cheats": False, "graphics": {"quality": "medium"}}
    )
    season_phase: str = "preseason"
    calendar_week: int = 1

    table_snapshot: Dict[str, Any] = field(default_factory=dict)
    player_stats: Dict[int, Any] = field(default_factory=dict)
    player_career_stats: Dict[int, Any] = field(default_factory=dict)
    club_stats: Dict[str, Any] = field(default_factory=dict)
    club_career_stats: Dict[str, Any] = field(default_factory=dict)
    match_log: List[Any] = field(default_factory=list)
    player_stats_history: Dict[int, Any] = field(default_factory=dict)
    club_stats_history: Dict[int, Any] = field(default_factory=dict)

    # NYTT: träningsordrar och ekonomi/mail
    training_orders: List[Any] = field(default_factory=list)
    transfer_list: List[TransferListing] = field(default_factory=list)
    junior_offers: Dict[str, List[JuniorOffer]] = field(default_factory=dict)
    economy_ledger: List[Dict[str, Any]] = field(default_factory=list)
    mailbox: List[Dict[str, Any]] = field(default_factory=list)

    def ensure_containers(self) -> None:
        if self.table_snapshot is None:
            self.table_snapshot = {}
        if self.player_stats is None:
            self.player_stats = {}
        if not hasattr(self, "player_career_stats"):
            self.player_career_stats = {}
        if self.player_career_stats is None:
            self.player_career_stats = {}
        if self.club_stats is None:
            self.club_stats = {}
        if not hasattr(self, "club_career_stats"):
            self.club_career_stats = {}
        if self.club_career_stats is None:
            self.club_career_stats = {}
        if self.match_log is None:
            self.match_log = []
        if not hasattr(self, "player_stats_history"):
            self.player_stats_history = {}
        if self.player_stats_history is None:
            self.player_stats_history = {}
        if not hasattr(self, "club_stats_history"):
            self.club_stats_history = {}
        if self.club_stats_history is None:
            self.club_stats_history = {}
        if not hasattr(self, "training_orders"):
            self.training_orders = []
        if self.training_orders is None:
            self.training_orders = []
        if self.history is None:
            self.history = HistoryStore()
        if not hasattr(self, "transfer_list"):
            self.transfer_list = []
        if self.transfer_list is None:
            self.transfer_list = []
        if not hasattr(self, "junior_offers"):
            self.junior_offers = {}
        if self.junior_offers is None:
            self.junior_offers = {}
        if not hasattr(self, "meta") or not isinstance(self.meta, dict):
            self.meta = {"version": "1.0", "career_id": f"c-{uuid4().hex[:8]}"}
        if "version" not in self.meta:
            self.meta["version"] = "1.0"
        if "career_id" not in self.meta or not self.meta["career_id"]:
            self.meta["career_id"] = f"c-{uuid4().hex[:8]}"
        if not hasattr(self, "options") or not isinstance(self.options, dict):
            self.options = {"cheats": False, "graphics": {"quality": "medium"}}
        if not hasattr(self, "season_phase"):
            self.season_phase = "in_progress"
        if not hasattr(self, "calendar_week"):
            self.calendar_week = 1
        if not hasattr(self, "economy_ledger") or self.economy_ledger is None:
            self.economy_ledger = []
        if not hasattr(self, "mailbox") or self.mailbox is None:
            self.mailbox = []

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as f:
            json.dump(serialize_game_state(self), f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str | Path) -> "GameState":
        p = Path(path)
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GameState":
        if "fixtures_by_division" in data:
            league = league_from_dict(data["league"])
            fixtures = fixtures_from_dict(data["fixtures_by_division"], league)
            gs = cls(
                season=int(data.get("season", 1)),
                league=league,
                fixtures_by_division=fixtures,
                current_round=int(data.get("current_round", 1)),
                history=HistoryStore(),
                cup_state=None,
            )
            gs.meta = data.get("meta", {}) or {
                "version": "1.0",
                "career_id": f"c-{uuid4().hex[:8]}",
            }
            gs.options = data.get("options", {}) or {
                "cheats": False,
                "graphics": {"quality": "medium"},
            }
            gs.season_phase = data.get("season_phase", "in_progress") or "in_progress"
            gs.calendar_week = int(data.get("calendar_week", 1))
            gs.table_snapshot = data.get("table_snapshot", {}) or {}
            gs.player_stats = data.get("player_stats", {}) or {}
            gs.player_career_stats = data.get("player_career_stats", {}) or {}
            gs.club_stats = data.get("club_stats", {}) or {}
            gs.club_career_stats = data.get("club_career_stats", {}) or {}
            gs.match_log = match_log_from_dict_list(data.get("match_log", []))
            gs.training_orders = data.get("training_orders", []) or []
            gs.transfer_list = transfer_list_from_dict(data.get("transfer_list", []))
            gs.junior_offers = junior_offers_from_dict(data.get("junior_offers", {}))
            gs.player_stats_history = data.get("player_stats_history", {}) or {}
            gs.club_stats_history = data.get("club_stats_history", {}) or {}
            gs.economy_ledger = data.get("economy_ledger", []) or []
            gs.mailbox = data.get("mailbox", []) or []
            gs.ensure_containers()
            return gs
        return deserialize_game_state(data)

    def to_dict(self) -> Dict[str, Any]:
        return serialize_game_state(self)
