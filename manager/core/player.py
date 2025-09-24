from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List


class Position(Enum):
    GK = "GK"
    DF = "DF"
    MF = "MF"
    FW = "FW"


class Trait(Enum):
    LEDARE = auto()
    INTELLIGENT = auto()
    SNABB = auto()
    UTHALLIG = auto()
    AGGRESSIV = auto()
    STRAFFSPECIALIST = auto()
    FRISPARKSSPECIALIST = auto()
    TRANINGSVILLIG = auto()
    SKADEBENAGEN = auto()  # negativ
    OJAMN = auto()  # negativ
    KORTBENAGEN = auto()  # negativ


@dataclass(slots=True)
class Player:
    id: int
    first_name: str
    last_name: str
    age: int
    position: Position
    number: int

    # Öppet betyg (1–30) och dold utvecklingspoäng (1–99)
    skill_open: int = 5
    skill_hidden: int = 50
    # Behåll legacy-fältet för kompatibilitet med äldre sparfiler/tester
    skill_xp: int = 50  # alias för äldre kodbaser

    # Form (placeholdervärden)
    form_now: int = 10  # 1–20
    form_season: int = 10  # 1–20

    traits: List[Trait] = field(default_factory=list)
    value_sek: int = 0

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"
