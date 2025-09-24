from __future__ import annotations

import random
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

from .club import check_squad_limits
from .player import Player, Position, Trait
from .serialize import player_from_dict, player_to_dict
from .transfer import JuniorOffer, TransferListing

if TYPE_CHECKING:
    from .club import Club
    from .state import GameState


def _club_lookup(gs: "GameState", name: str) -> Optional["Club"]:
    for div in gs.league.divisions:
        for club in div.clubs:
            if club.name.lower() == name.lower():
                return club
    return None


POSITIONS = [Position.GK, Position.DF, Position.MF, Position.FW]


def _trait_multiplier(player: Player) -> float:
    mult = 1.0
    traits = getattr(player, "traits", []) or []
    for trait in traits:
        name = getattr(trait, "name", str(trait)).upper()
        if name in {"LEDARE", "INTELLIGENT", "UTHELLIG", "UTHALLIG"}:
            mult *= 1.08
        elif name in {"SNABB", "KYLDIG", "KYLDIG"}:
            mult *= 1.05
        elif name in {"STRAFFSPECIALIST", "FRISPARKSSPECIALIST"}:
            mult *= 1.04
        elif name in {"SKADEBENÄGEN", "SKADEBENAGEN"}:
            mult *= 0.80
        elif name in {"OJAMN", "KORTBENAGEN"}:
            mult *= 0.90
    return mult


def _stats_bonus(stats: Optional[object]) -> float:
    if not stats:
        return 1.0
    try:
        goals = float(getattr(stats, "goals", stats.get("goals", 0)))
        assists = float(getattr(stats, "assists", stats.get("assists", 0)))
        rating = float(getattr(stats, "rating_avg", stats.get("rating_avg", 0)))
    except Exception:
        goals = assists = rating = 0.0
    bonus = 1.0 + 0.03 * goals + 0.015 * assists
    if rating > 6.5:
        bonus *= 1.0 + (rating - 6.5) * 0.08
    return min(1.6, max(0.8, bonus))


def calculate_player_value(player: Player, stats: Optional[object] = None) -> int:
    skill = int(getattr(player, "skill_open", 5))
    age = int(getattr(player, "age", 24))
    form_now = float(getattr(player, "form_now", 10))
    form_season = float(getattr(player, "form_season", 10))

    base = 400_000 * max(1, skill)
    if age <= 20:
        base *= 1.35
    elif age <= 23:
        base *= 1.15
    elif age <= 28:
        base *= 1.0
    elif age <= 31:
        base *= 0.85
    else:
        base *= 0.70

    form_factor = (form_now + form_season) / 20.0
    base *= 0.85 + 0.15 * form_factor
    base *= _trait_multiplier(player)
    base *= _stats_bonus(stats)
    position = getattr(getattr(player, "position", None), "name", "")
    if position == "GK":
        base *= 0.9

    return int(max(50_000, base))


def update_player_values(gs: "GameState") -> None:
    stats_map = getattr(gs, "player_stats", {}) or {}
    for div in gs.league.divisions:
        for club in div.clubs:
            for player in club.players:
                stats_obj = stats_map.get(player.id)
                value = calculate_player_value(player, stats_obj)
                setattr(player, "value_sek", value)


def apply_weekly_finances(gs: "GameState", base_income: int = 600_000) -> List[str]:
    logs: List[str] = []
    for div in gs.league.divisions:
        for club in div.clubs:
            club.cash_sek = int(getattr(club, "cash_sek", 0)) + base_income
            logs.append(f"{club.name}: +{base_income:,} kr i sponsorbidrag")
            ledger_entry = {
                "date": {
                    "season": getattr(gs, "season", 1),
                    "week": getattr(gs, "calendar_week", 1),
                },
                "club_id": getattr(club, "club_id", None),
                "club": club.name,
                "type": "income",
                "label": "weekly_sponsor",
                "amount": base_income,
            }
            getattr(gs, "economy_ledger", []).append(ledger_entry)
    return logs


