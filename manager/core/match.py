from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional

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


REFEREE_NAMES = [
    "Hugh Cango",
    "Mia Jones",
    "Lars Fogel",
    "Ann Field",
    "Per Sann",
    "Rita Blow",
    "Ivo Stripe",
    "Eli Don",
    "Nina Gauge",
    "Gunnar Holm",
]


@dataclass(slots=True)
class Referee:
    skill: int = 6  # 1–10 (högre: bättre bedömningar)
    hardness: int = 5  # 1–10 (högre: fler kort / mer strikt)
    name: str = "Domare"


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
    home_minutes: Dict[int, int] = field(default_factory=dict)
    away_minutes: Dict[int, int] = field(default_factory=dict)
    home_lineup: List[Player] = field(default_factory=list)
    away_lineup: List[Player] = field(default_factory=list)
    home_bench: List[Player] = field(default_factory=list)
    away_bench: List[Player] = field(default_factory=list)
    home_dark_arts: bool = False
    away_dark_arts: bool = False
    referee: Referee | None = None
    home_ht_goals: int = 0
    away_ht_goals: int = 0
    stats_extra: Dict[str, Any] = field(default_factory=dict)
    ratings_by_unit: Dict[str, Dict[str, int]] = field(default_factory=dict)
    tactic_snapshot: Dict[str, Any] = field(default_factory=dict)
    awards: Dict[str, Any] = field(default_factory=dict)

    @property
    def scoreline(self) -> str:
        return f"{self.home_stats.goals}-{self.away_stats.goals}"


# ---------------------------------
# Matchplan (lineup & byten)
# ---------------------------------


@dataclass(slots=True)
class ScheduledSub:
    minute: int
    player_in: Player
    player_out_id: Optional[int] = None
    position: Optional[str] = None
    reason: str = ""


# ---------------------------------
# Hjälpfunktioner
# ---------------------------------


def _avg_skill(players: List[Player]) -> float:
    if not players:
        return 5.0
    return sum(getattr(p, "skill_open", 5) for p in players) / len(players)


def _player_display_name(player: Player) -> str:
    name = getattr(player, "full_name", "")
    if name:
        return name
    first = getattr(player, "first_name", "")
    last = getattr(player, "last_name", "")
    combo = f"{first} {last}".strip()
    return combo or f"#{getattr(player, 'number', '?')}"


def player_event_summary(
    events: List[PlayerEvent],
) -> Dict[int, Dict[str, Any]]:
    summary: Dict[int, Dict[str, Any]] = {}

    def ensure(player: Optional[Player]) -> Optional[Dict[str, Any]]:
        if player is None:
            return None
        pid = getattr(player, "id", None)
        if pid is None:
            return None
        if pid not in summary:
            summary[pid] = {
                "goals": 0,
                "goal_minutes": [],
                "assists": 0,
                "assist_minutes": [],
                "yellows": [],
                "reds": [],
                "pens_missed": [],
                "injury": False,
                "sub_in": None,
                "sub_out": None,
            }
        return summary[pid]

    for ev in events:
        minute = int(getattr(ev, "minute", 0) or 0)
        if ev.event in {EventType.GOAL, EventType.PENALTY_SCORED}:
            entry = ensure(ev.player)
            if entry is not None:
                entry["goals"] = int(entry.get("goals", 0)) + 1
                entry.setdefault("goal_minutes", []).append(minute)
        elif ev.event is EventType.PENALTY_MISSED:
            entry = ensure(ev.player)
            if entry is not None:
                entry.setdefault("pens_missed", []).append(minute)
        elif ev.event is EventType.YELLOW:
            entry = ensure(ev.player)
            if entry is not None:
                entry.setdefault("yellows", []).append(minute)
        elif ev.event is EventType.RED:
            entry = ensure(ev.player)
            if entry is not None:
                entry.setdefault("reds", []).append(minute)
        elif ev.event is EventType.INJURY:
            entry = ensure(ev.player)
            if entry is not None:
                entry["injury"] = True
        elif ev.event is EventType.SUBSTITUTION:
            entry_in = ensure(ev.player)
            if entry_in is not None:
                entry_in["sub_in"] = minute
            if getattr(ev, "assist_by", None) is not None:
                entry_out = ensure(ev.assist_by)
                if entry_out is not None:
                    entry_out["sub_out"] = minute

        if ev.assist_by is not None and ev.event in {EventType.GOAL, EventType.PENALTY_SCORED}:
            entry = ensure(ev.assist_by)
            if entry is not None:
                entry["assists"] = int(entry.get("assists", 0)) + 1
                entry.setdefault("assist_minutes", []).append(minute)

    return summary


