from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .fixtures import Match
from .history import HistoryStore
from .league import League

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
)


@dataclass(slots=True)
class GameState:
    season: int
    league: League
    fixtures_by_division: Dict[str, List[Match]]
    current_round: int = 1

    cup_state: Optional[Any] = None
    history: HistoryStore = field(default_factory=HistoryStore)

    table_snapshot: Dict[str, Any] = field(default_factory=dict)
    player_stats: Dict[int, Any] = field(default_factory=dict)
    club_stats: Dict[str, Any] = field(default_factory=dict)
    match_log: List[Any] = field(default_factory=list)

    # NYTT: träningsordrar
    training_orders: List[Any] = field(default_factory=list)

    def ensure_containers(self) -> None:
        if self.table_snapshot is None:
            self.table_snapshot = {}
        if self.player_stats is None:
            self.player_stats = {}
        if self.club_stats is None:
            self.club_stats = {}
        if self.match_log is None:
            self.match_log = []
        if self.training_orders is None:
            self.training_orders = []
        if self.history is None:
            self.history = HistoryStore()

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
            gs.table_snapshot = data.get("table_snapshot", {}) or {}
            gs.player_stats = data.get("player_stats", {}) or {}
            gs.club_stats = data.get("club_stats", {}) or {}
            gs.match_log = data.get("match_log", []) or []
            gs.training_orders = data.get("training_orders", []) or []
            gs.ensure_containers()
            return gs
        return deserialize_game_state(data)

    def to_dict(self) -> Dict[str, Any]:
        return serialize_game_state(self)