def process_weekly_economy(gs: "GameState", base_income: int = 600_000) -> List[str]:
    """Apply sponsorbidrag och låt bottar agera på transfermarknaden."""

    logs = apply_weekly_finances(gs, base_income=base_income)
    refresh_transfer_market(gs)
    logs.extend(evaluate_bot_signings(gs))
    update_player_values(gs)
    return logs


def award_sponsor_activity(gs: "GameState", club_name: str, amount: int = 1_000_000) -> str:
    for div in gs.league.divisions:
        for club in div.clubs:
            if club.name.lower() == club_name.lower():
                club.cash_sek += amount
                getattr(gs, "economy_ledger", []).append(
                    {
                        "date": {
                            "season": getattr(gs, "season", 1),
                            "week": getattr(gs, "calendar_week", 1),
                        },
                        "club_id": getattr(club, "club_id", None),
                        "club": club.name,
                        "type": "income",
                        "label": "sponsor_activity",
                        "amount": amount,
                    }
                )
                return f"{club.name} erhöll {amount:,} kr från sponsoraktivitet."
    raise ValueError(f"Hittade ingen klubb med namn '{club_name}'.")


def _all_clubs(gs: "GameState") -> List["Club"]:
    clubs: List["Club"] = []
    for div in gs.league.divisions:
        clubs.extend(div.clubs)
    return clubs


def _next_player_id(gs: "GameState") -> int:
    max_id = 0
    for club in _all_clubs(gs):
        for player in club.players:
            max_id = max(max_id, int(getattr(player, "id", 0)))
    for offers in getattr(gs, "junior_offers", {}).values():
        for offer in offers:
            pid = offer.player_snapshot.get("id")
            if pid:
                max_id = max(max_id, int(pid))
    for listing in getattr(gs, "transfer_list", []) or []:
        if listing.player_snapshot and listing.player_snapshot.get("id"):
            max_id = max(max_id, int(listing.player_snapshot["id"]))
    return max_id + 1


def _random_position() -> Position:
    weights = [0.15, 0.35, 0.30, 0.20]
    return random.choices(POSITIONS, weights=weights, k=1)[0]


def _generate_player(next_id: int, skill: int, age: int) -> Player:
    from .player import Player

    position = _random_position()
    number = random.randint(1, 99)
    traits_pool = list(Trait)
    random.shuffle(traits_pool)
    traits = []
    for t in traits_pool[: random.randint(0, 2)]:
        traits.append(t)
    player = Player(
        id=next_id,
        first_name=f"Junior{next_id}",
        last_name=f"Talang{random.randint(1, 999)}",
        age=age,
        position=position,
        number=number,
        skill_open=skill,
        skill_hidden=random.randint(30, 80),
        skill_xp=random.randint(30, 80),
        form_now=random.randint(8, 12),
        form_season=random.randint(8, 12),
        traits=traits,
    )
    return player


def _create_free_agent_listing(gs: "GameState") -> TransferListing:
    next_id = _next_player_id(gs)
    age = random.randint(22, 30)
    skill = max(3, min(12, int(random.gauss(6, 1.5))))
    player = _generate_player(next_id, skill, age)
    value = calculate_player_value(player)
    snapshot = player_to_dict(player)
    return TransferListing(
        player_id=player.id,
        club_name=None,
        price_sek=value,
        player_snapshot=snapshot,
        note="fri agent",
    )