def _ensure_summary_entry(summary: Dict[int, Dict[str, Any]], pid: int) -> Dict[str, Any]:
    if pid not in summary:
        summary[pid] = {
            "goals": 0,
            "goal_minutes": [],
            "assists": 0,
            "assist_minutes": [],
            "yellows": [],
            "reds": [],
            "pens_missed": [],
            "injury": False,
            "sub_in": None,
            "sub_out": None,
        }
    return summary[pid]


def _rating_to_bars(rating: float) -> int:
    if rating <= 0:
        return 0
    normalized = (rating - 5.0) / 4.5
    bars = int(round(normalized * 12))
    return max(0, min(12, bars))


def _unit_ratings(
    club: Club,
    minutes_map: Dict[int, int],
    ratings: Dict[int, float],
) -> Dict[str, int]:
    groups = {"def": [], "mid": [], "att": []}
    roster = {getattr(p, "id", None): p for p in club.players}
    for pid, minutes in minutes_map.items():
        if minutes <= 0:
            continue
        player = roster.get(pid)
        if not player:
            continue
        rating = ratings.get(pid, 0.0)
        pos = getattr(player, "position", None)
        if pos in (Position.GK, Position.DF):
            groups["def"].append(rating)
        elif pos is Position.MF:
            groups["mid"].append(rating)
        else:
            groups["att"].append(rating)

    return {
        key: _rating_to_bars(sum(vals) / len(vals)) if vals else 0
        for key, vals in groups.items()
    }


def _infer_formation(lineup: List[Player]) -> str:
    counts = {Position.DF: 0, Position.MF: 0, Position.FW: 0}
    for player in lineup:
        pos = getattr(player, "position", None)
        if pos in counts:
            counts[pos] += 1
    return f"{counts[Position.DF]}-{counts[Position.MF]}-{counts[Position.FW]}"


def _select_specialist(
    players: List[Player],
    preferred_trait: Optional[Trait],
) -> Optional[Player]:
    if preferred_trait is not None:
        for player in players:
            if preferred_trait in (getattr(player, "traits", []) or []):
                return player
    if not players:
        return None
    return max(players, key=lambda p: getattr(p, "skill_open", 0))


