from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

from .cup_state import CupState
from .fixtures import Match
from .history import HistoryStore, SeasonRecord
from .league import League
from .serialize import (
    cup_state_from_dict,
    cup_state_to_dict,
    fixtures_from_dict,
    fixtures_to_dict,
    league_from_dict,
    league_to_dict,
)
from .stats import ClubSeasonStats, MatchRecord, PlayerSeasonStats


@dataclass(slots=True)
class GameState:
    season: int
    league: League
    fixtures_by_division: Dict[str, List[Match]]
    current_round: int
    history: HistoryStore
    cup_state: Optional[CupState] = None

    # 9.2: nya fält
    table_snapshot: Dict[str, dict] = None  # club_name -> {mp,w,d,l,gf,ga,pts}
    player_stats: Dict[int, PlayerSeasonStats] = None  # player_id -> stats
    club_stats: Dict[str, ClubSeasonStats] = None  # club_name -> stats
    match_log: List[MatchRecord] = None  # kronologisk logg

    def ensure_containers(self) -> None:
        if self.table_snapshot is None:
            self.table_snapshot = {}
        if self.player_stats is None:
            self.player_stats = {}
        if self.club_stats is None:
            self.club_stats = {}
        if self.match_log is None:
            self.match_log = []

    # -------- (de)serialisering --------

    def to_dict(self) -> dict:
        self.ensure_containers()
        return {
            "season": self.season,
            "league": league_to_dict(self.league),
            "fixtures": fixtures_to_dict(self.fixtures_by_division),
            "current_round": self.current_round,
            "history": self.history.snapshot(),
            "cup": cup_state_to_dict(self.cup_state),
            "table_snapshot": self.table_snapshot,
            "player_stats": {
                pid: asdict(ps) | {"rating_avg": ps.rating_avg}
                for pid, ps in self.player_stats.items()
            },
            "club_stats": {name: asdict(cs) for name, cs in self.club_stats.items()},
            "match_log": [asdict(mr) for mr in self.match_log],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GameState":
        league = league_from_dict(d["league"])
        fixtures = fixtures_from_dict(league, d["fixtures"])

        hist = HistoryStore()
        for club, recs in d.get("history", {}).items():
            for r in recs:
                hist.add_record(
                    club,
                    SeasonRecord(
                        season=int(r["season"]),
                        league_position=(
                            None
                            if r.get("league_position") is None
                            else int(r["league_position"])
                        ),
                        cup_result=r.get("cup_result"),
                    ),
                )

        cup = cup_state_from_dict(league, d.get("cup"))

        gs = cls(
            season=int(d["season"]),
            league=league,
            fixtures_by_division=fixtures,
            current_round=int(d["current_round"]),
            history=hist,
            cup_state=cup,
        )
        gs.table_snapshot = d.get("table_snapshot", {}) or {}
        # player_stats
        pst = {}
        for pid_str, ps in (d.get("player_stats") or {}).items():
            pid = int(pid_str) if isinstance(pid_str, str) else int(pid_str)
            pst[pid] = PlayerSeasonStats(
                player_id=pid,
                club_name=ps["club_name"],
                appearances=int(ps.get("appearances", 0)),
                minutes=int(ps.get("minutes", 0)),
                goals=int(ps.get("goals", 0)),
                assists=int(ps.get("assists", 0)),
                yellows=int(ps.get("yellows", 0)),
                reds=int(ps.get("reds", 0)),
                rating_sum=float(ps.get("rating_sum", 0.0)),
                rating_count=int(ps.get("rating_count", 0)),
            )
        gs.player_stats = pst

        # club_stats
        cst = {}
        for name, cs in (d.get("club_stats") or {}).items():
            cst[name] = ClubSeasonStats(
                club_name=name,
                played=int(cs.get("played", 0)),
                wins=int(cs.get("wins", 0)),
                draws=int(cs.get("draws", 0)),
                losses=int(cs.get("losses", 0)),
                goals_for=int(cs.get("goals_for", 0)),
                goals_against=int(cs.get("goals_against", 0)),
                clean_sheets=int(cs.get("clean_sheets", 0)),
                yellows=int(cs.get("yellows", 0)),
                reds=int(cs.get("reds", 0)),
            )
        gs.club_stats = cst

        # match_log
        mlog: List[MatchRecord] = []
        for md in d.get("match_log") or []:
            mlog.append(
                MatchRecord(
                    competition=md["competition"],
                    round=int(md["round"]),
                    home=md["home"],
                    away=md["away"],
                    home_goals=int(md["home_goals"]),
                    away_goals=int(md["away_goals"]),
                    events=list(md.get("events", [])),
                    ratings={
                        int(pid): float(r)
                        for pid, r in (md.get("ratings", {}) or {}).items()
                    },
                )
            )
        gs.match_log = mlog
        gs.ensure_containers()
        return gs

    # -------- spara/ladda --------

    def save(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str) -> "GameState":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)