def refresh_transfer_market(gs: "GameState", min_listings: int = 10) -> None:
    listings: List[TransferListing] = list(getattr(gs, "transfer_list", []) or [])
    clubs = _all_clubs(gs)
    valid_listings: List[TransferListing] = []
    for listing in listings:
        if listing.player_snapshot:
            valid_listings.append(listing)
            continue
        found = False
        for club in clubs:
            if club.name == listing.club_name:
                if any(p.id == listing.player_id for p in club.players):
                    found = True
                break
        if found:
            valid_listings.append(listing)
    listings = valid_listings

    attempts = 0
    while len(listings) < min_listings and attempts < min_listings * 3:
        attempts += 1
        if random.random() < 0.3:
            listings.append(_create_free_agent_listing(gs))
            continue
        club = random.choice(clubs)
        sellable = [p for p in club.players if getattr(p, "skill_open", 0) >= 4]
        if not sellable:
            continue
        player = random.choice(sellable)
        if any(
            l.player_id == player.id and l.club_name == club.name for l in listings if not l.player_snapshot
        ):
            continue
        price = max(getattr(player, "value_sek", 200_000), 150_000)
        listings.append(
            TransferListing(
                player_id=player.id,
                club_name=club.name,
                price_sek=int(price * random.uniform(0.9, 1.2)),
                note="klubbförsäljning",
            )
        )

    gs.transfer_list = listings


def generate_junior_offers(gs: "GameState", club_name: str, count: int = 3) -> List[JuniorOffer]:
    offers = []
    next_id = _next_player_id(gs)
    for _ in range(max(1, count)):
        age_roll = random.random()
        if age_roll < 0.6:
            age = random.randint(17, 18)
        elif age_roll < 0.9:
            age = random.randint(16, 19)
        else:
            age = 20
        skill = max(2, min(12, int(random.gauss(4.5, 1.8))))
        player = _generate_player(next_id, skill, age)
        next_id += 1
        snapshot = player_to_dict(player)
        price = int(calculate_player_value(player) * 0.6)
        offer = JuniorOffer(
            club_name=club_name,
            price_sek=price,
            player_snapshot=snapshot,
            expires_season=gs.season + 1,
            tags=["junior"],
        )
        offers.append(offer)
    gs.junior_offers[club_name] = offers
    return offers


def roll_new_junior_offers(
    gs: "GameState", minimum: int = 1, maximum: int = 3
) -> Dict[str, List[JuniorOffer]]:
    """Skapa nya juniorerbjudanden för alla klubbar inför en ny säsong."""

    gs.ensure_containers()

    cleaned: Dict[str, List[JuniorOffer]] = {}
    for club_name, offers in (gs.junior_offers or {}).items():
        valid = [offer for offer in offers if offer.expires_season >= gs.season]
        if valid:
            cleaned[club_name] = valid
    gs.junior_offers = cleaned

    upper = max(maximum, minimum)
    lower = max(1, minimum)

    for club in _all_clubs(gs):
        count = random.randint(lower, upper)
        generate_junior_offers(gs, club.name, count)

    return gs.junior_offers


def accept_junior_offer(gs: "GameState", club_name: str, index: int) -> Player:
    club = next(
        (c for div in gs.league.divisions for c in div.clubs if c.name.lower() == club_name.lower()),
        None,
    )
    if not club:
        raise ValueError(f"Hittar ingen klubb '{club_name}'.")
    offers = gs.junior_offers.get(club.name) or []
    if not (0 <= index < len(offers)):
        raise IndexError("Ogiltigt juniorerbjudande.")
    offer = offers.pop(index)
    if getattr(club, "cash_sek", 0) < offer.price_sek:
        raise ValueError(f"{club.name} saknar pengar ({offer.price_sek:,} kr krävs).")
    player = player_from_dict(offer.player_snapshot)
    ok, reason = check_squad_limits(club, add=[player])
    if not ok:
        raise ValueError(f"{club.name}: {reason}")
    club.cash_sek -= offer.price_sek
    club.players.append(player)
    setattr(player, "value_sek", calculate_player_value(player))
    gs.junior_offers[club.name] = offers
    return player


