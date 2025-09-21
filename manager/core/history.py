from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(slots=True)
class SeasonRecord:
    season: int
    league_position: Optional[int] = None  # 1 = mästare, etc.
    cup_result: Optional[str] = None  # "Vinnare", "Final", "Semi", "Kvarts" etc.


class HistoryStore:
    """
    Enkel in-memory-butik. Nycklar: klubbnamn (str).
    I en riktig app skulle detta sparas till fil/databas.
    """

    def __init__(self) -> None:
        self._store: Dict[str, List[SeasonRecord]] = {}

    def add_record(self, club_name: str, record: SeasonRecord) -> None:
        self._store.setdefault(club_name, []).append(record)

    def last_record(self, club_name: str) -> Optional[SeasonRecord]:
        lst = self._store.get(club_name, [])
        return lst[-1] if lst else None

    def all_for(self, club_name: str) -> List[SeasonRecord]:
        return self._store.get(club_name, [])

    def snapshot(self) -> Dict[str, List[SeasonRecord]]:
        return self._store.copy()
