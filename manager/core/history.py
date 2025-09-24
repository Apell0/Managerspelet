from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional


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

    # --- Serialisering -------------------------------------------------

    def to_dict(self) -> Dict[str, List[Dict[str, Any]]]:
        out: Dict[str, List[Dict[str, Any]]] = {}
        for club, records in self._store.items():
            serialised: List[Dict[str, Optional[int]]] = []
            for record in records:
                if isinstance(record, SeasonRecord):
                    serialised.append(asdict(record))
                elif isinstance(record, dict):
                    serialised.append(record)
            out[club] = serialised
        return out

    @classmethod
    def from_dict(cls, data: Dict[str, List[Dict[str, Any]]]) -> "HistoryStore":
        store = cls()
        for club, records in (data or {}).items():
            parsed: List[SeasonRecord] = []
            for record in records or []:
                if isinstance(record, SeasonRecord):
                    parsed.append(record)
                elif isinstance(record, dict):
                    try:
                        parsed.append(SeasonRecord(**record))
                    except TypeError:
                        continue
            if parsed:
                store._store[club] = parsed
        return store
