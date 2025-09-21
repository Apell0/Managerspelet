from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Tuple

from .club import Club
from .player import Player


@dataclass(slots=True)
class TrainingOrder:
    id: int
    club_name: str
    player_id: int
    weeks_left: int = 1
    cost_sek: int = 200_000
    status: str = "active"  # active | done | cancelled
    # valfritt: lite loggtext
    note: str = ""


# --------- Hjälpare ---------


def _find_club_and_player(
    clubs: List[Club], club_name: str, player_id: int
) -> Tuple[Club, Player]:
    club = next((c for c in clubs if c.name.lower() == club_name.lower()), None)
    if not club:
        raise ValueError(f"Hittar ingen klubb '{club_name}'")
    player = next((p for p in club.players if p.id == player_id), None)
    if not player:
        raise ValueError(f"Hittar ingen spelare med id={player_id} i {club.name}")
    return club, player


def _has_trait(player: Player, *names: str) -> bool:
    traits = getattr(player, "traits", []) or []
    names_u = {n.upper() for n in names}
    for t in traits:
        nm = getattr(t, "name", str(t)).upper()
        if nm in names_u:
            return True
    return False


# --------- API ---------


def list_training(gs) -> List[TrainingOrder]:
    return [o for o in (gs.training_orders or [])]


def start_form_training(gs, club_name: str, player_id: int) -> TrainingOrder:
    """Starta en veckas formträning för spelare. Drar 200k kr omedelbart."""
    div = gs.league.divisions[0]
    club, player = _find_club_and_player(div.clubs, club_name, player_id)

    # Kolla om redan aktiv order för spelaren
    for o in gs.training_orders:
        if (
            o.status == "active"
            and o.player_id == player_id
            and o.club_name.lower() == club.name.lower()
        ):
            raise ValueError(
                f"{player.first_name} {player.last_name} har redan aktiv formträning."
            )

    if getattr(club, "cash_sek", 0) < 200_000:
        raise ValueError(f"{club.name} har inte råd (behöver 200 000 kr).")

    club.cash_sek -= 200_000
    next_id = (
        (max((o.id for o in gs.training_orders), default=0) + 1)
        if gs.training_orders
        else 1
    )
    order = TrainingOrder(id=next_id, club_name=club.name, player_id=player.id)
    gs.training_orders.append(order)
    return order


def advance_week(gs) -> List[str]:
    """
    Processa en 'vecka': decrement weeks_left, applicera form-boost när order når 0.
    Returnerar en lista med loggrader (trevliga att visa i CLI).
    """
    logs: List[str] = []
    div = gs.league.divisions[0]

    # Index för snabb lookup
    club_ix = {c.name: c for c in div.clubs}
    player_ix = {p.id: p for c in div.clubs for p in c.players}

    for o in gs.training_orders:
        if o.status != "active":
            continue

        o.weeks_left -= 1
        if o.weeks_left > 0:
            continue

        # Klar → applicera boost
        club = club_ix.get(o.club_name)
        player = player_ix.get(o.player_id)
        if not (club and player):
            o.status = "done"
            o.note = "Spelare/klubb saknas vid slutförande."
            continue

        base = random.randint(2, 5)  # 2–5
        bonus = 0
        # robust trait-match mot TRÄNINGSVILLIG / TRAININGSVILLIG
        if _has_trait(player, "TRÄNINGSVILLIG", "TRAININGSVILLIG"):
            bonus = random.randint(1, 3)
        boost = base + bonus

        # applicera
        now = int(getattr(player, "form_now", 10))
        new_now = max(1, min(20, now + boost))
        setattr(player, "form_now", new_now)

        # justera säsongsform lite försiktigt
        season = float(getattr(player, "form_season", 10))
        season = min(20.0, season + 0.5 * boost)
        setattr(player, "form_season", season)

        o.status = "done"
        o.note = f"+{boost} form (nu {new_now})"
        logs.append(
            f"{club.name}: {player.first_name} {player.last_name} fick +{boost} form → {new_now} (säsong {season:.1f})"
        )

    return logs
