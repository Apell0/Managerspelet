import random
from typing import Any
from unittest.mock import patch

import pytest

from manager.core.club import Club, SubstitutionRule
from manager.core.economy import (
    accept_junior_offer,
    apply_weekly_finances,
    evaluate_bot_signings,
    generate_junior_offers,
    process_weekly_economy,
    purchase_listing,
    submit_transfer_bid,
    update_player_values,
)
from manager.core.generator import generate_club
from manager.core.livefeed import format_feed
from manager.core.league import Division, League, LeagueRules
from manager.core.match import (
    Referee,
    TeamStats,
    MatchResult,
    _captain_effect,
    _schedule_substitutions,
    simulate_match,
)
from manager.core.player import Player, Position, Trait
from manager.core.season import Aggressiveness, Tactic
from manager.core.season_progression import end_season
from manager.core.state import GameState
from manager.core.transfer import TransferListing
from manager.core.serialize import player_to_dict
from manager.core.stats import update_stats_from_result


def _make_player(pid: int, position: Position, skill: int = 5, traits=None) -> Player:
    traits = traits or []
    return Player(
        id=pid,
        first_name=f"P{pid}",
        last_name="Test",
        age=24,
        position=position,
        number=pid,
        skill_open=skill,
        skill_hidden=skill * 3,
        traits=traits,
    )


def _make_club(name: str, start_id: int = 1) -> Club:
    layout = [
        (Position.GK, 2),
        (Position.DF, 5),
        (Position.MF, 5),
        (Position.FW, 4),
    ]
    players: list[Player] = []
    pid = start_id
    for pos, count in layout:
        for _ in range(count):
            players.append(_make_player(pid, pos, skill=6))
            pid += 1
    club = Club(name=name, players=players, cash_sek=1_000_000)
    club.preferred_lineup = [p.id for p in players[:11]]
    club.substitution_plan = []
    return club


def _make_state(clubs) -> GameState:
    division = Division(name="Div 1", level=1, clubs=list(clubs))
    league = League(name="Testligan", rules=LeagueRules(teams_per_div=len(clubs)), divisions=[division])
    gs = GameState(season=1, league=league, fixtures_by_division={division.name: []})
    gs.ensure_containers()
    return gs


def test_generate_club_assigns_player_values():
    club = generate_club("Värde FC")
    assert club.players, "Klubben ska ha spelare"
    assert all(getattr(player, "value_sek", 0) > 0 for player in club.players)


def test_captain_effect_requires_named_captain():
    players = [_make_player(i, Position.MF, skill=6) for i in range(1, 12)]
    captain = players[0]
    captain.traits.append(Trait.LEDARE)
    club = Club(name="Kapten FC", players=players, captain_id=captain.id)
    boost, cap_obj, uplift = _captain_effect(club, players[:11])
    assert cap_obj is captain
    assert boost > 0
    assert uplift > 0

    club.captain_id = None
    boost_empty, cap_none, uplift_empty = _captain_effect(club, players[:11])
    assert boost_empty == 0
    assert cap_none is None
    assert uplift_empty == 0


def test_schedule_substitutions_distributes_minutes():
    starters = [_make_player(i, Position.MF, skill=5) for i in range(1, 12)]
    bench_player = _make_player(20, Position.MF, skill=5)
    club = Club(
        name="Bytes IF",
        players=starters + [bench_player],
        substitution_plan=[SubstitutionRule(minute=60, player_in=bench_player.id, player_out=starters[4].id)],
    )
    minutes, participants, events = _schedule_substitutions(club, starters, [bench_player], [])
    assert minutes[starters[4].id] == 60
    assert minutes[bench_player.id] == 30
    assert bench_player in participants
    assert any(ev.player == bench_player for ev in events)


def test_referee_skill_influences_fouls():
    home_high = _make_club("Hemma")
    away_high = _make_club("Borta", start_id=100)
    random.seed(42)
    high_result = simulate_match(
        home_high,
        away_high,
        referee=Referee(skill=10, hardness=5),
        home_tactic=Tactic(),
        away_tactic=Tactic(),
        home_aggr=Aggressiveness("Aggressiv"),
        away_aggr=Aggressiveness("Aggressiv"),
    )

    home_low = _make_club("Hemma")
    away_low = _make_club("Borta", start_id=100)
    random.seed(42)
    low_result = simulate_match(
        home_low,
        away_low,
        referee=Referee(skill=1, hardness=5),
        home_tactic=Tactic(),
        away_tactic=Tactic(),
        home_aggr=Aggressiveness("Aggressiv"),
        away_aggr=Aggressiveness("Aggressiv"),
    )

    assert high_result.home_stats.fouls > low_result.home_stats.fouls
    assert high_result.away_stats.offsides >= low_result.away_stats.offsides