def _tactic_snapshot(
    club: Club,
    tactic,
    aggressiveness,
    lineup: List[Player],
) -> Dict[str, Any]:
    formation = _infer_formation(lineup)
    tempo = float(getattr(tactic, "tempo", 1.0) or 1.0)
    if tempo >= 1.1:
        style = "Offensiv"
    elif tempo <= 0.9:
        style = "Lugn"
    else:
        style = "Normal"

    aggr_name = str(getattr(aggressiveness, "name", "Medel")).lower()
    if "aggressiv" in aggr_name:
        aggr_label = "Hårt"
    elif "lugn" in aggr_name:
        aggr_label = "Lugnt"
    else:
        aggr_label = "Normal"

    midfielders = [p for p in lineup if getattr(p, "position", None) is Position.MF]
    forwards = [p for p in lineup if getattr(p, "position", None) is Position.FW]
    specialists_pool = lineup + [p for p in club.players if p not in lineup]

    playmaker = _select_specialist(midfielders or lineup, None)
    freekick = _select_specialist(specialists_pool, Trait.FRISPARKSSPECIALIST)
    penalty = _select_specialist(specialists_pool, Trait.STRAFFSPECIALIST)

    def _pid(player: Optional[Player]) -> Optional[str]:
        if player is None:
            return None
        pid = getattr(player, "id", None)
        if pid is None:
            return None
        return f"p-{pid}"

    return {
        "formation": formation,
        "style": style,
        "attack_strategy": "Varierat",
        "defense_strategy": "Normalt" if not getattr(tactic, "defending", False) else "Defensivt",
        "aggressiveness": aggr_label,
        "long_balls": tempo >= 1.1,
        "pressing": bool(getattr(tactic, "attacking", False)),
        "offside_trap": bool(getattr(tactic, "offside_trap", False)),
        "dark_arts": bool(getattr(tactic, "dark_arts", False)),
        "gameplan_vs": "Ingen",
        "playmaker_id": _pid(playmaker),
        "captain_id": (
            f"p-{club.captain_id}" if getattr(club, "captain_id", None) else None
        ),
        "freekick_taker_id": _pid(freekick or playmaker),
        "penalty_taker_id": _pid(penalty or forwards[0] if forwards else playmaker),
    }


def _select_award(
    player_ids: List[int],
    ratings: Dict[int, float],
    summary: Dict[int, Dict[str, Any]],
    roster: Dict[int, Player],
) -> Optional[Dict[str, Any]]:
    best_id: Optional[int] = None
    best_key = (-1.0, -1, -1, -1)
    for pid in player_ids:
        rating = ratings.get(pid, 0.0)
        info = summary.get(pid, {})
        goals = int(info.get("goals", 0))
        assists = int(info.get("assists", 0))
        minutes = int(info.get("minutes", 0))
        key = (rating, goals, assists, minutes)
        if key > best_key:
            best_key = key
            best_id = pid
    if best_id is None:
        return None
    player = roster.get(best_id)
    if not player:
        return None
    return {"player_id": f"p-{best_id}", "name": _player_display_name(player)}


def _captain_effect(club: Club, lineup: List[Player]) -> tuple[float, Player | None, float]:
    cap_id = getattr(club, "captain_id", None)
    if not cap_id:
        return 0.0, None, 0.0
    captain = next((p for p in lineup if getattr(p, "id", None) == cap_id), None)
    if captain is None:
        return 0.0, None, 0.0

    avg = _avg_skill(lineup)
    skill = float(getattr(captain, "skill_open", avg))
    diff = skill - avg
    trait_names = {
        getattr(t, "name", str(t)).upper() for t in getattr(captain, "traits", []) or []
    }
    boost = 0.18
    if "LEDARE" in trait_names:
        boost += 0.10
    if "INTELLIGENT" in trait_names:
        boost += 0.06
    boost += 0.015 * diff
    boost = max(0.0, min(0.5, boost))
    team_uplift = 0.04 + 0.01 * max(0.0, diff)
    return boost, captain, team_uplift


def _pick_lineup(club: Club, n: int = 11) -> List[Player]:
    """Enkel elvaväljare: ta de första 11, fyll upp med slump om färre."""
    ps = list(club.players)
    if len(ps) >= n:
        return ps[:n]
    while len(ps) < n and club.players:
        ps.append(random.choice(club.players))
    return ps[:n]


def _preferred_lineup(club: Club, n: int = 11) -> tuple[List[Player], List[Player]]:
    id_order = list(getattr(club, "preferred_lineup", []) or [])
    players_by_id = {getattr(p, "id", None): p for p in club.players}
    lineup: List[Player] = []
    used: set[int] = set()
    for pid in id_order:
        player = players_by_id.get(pid)
        if player and player.id not in used:
            lineup.append(player)
            used.add(player.id)
        if len(lineup) == n:
            break
    if len(lineup) < n:
        remaining = sorted(
            (p for p in club.players if getattr(p, "id", None) not in used),
            key=lambda x: getattr(x, "skill_open", 5),
            reverse=True,
        )
        for p in remaining:
            lineup.append(p)
            used.add(getattr(p, "id", 0))
            if len(lineup) == n:
                break
    bench: List[Player] = []
    bench_order = list(getattr(club, "bench_order", []) or [])
    for pid in bench_order:
        if pid in used:
            continue
        player = players_by_id.get(pid)
        if player:
            bench.append(player)
            used.add(player.id)
    for p in club.players:
        pid = getattr(p, "id", None)
        if pid is None or pid in used:
            continue
        bench.append(p)
        used.add(pid)
    return lineup[:n], bench


