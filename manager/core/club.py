from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, Iterable, List, Optional, Sequence, Tuple

from .player import Player, Position

if TYPE_CHECKING:
    # Endast för type hints (körs inte vid runtime) → ingen cirkulär import
    from .season import Aggressiveness, Tactic


def _default_tactic():
    # Lazy import för att undvika cirkulär import vid runtime
    from .season import Tactic

    return Tactic(attacking=False, defending=False, offside_trap=False, tempo=1.0)


def _default_aggr():
    # Lazy import för att undvika cirkulär import vid runtime
    from .season import Aggressiveness

    return Aggressiveness("Medel")


@dataclass(slots=True)
class SubstitutionRule:
    minute: int = 60
    player_in: Optional[int] = None
    player_out: Optional[int] = None
    position: Optional[str] = None  # "GK", "DF", "MF", "FW"
    on_injury: bool = False


@dataclass(slots=True)
class Club:
    name: str
    players: List[Player] = field(default_factory=list)
    cash_sek: int = 0
    club_id: str | None = None
    emblem_path: str | None = None
    kit_path: str | None = None
    stadium_name: str | None = None
    manager_name: str | None = None
    colors: Dict[str, str | None] = field(default_factory=dict)
    form_history: List[int] = field(default_factory=list)
    trophies: List[str] = field(default_factory=list)
    captain_id: int | None = None
    preferred_lineup: List[int] = field(default_factory=list)
    bench_order: List[int] = field(default_factory=list)
    substitution_plan: List[SubstitutionRule] = field(default_factory=list)

    # Per-klubb taktik & aggressivitet (persistenta)
    tactic: "Tactic" = field(default_factory=_default_tactic)
    aggressiveness: "Aggressiveness" = field(default_factory=_default_aggr)

    def average_skill(self) -> float:
        if not self.players:
            return 0.0
        return sum(getattr(p, "skill_open", 5) for p in self.players) / len(
            self.players
        )


MIN_SQUAD_SIZE = 13
MAX_SQUAD_SIZE = 30
MIN_POSITION_COUNTS = {
    Position.GK: 1,
    Position.DF: 4,
    Position.MF: 4,
    Position.FW: 2,
}


def _position_enum(value) -> Optional[Position]:
    if isinstance(value, Position):
        return value
    if hasattr(value, "value"):
        return _position_enum(getattr(value, "value"))
    if value is None:
        return None
    try:
        return Position(value)
    except ValueError:
        try:
            return Position[str(value).upper()]
        except Exception:
            return None


def project_squad(
    club: "Club",
    *,
    add: Sequence[Player] | None = None,
    remove: Sequence[Player] | None = None,
) -> List[Player]:
    """Returnera en projekterad spelarlista efter tillägg/borttag."""

    projected: List[Player] = []
    remove_ids = {
        getattr(p, "id", id(p)) for p in (remove or []) if getattr(p, "id", None) is not None
    }
    if remove_ids:
        projected.extend(p for p in club.players if getattr(p, "id", None) not in remove_ids)
    else:
        projected.extend(club.players)
    if add:
        projected.extend(add)
    return projected


def count_positions(players: Iterable[Player]) -> dict[Position, int]:
    counts = {pos: 0 for pos in Position}
    for player in players:
        pos = _position_enum(getattr(player, "position", None))
        if pos is not None:
            counts[pos] = counts.get(pos, 0) + 1
    return counts


def validate_squad(
    players: Sequence[Player],
    *,
    min_size: int = MIN_SQUAD_SIZE,
    max_size: int = MAX_SQUAD_SIZE,
    min_positions: dict[Position, int] | None = None,
) -> Tuple[bool, str]:
    size = len(players)
    if size < min_size:
        return False, f"laget måste ha minst {min_size} spelare (har {size})."
    if size > max_size:
        return False, f"laget kan max ha {max_size} spelare (har {size})."

    mins = min_positions or MIN_POSITION_COUNTS
    pos_counts = count_positions(players)
    for pos, required in mins.items():
        if pos_counts.get(pos, 0) < required:
            return (
                False,
                f"laget måste ha minst {required} spelare på position {pos.value} (har {pos_counts.get(pos, 0)}).",
            )
    return True, ""


def check_squad_limits(
    club: "Club",
    *,
    add: Sequence[Player] | None = None,
    remove: Sequence[Player] | None = None,
    min_size: int = MIN_SQUAD_SIZE,
    max_size: int = MAX_SQUAD_SIZE,
    min_positions: dict[Position, int] | None = None,
) -> Tuple[bool, str]:
    """Kontrollera att klubben klarar min-/maxgränser och positionskrav."""

    projected = project_squad(club, add=add, remove=remove)
    return validate_squad(
        projected,
        min_size=min_size,
        max_size=max_size,
        min_positions=min_positions,
    )