def test_dark_arts_increases_risk_against_strict_ref():
    home = _make_club("Hemmabos FC")
    away = _make_club("Bortalaget", start_id=200)

    random.seed(7)
    baseline = simulate_match(
        home,
        away,
        referee=Referee(skill=8, hardness=9),
        home_tactic=Tactic(),
        away_tactic=Tactic(),
        home_aggr=Aggressiveness("Aggressiv"),
        away_aggr=Aggressiveness("Aggressiv"),
    )

    random.seed(7)
    sneaky = simulate_match(
        home,
        away,
        referee=Referee(skill=8, hardness=9),
        home_tactic=Tactic(dark_arts=True),
        away_tactic=Tactic(),
        home_aggr=Aggressiveness("Aggressiv"),
        away_aggr=Aggressiveness("Aggressiv"),
    )

    assert sneaky.home_stats.fouls >= baseline.home_stats.fouls
    assert (
        sneaky.home_stats.yellows + sneaky.home_stats.reds
        >= baseline.home_stats.yellows + baseline.home_stats.reds
    )


def test_apply_weekly_finances_updates_cash_and_values():
    club_a = _make_club("A")
    club_b = _make_club("B", start_id=200)
    gs = _make_state([club_a, club_b])
    club_a.cash_sek = 100_000
    club_b.cash_sek = 50_000

    logs = apply_weekly_finances(gs, base_income=500_000)
    assert club_a.cash_sek == 600_000
    assert club_b.cash_sek == 550_000
    assert all("500,000" in line or "500 000" in line.replace("\u202f", " ") for line in logs)

    update_player_values(gs)
    assert all(getattr(p, "value_sek", 0) > 0 for p in club_a.players + club_b.players)


def test_update_stats_records_goalkeeper_clean_sheet_and_possession():
    home = _make_club("Hemma")
    away = _make_club("Borta", start_id=300)

    home_gk = next(p for p in home.players if p.position == Position.GK)
    away_gk = next(p for p in away.players if p.position == Position.GK)
    home_outfield = [p for p in home.players if p is not home_gk]
    away_outfield = [p for p in away.players if p is not away_gk]

    home_lineup = [home_gk] + home_outfield[:10]
    away_lineup = [away_gk] + away_outfield[:10]
    home_bench = [p for p in home.players if p not in home_lineup]
    away_bench = [p for p in away.players if p not in away_lineup]

    home_minutes = {p.id: 90 for p in home_lineup}
    away_minutes = {p.id: 90 for p in away_lineup}

    result = MatchResult(
        home=home,
        away=away,
        events=[],
        home_stats=TeamStats(
            goals=2,
            shots=11,
            shots_on=6,
            saves=3,
            woodwork=0,
            corners=5,
            fouls=9,
            offsides=2,
            yellows=1,
            reds=0,
            possession_pct=62,
        ),
        away_stats=TeamStats(
            goals=0,
            shots=5,
            shots_on=2,
            saves=4,
            woodwork=0,
            corners=1,
            fouls=12,
            offsides=1,
            yellows=2,
            reds=0,
            possession_pct=38,
        ),
        ratings={},
        home_minutes=home_minutes,
        away_minutes=away_minutes,
        home_lineup=home_lineup,
        away_lineup=away_lineup,
        home_bench=home_bench,
        away_bench=away_bench,
    )

    player_stats: dict[int, Any] = {}
    player_career_stats: dict[int, Any] = {}
    club_stats: dict[str, Any] = {}
    club_career_stats: dict[str, Any] = {}
    update_stats_from_result(
        result,
        competition="league",
        round_no=1,
        player_stats=player_stats,
        club_stats=club_stats,
        player_career_stats=player_career_stats,
        club_career_stats=club_career_stats,
    )

    assert player_stats[home_gk.id].clean_sheets == 1
    assert player_stats[away_gk.id].clean_sheets == 0
    assert player_career_stats[home_gk.id].clean_sheets == 1
    assert player_career_stats[away_gk.id].clean_sheets == 0

    home_stats = club_stats[home.name]
    away_stats = club_stats[away.name]
    assert home_stats.possession_for == 62
    assert away_stats.possession_for == 38
    assert home_stats.shots_against == 5
    assert away_stats.shots_against == 11

    home_career = club_career_stats[home.name]
    away_career = club_career_stats[away.name]
    assert home_career.possession_for == 62
    assert away_career.possession_for == 38


