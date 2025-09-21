from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional

from .club import Club
from .player import Player, Position, Trait

# ---------------------------------
# Händelsetyper
# ---------------------------------


class EventType(Enum):
    GOAL = auto()
    SHOT_ON = auto()
    SHOT_OFF = auto()
    SAVE = auto()
    WOODWORK = auto()
    CORNER = auto()
    FOUL = auto()
    YELLOW = auto()
    RED = auto()
    PENALTY_AWARDED = auto()
    PENALTY_SCORED = auto()
    PENALTY_MISSED = auto()
    OFFSIDE = auto()
    INJURY = auto()
    SUBSTITUTION = auto()


# ---------------------------------
# Domare
# ---------------------------------


@dataclass(slots=True)
class Referee:
    skill: int = 6  # 1–10 (högre: bättre bedömningar)
    hardness: int = 5  # 1–10 (högre: fler kort / mer strikt)


# ---------------------------------
# Matchstatistik (per lag)
# ---------------------------------


@dataclass(slots=True)
class TeamStats:
    goals: int = 0
    shots: int = 0
    shots_on: int = 0
    saves: int = 0
    woodwork: int = 0
    corners: int = 0
    fouls: int = 0
    offsides: int = 0
    yellows: int = 0
    reds: int = 0
    possession_pct: int = 50  # sätts efter simuleringen


# ---------------------------------
# Matchresultat + händelser
# ---------------------------------


@dataclass(slots=True)
class PlayerEvent:
    event: EventType
    minute: int
    player: Optional[Player] = None
    assist_by: Optional[Player] = None
    note: Optional[str] = None


@dataclass(slots=True)
class MatchResult:
    home: Club
    away: Club
    events: List[PlayerEvent]
    home_stats: TeamStats
    away_stats: TeamStats
    ratings: Dict[int, float] = field(default_factory=dict)

    @property
    def scoreline(self) -> str:
        return f"{self.home_stats.goals}-{self.away_stats.goals}"


# ---------------------------------
# Hjälpfunktioner
# ---------------------------------


def _avg_skill(players: List[Player]) -> float:
    if not players:
        return 5.0
    return sum(getattr(p, "skill_open", 5) for p in players) / len(players)


def _pick_lineup(club: Club, n: int = 11) -> List[Player]:
    """Enkel elvaväljare: ta de första 11, fyll upp med slump om färre."""
    ps = list(club.players)
    if len(ps) >= n:
        return ps[:n]
    while len(ps) < n and club.players:
        ps.append(random.choice(club.players))
    return ps[:n]


def _choose_weighted(players: List[Player], role: str) -> Player:
    """
    Välj en spelare med vikt beroende på position/roll:
    - scorer: FW > MF > DF > GK
    - assister: MF > FW > DF > GK
    """
    weights = []
    for p in players:
        pos = getattr(p, "position", None)
        base = 1.0
        if role == "scorer":
            if pos == Position.FW:
                base = 6.0
            elif pos == Position.MF:
                base = 3.0
            elif pos == Position.DF:
                base = 1.5
            else:
                base = 0.3
        else:  # assister
            if pos == Position.MF:
                base = 6.0
            elif pos == Position.FW:
                base = 3.0
            elif pos == Position.DF:
                base = 1.3
            else:
                base = 0.2

        base *= 0.8 + 0.02 * getattr(p, "skill_open", 5)
        if role == "scorer" and Trait.STRAFFSPECIALIST in getattr(p, "traits", []):
            base *= 1.15
        if role == "assister" and Trait.INTELLIGENT in getattr(p, "traits", []):
            base *= 1.10
        weights.append(max(0.05, base))

    r = random.random() * sum(weights)
    acc = 0.0
    for p, w in zip(players, weights):
        acc += w
        if r <= acc:
            return p
    return random.choice(players)


def _keeper_skill(players: List[Player]) -> float:
    """Bästa GK i elvan, annars låg nivå."""
    gks = [p for p in players if getattr(p, "position", None) == Position.GK]
    if not gks:
        return 4.5
    return max(getattr(p, "skill_open", 5) for p in gks)


def _poisson(lmbd: float) -> int:
    """Knuths algoritm för Poisson-dragning."""
    L = math.exp(-lmbd)
    k = 0
    p = 1.0
    while True:
        k += 1
        p *= random.random()
        if p <= L:
            return k - 1


# ---------------------------------
# Simulering (Poisson-kalibrerad med tempo)
# ---------------------------------