def purchase_listing(gs: "GameState", buyer_name: str, index: int) -> Tuple[str, Player]:
    listings = getattr(gs, "transfer_list", []) or []
    if not (0 <= index < len(listings)):
        raise IndexError("Ogiltigt transferindex.")
    listing = listings[index]
    buyer = next(
        (c for div in gs.league.divisions for c in div.clubs if c.name.lower() == buyer_name.lower()),
        None,
    )
    if not buyer:
        raise ValueError(f"Hittar ingen klubb '{buyer_name}'.")
    price = int(listing.price_sek)
    if getattr(buyer, "cash_sek", 0) < price:
        raise ValueError(f"{buyer.name} saknar pengar ({price:,} kr krävs).")

    if listing.player_snapshot:
        player = player_from_dict(listing.player_snapshot)
        ok, reason = check_squad_limits(buyer, add=[player])
        if not ok:
            raise ValueError(f"{buyer.name}: {reason}")
        buyer.players.append(player)
        buyer.cash_sek -= price
        setattr(player, "value_sek", calculate_player_value(player))
        gs.transfer_list.pop(index)
        return f"{buyer.name} skrev kontrakt med {player.full_name} (fri agent)", player

    seller = next(
        (c for div in gs.league.divisions for c in div.clubs if c.name == listing.club_name),
        None,
    )
    if not seller:
        raise ValueError("Säljarklubben finns inte längre.")
    if seller is buyer:
        raise ValueError("En klubb kan inte köpa sin egen spelare.")
    player = next((p for p in seller.players if p.id == listing.player_id), None)
    if not player:
        raise ValueError("Spelaren finns inte längre i säljarklubben.")

    ok_add, reason_add = check_squad_limits(buyer, add=[player])
    if not ok_add:
        raise ValueError(f"{buyer.name}: {reason_add}")
    ok_remove, reason_remove = check_squad_limits(seller, remove=[player])
    if not ok_remove:
        raise ValueError(f"{seller.name}: {reason_remove}")

    seller.players.remove(player)
    buyer.players.append(player)
    buyer.cash_sek -= price
    seller.cash_sek += price
    gs.transfer_list.pop(index)
    setattr(player, "value_sek", calculate_player_value(player))
    return f"{buyer.name} köpte {player.full_name} från {seller.name}", player


def evaluate_bot_signings(gs: "GameState") -> List[str]:
    clubs = _all_clubs(gs)
    logs: List[str] = []
    idx = 0
    while idx < len(getattr(gs, "transfer_list", []) or []):
        listings = getattr(gs, "transfer_list", []) or []
        if idx >= len(listings):
            break
        listing = listings[idx]
        candidates = []
        for club in clubs:
            if listing.club_name and club.name == listing.club_name:
                continue
            if getattr(club, "cash_sek", 0) > listing.price_sek * 1.3:
                candidates.append(club)
        if candidates:
            chance = 0.08 if listing.player_snapshot else 0.04
            if random.random() < chance:
                buyer = random.choice(candidates)
                try:
                    msg, _ = purchase_listing(gs, buyer.name, idx)
                except Exception:
                    continue
                logs.append(msg)
                continue
        idx += 1
    return logs


def _club_table_position(gs: "GameState", club: "Club") -> Tuple[int, int]:
    for div in gs.league.divisions:
        if club not in div.clubs:
            continue
        rows = []
        for other in div.clubs:
            row = (gs.table_snapshot or {}).get(
                other.name, {"pts": 0, "gf": 0, "ga": 0}
            )
            pts = int(row.get("pts", 0))
            gf = int(row.get("gf", 0))
            ga = int(row.get("ga", 0))
            gd = gf - ga
            rows.append((other, pts, gd, gf))
        rows.sort(key=lambda x: (x[1], x[2], x[3], x[0].name), reverse=True)
        for index, (candidate, *_rest) in enumerate(rows, start=1):
            if candidate is club:
                return index, len(rows)
    return 1, 1