def test_evaluate_bot_signings_handles_multiple_listings():
    seller_one = _make_club("S1")
    seller_two = _make_club("S2", start_id=200)
    buyer = _make_club("Buyer", start_id=400)
    buyer.cash_sek = 10_000_000
    gs = _make_state([seller_one, seller_two, buyer])

    first_listing = TransferListing(
        player_id=seller_one.players[0].id,
        club_name=seller_one.name,
        price_sek=300_000,
    )
    second_listing = TransferListing(
        player_id=seller_two.players[0].id,
        club_name=seller_two.name,
        price_sek=320_000,
    )
    gs.transfer_list = [first_listing, second_listing]

    with patch("manager.core.economy.random.random", return_value=0.0), patch(
        "manager.core.economy.random.choice", return_value=buyer
    ):
        logs = evaluate_bot_signings(gs)

    assert len(logs) == 2
    assert all("köpte" in entry for entry in logs)
    assert all(p.id not in {first_listing.player_id, second_listing.player_id} for p in seller_one.players)
    assert all(p.id not in {first_listing.player_id, second_listing.player_id} for p in seller_two.players)
    assert any(p.id == first_listing.player_id for p in buyer.players)
    assert any(p.id == second_listing.player_id for p in buyer.players)
    assert gs.transfer_list == []


def test_accept_junior_offer_respects_maximum_squad():
    club = _make_club("Full FC")
    gs = _make_state([club])
    cycle = [Position.GK, Position.DF, Position.MF, Position.FW]
    while len(club.players) < 30:
        pid = 10_000 + len(club.players)
        pos = cycle[len(club.players) % len(cycle)]
        club.players.append(_make_player(pid, pos, skill=5))
    club.cash_sek = 5_000_000
    gs.junior_offers = {}
    generate_junior_offers(gs, club.name, 1)
    with pytest.raises(ValueError) as exc:
        accept_junior_offer(gs, club.name, 0)
    assert "max" in str(exc.value).lower()


def test_purchase_listing_blocks_full_roster():
    buyer = _make_club("Buyer")
    seller = _make_club("Seller", start_id=500)
    gs = _make_state([buyer, seller])
    cycle = [Position.GK, Position.DF, Position.MF, Position.FW]
    while len(buyer.players) < 30:
        pid = 20_000 + len(buyer.players)
        pos = cycle[len(buyer.players) % len(cycle)]
        buyer.players.append(_make_player(pid, pos, skill=5))
    free_agent = _make_player(30_000, Position.MF, skill=7)
    listing = TransferListing(
        player_id=None,
        club_name=None,
        price_sek=250_000,
        player_snapshot=player_to_dict(free_agent),
        note="fri agent",
    )
    gs.transfer_list = [listing]
    with pytest.raises(ValueError) as exc:
        purchase_listing(gs, buyer.name, 0)
    assert buyer.name in str(exc.value)


def test_end_season_generates_junior_offers():
    club_a = _make_club("Alpha")
    club_b = _make_club("Beta", start_id=200)
    gs = _make_state([club_a, club_b])
    gs.junior_offers = {}

    update_player_values(gs)
    end_season(gs)

    assert gs.junior_offers
    for club in (club_a, club_b):
        offers = gs.junior_offers.get(club.name)
        assert offers, f"{club.name} saknar auto-genererade juniorer"
        assert 1 <= len(offers) <= 3


def test_end_season_increments_age_and_retires_veterans():
    club = _make_club("Åldring FC")
    veteran = club.players[0]
    younger = club.players[1]
    veteran.age = 50
    younger_age = younger.age
    gs = _make_state([club])

    results = end_season(gs)

    assert younger.age == younger_age + 1
    assert veteran not in club.players
    veteran_progress = next((r for r in results if r.player_id == veteran.id), None)
    assert veteran_progress is not None
    assert "pension" in veteran_progress.note.lower()