def simulate_match(
    home: Club,
    away: Club,
    *,
    referee: Referee,
    home_tactic,
    away_tactic,
    home_aggr,
    away_aggr,
) -> MatchResult:
    """
    Poisson-styrd målmodell:
      1) Beräkna förväntade mål (xG) för båda lagen från relativ styrka + taktik + hemmabonus + TEMPO
      2) Dra antal mål ur Poisson
      3) Syntetisera skott/avslut/saves/hörnor mm. konsekvent med antalet mål
      4) Tilldela målskytt/assist och händelsetider
      5) Kort/fouls/straffar/offsides/skador m.m.
      6) Spelar-betyg från prestation
    """
    # 1) Elvor och grundparametrar
    home_xi = _pick_lineup(home)
    away_xi = _pick_lineup(away)

    sH = _avg_skill(home_xi)
    sA = _avg_skill(away_xi)
    gkH = _keeper_skill(home_xi)
    gkA = _keeper_skill(away_xi)

    # Hemmabonus och taktik
    strength_diff = sH - sA
    home_bonus = 0.12  # ~0.12 mål i snitt
    tacH = (
        0.10
        if getattr(home_tactic, "attacking", False)
        else (-0.05 if getattr(home_tactic, "defending", False) else 0.0)
    )
    tacA = (
        0.10
        if getattr(away_tactic, "attacking", False)
        else (-0.05 if getattr(away_tactic, "defending", False) else 0.0)
    )

    # Keeper påverkar negativt motståndarnas xG
    gk_effect_on_A = -0.06 * (gkH - 5)  # bättre hemmakeeper → lägre xG för bortalag
    gk_effect_on_H = -0.06 * (gkA - 5)

    # Basnivåer (ligasnitt ~2.6 totalt)
    base_home = 1.35
    base_away = 1.15

    # Tempo (0.8–1.2 typiskt)
    tempoH = float(getattr(home_tactic, "tempo", 1.0) or 1.0)
    tempoA = float(getattr(away_tactic, "tempo", 1.0) or 1.0)

    xg_home = (
        base_home + 0.18 * strength_diff + home_bonus + tacH + gk_effect_on_A
    ) * tempoH
    xg_away = (base_away - 0.18 * strength_diff + tacA + gk_effect_on_H) * tempoA

    # Offsidefälla minskar något
    if getattr(home_tactic, "offside_trap", False):
        xg_away *= 0.94
    if getattr(away_tactic, "offside_trap", False):
        xg_home *= 0.94

    # Clamp rimligt intervall
    xg_home = max(0.2, min(3.2, xg_home))
    xg_away = max(0.2, min(3.2, xg_away))

    # 2) Dra antal mål
    goals_home = _poisson(xg_home)
    goals_away = _poisson(xg_away)

    # 3) Syntetisera skott/avslut mm. utifrån mål
    # Skapa rimliga totalsiffror: ca 8–16 skott/lag, ~30–40% on target, 60–80% saves av on-target
    def synth_stats(goals: int, xg: float, gk_vs: float) -> TeamStats:
        shots = max(3, int(random.gauss(10 + 2 * (xg - 1.0), 2.8)))
        on_ratio = 0.30 + 0.04 * (xg - 1.0)  # 26–40 %
        shots_on = max(goals, int(shots * max(0.22, min(0.42, on_ratio))))
        # säkra att skott på mål >= mål
        shots_on = max(shots_on, goals)
        save_ratio = 0.62 + 0.04 * (gk_vs - 5)  # bättre keeper → fler räddningar
        saves = max(
            0, min(shots_on - goals, int(shots_on * max(0.45, min(0.90, save_ratio))))
        )
        corners = max(0, int(shots * random.uniform(0.15, 0.30)))
        woodwork = 1 if random.random() < 0.08 else 0
        offsides = int(random.random() < 0.25) + (1 if random.random() < 0.15 else 0)

        return TeamStats(
            goals=goals,
            shots=shots,
            shots_on=shots_on,
            saves=saves,
            woodwork=woodwork,
            corners=corners,
            fouls=0,  # fylls nedan
            offsides=offsides,
            yellows=0,
            reds=0,
        )

    H = synth_stats(goals_home, xg_home, gkA)
    A = synth_stats(goals_away, xg_away, gkH)

    # 4) Bygg händelser tidslinje (mål först, fyll sedan på)
    events: List[PlayerEvent] = []

    def add_goals(team_players: List[Player], goals: int):
        minutes = sorted(
            random.sample(range(2, 90), k=min(goals, 8))
        )  # max 8 tidsstämplar, flera mål kan hamna i samma minut
        if goals > len(minutes):
            extra = [random.choice(minutes) for _ in range(goals - len(minutes))]
            minutes += extra
            minutes.sort()
        for m in minutes:
            scorer = _choose_weighted(team_players, "scorer")
            assister = None
            if random.random() < 0.60:  # assist ganska vanligt
                pool = [p for p in team_players if p is not scorer]
                assister = _choose_weighted(pool, "assister") if pool else None
            events.append(PlayerEvent(EventType.GOAL, m, scorer, assist_by=assister))

    add_goals(home_xi, goals_home)
    add_goals(away_xi, goals_away)

    # 5) Fouls, kort, straffar, offsides, woodwork, hörnor fördelas runt
    def distribute_misc(team_players: List[Player], stats: TeamStats, is_home: bool):
        # fouls/kort
        aggr = getattr(home_aggr if is_home else away_aggr, "name", "Medel").lower()
        aggr_factor = 1.25 if "aggress" in aggr else (0.85 if "lugn" in aggr else 1.0)
        base_fouls = int(random.gauss(10, 3))
        fouls = max(4, int(base_fouls * aggr_factor))
        stats.fouls = fouls
        for _ in range(fouls):
            minute = random.randint(3, 88)
            victim = random.choice(team_players)
            events.append(PlayerEvent(EventType.FOUL, minute, victim))
            # kortbedömning
            if random.random() < 0.10 * aggr_factor * (
                1 + 0.06 * (referee.hardness - 5)
            ):
                stats.yellows += 1
                events.append(PlayerEvent(EventType.YELLOW, minute, victim))
                if random.random() < 0.08:  # andra gula
                    stats.reds += 1
                    events.append(PlayerEvent(EventType.RED, minute, victim))

        # straffar – mer sällan (ca 0.1–0.2 / match)
        if random.random() < 0.12:
            minute = random.randint(5, 85)
            taker = next(
                (
                    p
                    for p in team_players
                    if Trait.STRAFFSPECIALIST in getattr(p, "traits", [])
                ),
                None,
            )
            if not taker:
                taker = _choose_weighted(team_players, "scorer")
            events.append(PlayerEvent(EventType.PENALTY_AWARDED, minute, taker))
            gk = gkA if is_home else gkH
            p_score = 0.74 - 0.02 * (gk - 5)
            if random.random() < p_score:
                stats.goals += 1
                events.append(PlayerEvent(EventType.PENALTY_SCORED, minute, taker))
                events.append(PlayerEvent(EventType.GOAL, minute, taker))
            else:
                events.append(PlayerEvent(EventType.PENALTY_MISSED, minute, taker))

        # offsides och woodwork/hörnor – synka mot stats (lägg “markörer” i tidslinjen)
        for _ in range(stats.offsides):
            events.append(
                PlayerEvent(
                    EventType.OFFSIDE,
                    random.randint(2, 88),
                    _choose_weighted(team_players, "scorer"),
                )
            )
        for _ in range(stats.woodwork):
            events.append(
                PlayerEvent(
                    EventType.WOODWORK,
                    random.randint(2, 88),
                    _choose_weighted(team_players, "scorer"),
                )
            )
        for _ in range(stats.corners):
            events.append(PlayerEvent(EventType.CORNER, random.randint(2, 88)))

    distribute_misc(home_xi, H, True)
    distribute_misc(away_xi, A, False)

    # 6) Skador & symboliska byten (robust traitnamn)
    def injuries(block: List[Player]) -> None:
        n = 0
        for p in block:
            risk = 0.003
            traits = getattr(p, "traits", []) or []
            trait_names = {getattr(t, "name", str(t)).upper() for t in traits}
            if {"SKADEBENÄGEN", "SKADBENÄGEN", "SKADEBENAGEN"} & trait_names:
                risk += 0.010
            if random.random() < risk:
                n += 1
                events.append(PlayerEvent(EventType.INJURY, random.randint(10, 85), p))
        for _ in range(n):
            events.append(PlayerEvent(EventType.SUBSTITUTION, random.randint(12, 88)))

    injuries(home_xi)
    injuries(away_xi)

    # 7) Bollinnehav (grovt av styrka och skott)
    total_shots = max(1, H.shots + A.shots)
    posH = int(50 + 8 * (sH - sA) + 4 * (H.shots - A.shots) / total_shots)
    H.possession_pct = max(30, min(70, posH))
    A.possession_pct = 100 - H.possession_pct

    # 8) Spelar-betyg 5.0–9.5 (mål/assist upp, rött/gult ner, traits påverkar lite)
    ratings: Dict[int, float] = {}
    impact: Dict[int, float] = {p.id: 0.0 for p in home_xi + away_xi}
    for ev in events:
        if ev.event is EventType.GOAL and ev.player:
            impact[ev.player.id] = impact.get(ev.player.id, 0.0) + 0.9
            if ev.assist_by:
                impact[ev.assist_by.id] = impact.get(ev.assist_by.id, 0.0) + 0.4
        elif ev.event is EventType.RED and ev.player:
            impact[ev.player.id] = impact.get(ev.player.id, 0.0) - 1.0
        elif ev.event is EventType.YELLOW and ev.player:
            impact[ev.player.id] = impact.get(ev.player.id, 0.0) - 0.2

    for p in home_xi + away_xi:
        base = (
            6.2 + 0.12 * (getattr(p, "skill_open", 5) - 5) + random.uniform(-0.6, 0.6)
        )
        base += impact.get(p.id, 0.0)
        if Trait.LEDARE in getattr(p, "traits", []):
            base += 0.1
        if Trait.AGGRESSIV in getattr(p, "traits", []):
            base -= 0.05
        ratings[p.id] = float(max(5.0, min(9.5, base)))

    # 9) Sortera händelser och returnera
    events.sort(key=lambda e: e.minute)
    return MatchResult(
        home=home,
        away=away,
        events=events,
        home_stats=H,
        away_stats=A,
        ratings=ratings,
    )
