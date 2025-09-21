from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil
from typing import Dict, List, Optional

from .club import Club


@dataclass(slots=True)
class CupRules:
    """Regler för cupen."""

    two_legged: bool = True  # alla rundor dubbelmöte …
    final_two_legged: bool = False  # … utom finalen (default enkelmöte)


@dataclass(slots=True)
class CupMatch:
    home: Club
    away: Club
    round_name: str
    leg: int  # 1 eller 2 (finalens enkelmöte får leg=1)


@dataclass(slots=True)
class Cup:
    name: str
    rules: CupRules
    entrants: List[Club] = field(default_factory=list)
    bracket: Dict[str, List[CupMatch]] = field(
        default_factory=dict
    )  # round_name -> matcher


def _round_name(num_pairs: int) -> str:
    mapping = {
        1: "Final",
        2: "Semifinal",
        4: "Kvartsfinal",
        8: "Åttondel",
        16: "Sextondel",
        32: "Tretiotvåondel",
    }
    return mapping.get(num_pairs, f"Runda-{num_pairs*2}")


def _pad_to_power_of_two(clubs: List[Club]) -> List[Optional[Club]]:
    """Fyll upp med None (byes) till närmsta tvåpotens."""
    n = len(clubs)
    power = 1
    while power < n:
        power *= 2
    byes = power - n
    return clubs[:] + [None] * byes  # type: ignore[list-item]


def generate_cup_bracket(
    name: str, clubs: List[Club], rules: Optional[CupRules] = None
) -> Cup:
    """
    Skapar schema för en utslagscup:
    - Fyller upp till närmsta tvåpotens med byes
    - Alla rundor dubbelmöte om rules.two_legged=True, men finalen följer rules.final_two_legged
    - INGEN simulering; vi genererar bara matcher (legs) per runda
    """
    rules = rules or CupRules()
    padded: List[Optional[Club]] = _pad_to_power_of_two(clubs)
    cup = Cup(name=name, rules=rules, entrants=clubs[:], bracket={})

    # Starta med par (a,b) i första spelbara runda
    pairs: List[tuple[Optional[Club], Optional[Club]]] = []
    for i in range(0, len(padded), 2):
        pairs.append((padded[i], padded[i + 1]))

    while True:
        # Ta bort helt tomma byes (None,None) i utskriften, men behåll längden för rundnamn
        real_pairs = [(a, b) for (a, b) in pairs if (a is not None or b is not None)]
        num_pairs = len(real_pairs)
        if num_pairs == 0:
            break  # inget mer att schemalägga

        round_name = _round_name(num_pairs)
        is_final = num_pairs == 1
        legs = (
            1
            if (is_final and not rules.final_two_legged)
            else (2 if rules.two_legged else 1)
        )

        matches: List[CupMatch] = []
        for a, b in real_pairs:
            # Byes: laget utan motstånd går vidare utan match; ingen CupMatch behövs
            if a is None or b is None:
                continue
            if legs == 1:
                matches.append(CupMatch(home=a, away=b, round_name=round_name, leg=1))
            else:
                matches.append(CupMatch(home=a, away=b, round_name=round_name, leg=1))
                matches.append(CupMatch(home=b, away=a, round_name=round_name, leg=2))

        cup.bracket[round_name] = matches

        if is_final:
            break

        # Nästa runda kräver hälften så många par (vinnare per par). Vi behöver inte veta vilka –
        # vi reducerar bara antalet par till ceil(num_pairs/2) och använder placeholders (None,None).
        next_pairs_count = ceil(num_pairs / 2)
        pairs = [(None, None) for _ in range(next_pairs_count)]

    return cup