def test_submit_transfer_bid_respects_context():
    seller = _make_club("Top FC")
    buyer = _make_club("Buyer FC", start_id=200)
    challenger = _make_club("Challenger", start_id=400)
    buyer.cash_sek = 12_000_000
    gs = _make_state([seller, buyer, challenger])

    update_player_values(gs)
    target = seller.players[0]
    value = int(getattr(target, "value_sek", 500_000))
    low_bid = max(50_000, int(value * 0.6))

    gs.table_snapshot = {
        seller.name: {"pts": 55, "gf": 60, "ga": 20},
        buyer.name: {"pts": 30, "gf": 35, "ga": 30},
        challenger.name: {"pts": 25, "gf": 28, "ga": 40},
    }

    accepted, message, _ = submit_transfer_bid(gs, buyer.name, target.id, low_bid)
    assert not accepted
    assert "avböjde" in message

    seller.cash_sek = 150_000
    high_bid = int(value * 1.6)
    accepted, message, player = submit_transfer_bid(gs, buyer.name, target.id, high_bid)
    assert accepted
    assert player is not None and player.id == target.id
    assert player in buyer.players
    assert all(p.id != target.id for p in seller.players)
    assert buyer.cash_sek == 12_000_000 - high_bid
    assert seller.cash_sek >= high_bid


def test_end_season_archives_and_resets_stats():
    club_a = _make_club("Alpha")
    club_b = _make_club("Beta", start_id=200)
    gs = _make_state([club_a, club_b])
    gs.ensure_containers()

    random.seed(3)
    result = simulate_match(
        club_a,
        club_b,
        referee=Referee(skill=6, hardness=6),
        home_tactic=Tactic(),
        away_tactic=Tactic(),
        home_aggr=Aggressiveness("Medel"),
        away_aggr=Aggressiveness("Medel"),
    )

    update_stats_from_result(
        result,
        competition="league",
        round_no=1,
        player_stats=gs.player_stats,
        club_stats=gs.club_stats,
        player_career_stats=gs.player_career_stats,
        club_career_stats=gs.club_career_stats,
    )

    assert gs.player_stats, "Säsongsstatistik ska fyllas efter match"
    tracked_player = club_a.players[0].id
    season_appearances = gs.player_stats[tracked_player].appearances

    end_season(gs)

    assert not gs.player_stats, "Säsongsstatistik ska nollställas inför ny säsong"
    assert not gs.club_stats, "Lagstatistik ska nollställas inför ny säsong"

    career_stats = gs.player_career_stats.get(tracked_player)
    assert career_stats is not None
    assert career_stats.appearances >= season_appearances
    assert getattr(career_stats, "seasons", 0) == 1

    assert 1 in gs.player_stats_history
    assert tracked_player in gs.player_stats_history[1]
    assert (
        gs.player_stats_history[1][tracked_player].appearances == season_appearances
    )

    assert 1 in gs.club_stats_history
    assert club_a.name in gs.club_stats_history[1]
    assert gs.club_career_stats[club_a.name].seasons == 1


def test_submit_transfer_bid_respects_squad_minimum():
    seller = _make_club("Seller FC")
    buyer = _make_club("Buyer FC", start_id=700)
    gs = _make_state([seller, buyer])
    buyer.cash_sek = 15_000_000

    gks = [p for p in seller.players if p.position is Position.GK]
    for extra in gks[1:]:
        seller.players.remove(extra)
    seller.preferred_lineup = [p.id for p in seller.players[:11]]
    target = gks[0]

    with pytest.raises(ValueError) as exc:
        submit_transfer_bid(gs, buyer.name, target.id, 5_000_000)
    assert seller.name in str(exc.value)


def test_format_feed_includes_lineups_and_icons():
    home = _make_club("Hemma")
    away = _make_club("Borta", start_id=900)
    random.seed(42)
    result = simulate_match(
        home,
        away,
        referee=Referee(skill=7, hardness=5),
        home_tactic=Tactic(),
        away_tactic=Tactic(),
        home_aggr=Aggressiveness("Medel"),
        away_aggr=Aggressiveness("Medel"),
    )

    feed = format_feed(result)
    assert "Laguppställningar" in feed
    assert "Lagdelsbetyg" in feed
    assert "Matchhändelser" in feed
    assert "Startelva" in feed
    assert "🔚 Slut" in feed
    assert home.name in feed and away.name in feed


def test_process_weekly_economy_runs_financial_hooks():
    club = _make_club("Echo")
    gs = _make_state([club])
    club.cash_sek = 100_000

    with patch("manager.core.economy.refresh_transfer_market") as mock_refresh, patch(
        "manager.core.economy.evaluate_bot_signings", return_value=["bot"]
    ) as mock_bots, patch("manager.core.economy.update_player_values") as mock_values:
        logs = process_weekly_economy(gs, base_income=400_000)

    assert club.cash_sek == 500_000
    mock_refresh.assert_called_once()
    mock_bots.assert_called_once()
    mock_values.assert_called_once()
    assert any("400" in line or "400" in line.replace("\u202f", " ") for line in logs)
    assert "bot" in logs[-1]
