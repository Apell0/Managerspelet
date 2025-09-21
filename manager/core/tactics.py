from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Tuple

from .club import Club
from .player import Position


class Aggression(Enum):
    LUGN = "lugn"
    MEDEL = "medel"
    AGGRESSIV = "aggressiv"


class TacticName(Enum):
    BALANCED_442 = "balanced_442"
    DEFENSIVE_451 = "defensive_451"
    ATTACKING_433 = "attacking_433"
    HIGH_PRESS_4231 = "high_press_4231"
    COUNTER_4141 = "counter_4141"


@dataclass(slots=True)
class TacticProfile:
    name: TacticName
    # Viktning för lagdelar (summa ~1.0 är lagom, men behöver inte vara exakt)
    w_gk: float
    w_def: float
    w_mid: float
    w_fwd: float
    # Basbonusar/malus (små justeringar i målchans)
    base_off_bonus: float = 0.0  # påverkar målframåt (0.95–1.05 typ)
    base_def_bonus: float = (
        0.0  # påverkar mål bakåt (0.95–1.05, där <1 är bra för defensiven)
    )


# En liten uppsättning standardtaktiker
TACTICS: Dict[TacticName, TacticProfile] = {
    TacticName.BALANCED_442: TacticProfile(
        name=TacticName.BALANCED_442,
        w_gk=0.20,
        w_def=0.30,
        w_mid=0.30,
        w_fwd=0.20,
        base_off_bonus=1.00,
        base_def_bonus=1.00,
    ),
    TacticName.DEFENSIVE_451: TacticProfile(
        name=TacticName.DEFENSIVE_451,
        w_gk=0.22,
        w_def=0.35,
        w_mid=0.28,
        w_fwd=0.15,
        base_off_bonus=0.97,
        base_def_bonus=0.98,
    ),
    TacticName.ATTACKING_433: TacticProfile(
        name=TacticName.ATTACKING_433,
        w_gk=0.18,
        w_def=0.26,
        w_mid=0.28,
        w_fwd=0.28,
        base_off_bonus=1.03,
        base_def_bonus=1.02,
    ),
    TacticName.HIGH_PRESS_4231: TacticProfile(
        name=TacticName.HIGH_PRESS_4231,
        w_gk=0.18,
        w_def=0.28,
        w_mid=0.34,
        w_fwd=0.20,
        base_off_bonus=1.02,
        base_def_bonus=1.03,
    ),
    TacticName.COUNTER_4141: TacticProfile(
        name=TacticName.COUNTER_4141,
        w_gk=0.20,
        w_def=0.32,
        w_mid=0.30,
        w_fwd=0.18,
        base_off_bonus=0.99,
        base_def_bonus=0.98,
    ),
}

# Enkel “rock–paper–scissors”-liknande matrix (hemmaTaktik, bortaTaktik) -> multiplicerare på hemma lagets offensiv
# Notera: bortalaget får motsatt effekt (1 / multiplikatorn) när vi räknar på bortalagets offensiv.
COUNTER_MATRIX: Dict[Tuple[TacticName, TacticName], float] = {
    # 442 neutral men får liten fördel mot mycket offensiva 433
    (TacticName.BALANCED_442, TacticName.ATTACKING_433): 1.03,
    (TacticName.ATTACKING_433, TacticName.BALANCED_442): 0.98,
    # 451 stänger ner 433 lite
    (TacticName.DEFENSIVE_451, TacticName.ATTACKING_433): 1.05,
    (TacticName.ATTACKING_433, TacticName.DEFENSIVE_451): 0.96,
    # 4231 press stör 451 uppspel
    (TacticName.HIGH_PRESS_4231, TacticName.DEFENSIVE_451): 1.04,
    (TacticName.DEFENSIVE_451, TacticName.HIGH_PRESS_4231): 0.97,
    # 4141 kontrar gärna mot 4231
    (TacticName.COUNTER_4141, TacticName.HIGH_PRESS_4231): 1.04,
    (TacticName.HIGH_PRESS_4231, TacticName.COUNTER_4141): 0.97,
    # 4141 vs 433 ok kontrayta
    (TacticName.COUNTER_4141, TacticName.ATTACKING_433): 1.02,
    (TacticName.ATTACKING_433, TacticName.COUNTER_4141): 0.99,
}


def _avg_by_position(club: Club, pos: Position) -> float:
    pool = [p.skill_open for p in club.players if p.position is pos]
    return (sum(pool) / len(pool)) if pool else 5.0


def unit_scores(club: Club, tactic: TacticProfile) -> Tuple[float, float, float, float]:
    """
    Returnerar (GK, DEF, MID, FWD) som vägt med spelarstyrka.
    Värdena är inte begränsade men kommer typiskt ligga kring 3–8.
    """
    gk = _avg_by_position(club, Position.GK)
    df = _avg_by_position(club, Position.DF)
    mf = _avg_by_position(club, Position.MF)
    fw = _avg_by_position(club, Position.FW)

    # Väg ihop med taktikvikter
    return (
        gk * tactic.w_gk,
        df * tactic.w_def,
        mf * tactic.w_mid,
        fw * tactic.w_fwd,
    )


def aggression_modifiers(agg: Aggression) -> Tuple[float, float]:
    """
    Returnerar (offensiv_multiplikator, kort_multiplikator).
    LUGN ger färre kort, AGGRESSIV ger fler kort samt liten offensiv boost.
    """
    if agg is Aggression.LUGN:
        return (0.99, 0.85)
    if agg is Aggression.MEDEL:
        return (1.00, 1.00)
    if agg is Aggression.AGGRESSIV:
        return (1.02, 1.20)
    return (1.00, 1.00)
