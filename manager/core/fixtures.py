from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .club import Club


@dataclass(slots=True)
class Match:
    home: Club
    away: Club
    round: int

    def __str__(self) -> str:
        return f"{self.round}: {self.home.name} vs {self.away.name}"


def round_robin(clubs: List[Club], double_round: bool = True) -> List[Match]:
    # Klassisk round-robin: varje lag möter varje lag en gång (eller två gånger)
    if len(clubs) < 2:
        return []

    n = len(clubs)
    if n % 2:
        clubs.append(None)  # bye om ojämnt antal
        n += 1

    schedule: List[List[tuple]] = []
    for i in range(n - 1):
        mid = n // 2
        l1 = clubs[:mid]
        l2 = clubs[mid:]
        l2.reverse()
        pairings = list(zip(l1, l2))
        schedule.append(pairings)
        clubs.insert(1, clubs.pop())

    matches: List[Match] = []
    round_num = 1
    for round_pairs in schedule:
        for home, away in round_pairs:
            if home is None or away is None:
                continue
            matches.append(Match(home=home, away=away, round=round_num))
        round_num += 1

    if double_round:
        extra = [
            Match(home=m.away, away=m.home, round=m.round + (round_num - 1))
            for m in matches
        ]
        matches.extend(extra)

    return matches