def _seller_accepts_transfer(
    gs: "GameState",
    seller: "Club",
    player: Player,
    offer: int,
    value: int,
) -> Tuple[bool, str]:
    position, total = _club_table_position(gs, seller)
    ratio = position / max(total, 1)

    threshold = 1.05
    if ratio <= 0.25:
        threshold += 0.35
    elif ratio <= 0.5:
        threshold += 0.15
    elif ratio >= 0.9:
        threshold -= 0.15

    cash = int(getattr(seller, "cash_sek", 0))
    if cash < value:
        threshold -= 0.1
    if cash < offer // 2:
        threshold -= 0.1
    if cash > 7_500_000:
        threshold += 0.05

    roster = len(getattr(seller, "players", []) or [])
    if roster <= 14:
        threshold += 0.15
    elif roster >= 23:
        threshold -= 0.05

    avg_skill = 0.0
    if roster:
        avg_skill = sum(int(getattr(p, "skill_open", 5)) for p in seller.players) / roster
    if int(getattr(player, "skill_open", 5)) >= avg_skill + 2:
        threshold += 0.1
    elif int(getattr(player, "skill_open", 5)) <= avg_skill - 1:
        threshold -= 0.05

    threshold = max(0.85, threshold)
    ratio_offer = offer / max(value, 1)
    if ratio_offer >= threshold:
        return True, "budet var tillräckligt högt"

    reason = (
        f"kräver minst {threshold:.2f}× värdet ({value:,} kr) men budet var"
        f" {ratio_offer:.2f}×"
    )
    if roster <= 14:
        reason += ", truppen är för tunn"
    elif ratio <= 0.5:
        reason += ", klubben jagar topplacering"
    return False, reason


def submit_transfer_bid(
    gs: "GameState", buyer_name: str, player_id: int, offer_price: Optional[int] = None
) -> Tuple[bool, str, Optional[Player]]:
    buyer = _club_lookup(gs, buyer_name)
    if not buyer:
        raise ValueError(f"Hittar ingen klubb '{buyer_name}'.")

    seller: Optional["Club"] = None
    player: Optional[Player] = None
    for club in _all_clubs(gs):
        for candidate in club.players:
            if candidate.id == player_id:
                seller = club
                player = candidate
                break
        if player:
            break

    if not player or not seller:
        raise ValueError(f"Spelare med id={player_id} hittades inte i ligan.")
    if seller is buyer:
        raise ValueError("En klubb kan inte lägga bud på sin egen spelare.")

    stats_map = getattr(gs, "player_stats", {}) or {}
    market_value = calculate_player_value(player, stats_map.get(player.id))
    offer = (
        int(offer_price)
        if offer_price is not None
        else int(max(market_value * 1.1, 50_000))
    )
    if offer <= 0:
        raise ValueError("Budet måste vara positivt.")
    if getattr(buyer, "cash_sek", 0) < offer:
        raise ValueError(f"{buyer.name} saknar pengar ({offer:,} kr krävs).")

    ok_add, reason_add = check_squad_limits(buyer, add=[player])
    if not ok_add:
        raise ValueError(f"{buyer.name}: {reason_add}")
    ok_remove, reason_remove = check_squad_limits(seller, remove=[player])
    if not ok_remove:
        raise ValueError(f"{seller.name}: {reason_remove}")

    accepted, reason = _seller_accepts_transfer(gs, seller, player, offer, market_value)
    if not accepted:
        return (
            False,
            f"{seller.name} avböjde budet på {offer:,} kr för {player.full_name}: {reason}.",
            None,
        )

    seller.players.remove(player)
    buyer.players.append(player)
    buyer.cash_sek -= offer
    seller.cash_sek += offer

    for attr in ("preferred_lineup", "bench_order"):
        seq = getattr(seller, attr, None)
        if seq:
            setattr(seller, attr, [pid for pid in seq if pid != player.id])
    plan = getattr(seller, "substitution_plan", None)
    if plan:
        filtered = [
            rule
            for rule in plan
            if getattr(rule, "player_in", None) != player.id
            and getattr(rule, "player_out", None) != player.id
        ]
        setattr(seller, "substitution_plan", filtered)

    listings = []
    for listing in getattr(gs, "transfer_list", []) or []:
        if listing.player_id == player.id:
            continue
        listings.append(listing)
    gs.transfer_list = listings

    setattr(player, "value_sek", calculate_player_value(player, stats_map.get(player.id)))

    message = (
        f"{buyer.name} värvade {player.full_name} från {seller.name} för {offer:,} kr"
    )
    return True, message, player