def _collect_injuries(players: List[Player]) -> tuple[List[tuple[Player, int]], List[PlayerEvent]]:
    injured: List[tuple[Player, int]] = []
    events: List[PlayerEvent] = []
    for p in players:
        risk = 0.003
        traits = getattr(p, "traits", []) or []
        trait_names = {getattr(t, "name", str(t)).upper() for t in traits}
        if {"SKADEBENÄGEN", "SKADBENÄGEN", "SKADEBENAGEN"} & trait_names:
            risk += 0.010
        if random.random() < risk:
            minute = random.randint(10, 85)
            injured.append((p, minute))
            events.append(PlayerEvent(EventType.INJURY, minute, p))
    return injured, events


def _pick_bench_player(
    bench: List[Player], preferred_id: Optional[int], position: Optional[str]
) -> Optional[Player]:
    if preferred_id is not None:
        for idx, p in enumerate(bench):
            if getattr(p, "id", None) == preferred_id:
                return bench.pop(idx)
    if position:
        position = position.upper()
        for idx, p in enumerate(bench):
            if getattr(getattr(p, "position", None), "name", "").upper() == position:
                return bench.pop(idx)
    if bench:
        return bench.pop(0)
    return None


def _schedule_substitutions(
    club: Club,
    lineup: List[Player],
    bench: List[Player],
    injuries: List[tuple[Player, int]],
) -> tuple[Dict[int, int], List[Player], List[PlayerEvent]]:
    minutes: Dict[int, int] = {getattr(p, "id", 0): 0 for p in lineup}
    participants: List[Player] = list(lineup)
    events: List[PlayerEvent] = []
    bench_pool: List[Player] = [p for p in bench if p not in lineup]

    injury_rules = [
        rule
        for rule in getattr(club, "substitution_plan", []) or []
        if getattr(rule, "on_injury", False)
    ]
    planned_rules = sorted(
        [
            rule
            for rule in getattr(club, "substitution_plan", []) or []
            if not getattr(rule, "on_injury", False)
        ],
        key=lambda r: int(getattr(r, "minute", 60)),
    )

    scheduled: List[ScheduledSub] = []

    def _match_rule(rule, player: Player) -> bool:
        if getattr(rule, "player_out", None) and getattr(rule, "player_out", None) != getattr(player, "id", None):
            return False
        pos = getattr(rule, "position", None)
        if pos:
            return pos.upper() == getattr(getattr(player, "position", None), "name", "").upper()
        return True

    for player, minute in sorted(injuries, key=lambda x: x[1]):
        replacement = None
        matched_rule = None
        for rule in list(injury_rules):
            if _match_rule(rule, player):
                replacement = _pick_bench_player(
                    bench_pool, getattr(rule, "player_in", None), getattr(rule, "position", None)
                )
                matched_rule = rule
                if replacement:
                    injury_rules.remove(rule)
                break
        if not replacement:
            replacement = _pick_bench_player(
                bench_pool,
                None,
                getattr(getattr(player, "position", None), "name", None),
            )
        if not replacement:
            continue
        scheduled.append(
            ScheduledSub(
                minute=int(minute),
                player_in=replacement,
                player_out_id=getattr(player, "id", None),
                position=getattr(getattr(player, "position", None), "name", None),
                reason="skada",
            )
        )
        participants.append(replacement)
        minutes.setdefault(getattr(replacement, "id", 0), 0)

    for rule in planned_rules:
        replacement = _pick_bench_player(
            bench_pool, getattr(rule, "player_in", None), getattr(rule, "position", None)
        )
        if not replacement:
            continue
        participants.append(replacement)
        minutes.setdefault(getattr(replacement, "id", 0), 0)
        scheduled.append(
            ScheduledSub(
                minute=int(getattr(rule, "minute", 60)),
                player_in=replacement,
                player_out_id=getattr(rule, "player_out", None),
                position=getattr(rule, "position", None),
                reason="planerat byte",
            )
        )

    current_players: List[Player] = list(lineup)
    current_minute = 0
    scheduled.sort(key=lambda s: s.minute)

    for sub in scheduled:
        minute = max(1, min(89, int(sub.minute)))
        duration = minute - current_minute
        if duration > 0:
            for p in current_players:
                pid = getattr(p, "id", None)
                if pid is None:
                    continue
                minutes[pid] = minutes.get(pid, 0) + duration
        current_minute = minute

        player_out = None
        if sub.player_out_id is not None:
            player_out = next(
                (p for p in current_players if getattr(p, "id", None) == sub.player_out_id),
                None,
            )
        if player_out is None and sub.position:
            player_out = next(
                (
                    p
                    for p in current_players
                    if getattr(getattr(p, "position", None), "name", "").upper()
                    == sub.position.upper()
                ),
                None,
            )
        if player_out is None and current_players:
            player_out = current_players[0]

        if player_out in current_players:
            current_players.remove(player_out)
        if sub.player_in not in current_players:
            current_players.append(sub.player_in)

        note = sub.reason or "byte"
        if player_out:
            note = f"in för {_player_display_name(player_out)}"
        events.append(
            PlayerEvent(
                EventType.SUBSTITUTION,
                minute,
                sub.player_in,
                assist_by=player_out,
                note=note,
            )
        )

    remaining = 90 - current_minute
    if remaining > 0:
        for p in current_players:
            pid = getattr(p, "id", None)
            if pid is None:
                continue
            minutes[pid] = minutes.get(pid, 0) + remaining

    return minutes, participants, events


