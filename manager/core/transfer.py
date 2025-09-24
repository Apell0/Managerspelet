from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(slots=True)
class TransferListing:
    """Beskriver en spelare som är till salu på transfermarknaden."""

    player_id: Optional[int]
    club_name: Optional[str]
    price_sek: int
    player_snapshot: Optional[Dict[str, object]] = None  # används för fria agenter
    note: str = ""


@dataclass(slots=True)
class JuniorOffer:
    """Ett juniorerbjudande för en klubb."""

    club_name: str
    price_sek: int
    player_snapshot: Dict[str, object]
    expires_season: int
    tags: List[str] = field(default_factory=list)


def transfer_listing_to_dict(listing: TransferListing) -> Dict[str, object]:
    return {
        "player_id": listing.player_id,
        "club_name": listing.club_name,
        "price_sek": int(listing.price_sek),
        "player_snapshot": listing.player_snapshot,
        "note": listing.note,
    }


def transfer_listing_from_dict(data: Dict[str, object]) -> TransferListing:
    return TransferListing(
        player_id=data.get("player_id"),
        club_name=data.get("club_name"),
        price_sek=int(data.get("price_sek", 0)),
        player_snapshot=data.get("player_snapshot"),
        note=data.get("note", ""),
    )


def junior_offer_to_dict(offer: JuniorOffer) -> Dict[str, object]:
    return {
        "club_name": offer.club_name,
        "price_sek": int(offer.price_sek),
        "player_snapshot": offer.player_snapshot,
        "expires_season": int(offer.expires_season),
        "tags": list(offer.tags or []),
    }


def junior_offer_from_dict(data: Dict[str, object]) -> JuniorOffer:
    return JuniorOffer(
        club_name=data.get("club_name", ""),
        price_sek=int(data.get("price_sek", 0)),
        player_snapshot=data.get("player_snapshot", {}),
        expires_season=int(data.get("expires_season", 0)),
        tags=list(data.get("tags", []) or []),
    )