def _effective_lineup(club: Club, minutes: Dict[int, int]) -> List[Player]:
    players_by_id = {getattr(p, "id", None): p for p in club.players}
    ordered: List[Player] = []
    for pid, _mins in sorted(minutes.items(), key=lambda item: item[1], reverse=True):
        player = players_by_id.get(pid)
        if player:
            ordered.append(player)
        if len(ordered) == 11:
            break
    if len(ordered) < 11:
        for p in club.players:
            if p not in ordered:
                ordered.append(p)
            if len(ordered) == 11:
                break
    return ordered[:11]


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
    base_name = getattr(referee, "name", "")
    if not base_name or base_name == "Domare":
        seed = f"{home.name}-{away.name}"
        idx = abs(hash(seed)) % len(REFEREE_NAMES)
        base_name = REFEREE_NAMES[idx]
    referee = Referee(
        skill=int(getattr(referee, "skill", 6)),
        hardness=int(getattr(referee, "hardness", 5)),
        name=base_name,
    )

    # 1) Elvor och grundparametrar
    lineup_home, bench_home = _preferred_lineup(home)
    lineup_away, bench_away = _preferred_lineup(away)

    home_injuries, home_injury_events = _collect_injuries(lineup_home)
    away_injuries, away_injury_events = _collect_injuries(lineup_away)

    home_minutes, home_participants, home_sub_events = _schedule_substitutions(
        home, lineup_home, bench_home, home_injuries
    )
    away_minutes, away_participants, away_sub_events = _schedule_substitutions(
        away, lineup_away, bench_away, away_injuries
    )

    home_xi = _effective_lineup(home, home_minutes)
    away_xi = _effective_lineup(away, away_minutes)

    home_cap_boost, home_captain, home_team_uplift = _captain_effect(home, home_xi)
    away_cap_boost, away_captain, away_team_uplift = _captain_effect(away, away_xi)

    sH = _avg_skill(home_xi)
    sA = _avg_skill(away_xi)
    sH += home_cap_boost
    sA += away_cap_boost
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

    # Kaptenens lagboost påverkar även förväntade mål marginellt
    if home_team_uplift:
        xg_home *= 1.0 + min(0.06, home_team_uplift)
    if away_team_uplift:
        xg_away *= 1.0 + min(0.06, away_team_uplift)

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

    home_dark = bool(getattr(home_tactic, "dark_arts", False))
    away_dark = bool(getattr(away_tactic, "dark_arts", False))

    # 4) Bygg händelser tidslinje (mål först, fyll sedan på)
    events: List[PlayerEvent] = []
    events.extend(home_injury_events)
    events.extend(away_injury_events)
    events.extend(home_sub_events)
    events.extend(away_sub_events)

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
    def distribute_misc(
        team_players: List[Player], stats: TeamStats, is_home: bool, uses_dark_arts: bool
    ):
        # fouls/kort
        aggr = getattr(home_aggr if is_home else away_aggr, "name", "Medel").lower()
        aggr_factor = 1.25 if "aggress" in aggr else (0.85 if "lugn" in aggr else 1.0)
        skill = max(1, min(10, getattr(referee, "skill", 5)))
        skill_offset = (skill - 5) / 5.0
        hardness = max(1, min(10, getattr(referee, "hardness", 5)))
        hardness_offset = (hardness - 5) / 5.0

        detection = 1.0 + 0.12 * skill_offset
        if uses_dark_arts:
            stealth = 1.0 - 0.18 * max(0.0, -skill_offset)
            crackdown = 1.0 + 0.25 * max(0.0, hardness_offset)
            detection *= stealth * crackdown

        base_fouls = int(random.gauss(10, 3))
        foul_factor = aggr_factor * detection
        if uses_dark_arts:
            foul_factor *= 1.12 + 0.10 * max(0.0, hardness_offset)
        fouls = max(4, int(base_fouls * foul_factor))
        stats.fouls = fouls
        for _ in range(fouls):
            minute = random.randint(3, 88)
            victim = random.choice(team_players)
            events.append(PlayerEvent(EventType.FOUL, minute, victim))
            # kortbedömning
            yellow_base = 0.10 * aggr_factor * (1 + 0.06 * (hardness - 5))
            yellow_base *= 1.0 + 0.08 * skill_offset
            if uses_dark_arts:
                yellow_base *= 1.12 + 0.22 * max(0.0, hardness_offset)
                yellow_base *= 1.0 - 0.12 * max(0.0, -skill_offset)
            if random.random() < yellow_base:
                stats.yellows += 1
                events.append(PlayerEvent(EventType.YELLOW, minute, victim))
                if random.random() < 0.08:  # andra gula
                    stats.reds += 1
                    events.append(PlayerEvent(EventType.RED, minute, victim))

        # straffar – mer sällan (ca 0.1–0.2 / match)
        penalty_chance = 0.09 * (1 + 0.10 * aggr_factor)
        penalty_chance *= 1.0 + 0.10 * skill_offset
        if uses_dark_arts:
            penalty_chance *= 1.20 + 0.18 * max(0.0, hardness_offset)
            penalty_chance *= 1.0 - 0.18 * max(0.0, -skill_offset)
        penalty_chance = max(0.03, min(0.30, penalty_chance))
        if random.random() < penalty_chance:
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
        adjusted_offsides = max(
            0, int(round(stats.offsides * (1.0 + 0.15 * skill_offset)))
        )
        for _ in range(adjusted_offsides):
            events.append(
                PlayerEvent(
                    EventType.OFFSIDE,
                    random.randint(2, 88),
                    _choose_weighted(team_players, "scorer"),
                )
            )
        stats.offsides = adjusted_offsides
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

    distribute_misc(home_xi, H, True, home_dark)
    distribute_misc(away_xi, A, False, away_dark)

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

    all_players = home_participants + [p for p in away_participants if p not in home_participants]
    for p in all_players:
        base = (
            6.2 + 0.12 * (getattr(p, "skill_open", 5) - 5) + random.uniform(-0.6, 0.6)
        )
        base += impact.get(p.id, 0.0)
        if Trait.LEDARE in getattr(p, "traits", []):
            base += 0.1
        if Trait.AGGRESSIV in getattr(p, "traits", []):
            base -= 0.05
        if home_captain and p is home_captain:
            base += 0.25
        elif away_captain and p is away_captain:
            base += 0.25
        elif home_captain and p in home_xi:
            base += 0.05
        elif away_captain and p in away_xi:
            base += 0.05
        minutes_played = 90
        if p in home_participants:
            minutes_played = home_minutes.get(getattr(p, "id", 0), 90)
        elif p in away_participants:
            minutes_played = away_minutes.get(getattr(p, "id", 0), 90)
        ratio = max(0.3, min(1.0, minutes_played / 90))
        adj = 6.0 + (base - 6.0) * ratio
        ratings[p.id] = float(max(5.0, min(9.5, adj)))

    home_ids = {getattr(p, "id", None) for p in home.players}
    away_ids = {getattr(p, "id", None) for p in away.players}
    ht_home_goals = 0
    ht_away_goals = 0
    for ev in events:
        if ev.event is EventType.GOAL and ev.player:
            pid = getattr(ev.player, "id", None)
            minute = int(getattr(ev, "minute", 0) or 0)
            if minute <= 45:
                if pid in home_ids:
                    ht_home_goals += 1
                elif pid in away_ids:
                    ht_away_goals += 1

    summary = player_event_summary(events)
    for pid, mins in home_minutes.items():
        entry = _ensure_summary_entry(summary, pid)
        entry["minutes"] = int(mins)
    for pid, mins in away_minutes.items():
        entry = _ensure_summary_entry(summary, pid)
        entry["minutes"] = int(mins)

    ratings_units = {
        "home": _unit_ratings(home, home_minutes, ratings),
        "away": _unit_ratings(away, away_minutes, ratings),
    }

    tactic_snapshot = {
        "home": _tactic_snapshot(home, home_tactic, home_aggr, home_xi),
        "away": _tactic_snapshot(away, away_tactic, away_aggr, away_xi),
    }

    home_roster = {getattr(p, "id", None): p for p in home.players}
    away_roster = {getattr(p, "id", None): p for p in away.players}
    awards = {
        "mom_home": _select_award(list(home_minutes.keys()), ratings, summary, home_roster),
        "mom_away": _select_award(list(away_minutes.keys()), ratings, summary, away_roster),
    }

    stats_extra = {
        "possession": {
            "home": H.possession_pct,
            "away": A.possession_pct,
            "ht_home": H.possession_pct,
            "ht_away": A.possession_pct,
        },
        "chances": {
            "home": H.shots_on,
            "away": A.shots_on,
            "ht_home": min(H.shots_on, (H.shots_on + 1) // 2),
            "ht_away": min(A.shots_on, (A.shots_on + 1) // 2),
        },
    }

    # 9) Sortera händelser och returnera
    events.sort(key=lambda e: e.minute)
    return MatchResult(
        home=home,
        away=away,
        events=events,
        home_stats=H,
        away_stats=A,
        ratings=ratings,
        home_minutes=home_minutes,
        away_minutes=away_minutes,
        home_lineup=list(lineup_home),
        away_lineup=list(lineup_away),
        home_bench=list(bench_home),
        away_bench=list(bench_away),
        home_dark_arts=home_dark,
        away_dark_arts=away_dark,
        referee=referee,
        home_ht_goals=ht_home_goals,
        away_ht_goals=ht_away_goals,
        stats_extra=stats_extra,
        ratings_by_unit=ratings_units,
        tactic_snapshot=tactic_snapshot,
        awards=awards,
    )
