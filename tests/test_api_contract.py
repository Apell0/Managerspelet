import json
from pathlib import Path

import pytest

from manager.api import CareerManager, GameService, ServiceContext


@pytest.fixture()
def service(tmp_path: Path) -> GameService:
    ctx = ServiceContext.from_paths(tmp_path, tmp_path / "active.json")
    svc = GameService(ctx)
    payload = {
        "league_structure": "rak",
        "divisions": 1,
        "teams_per_division": 4,
        "user_team": {"name": "Test FC"},
    }
    svc.create(payload)
    return svc


def test_contract_contains_expected_sections(service: GameService):
    contract = service.dump()
    assert set(contract.keys()) >= {
        "meta",
        "options",
        "season",
        "league",
        "teams",
        "players",
        "standings",
        "fixtures",
        "matches",
        "squads",
        "youth",
        "transfers",
        "stats",
        "economy",
        "mail",
        "history",
    }
    assert contract["meta"]["career_id"].startswith("c-")
    assert contract["season"]["phase"] == "preseason"
    assert contract["league"]["structure"] in {"single_division", "pyramid"}
    assert contract["teams"], "ska finnas lag i kontraktet"
    assert contract["players"], "ska finnas spelare"


def test_career_manager_lists_created_game(service: GameService):
    ctx = service.context
    entries = CareerManager(ctx).list_careers()
    assert len(entries) == 1
    entry = entries[0]
    assert entry["career_id"].startswith("c-")
    assert entry["season"] == 1


def test_next_week_updates_calendar_and_ledger(service: GameService):
    before = service.dump()["economy"].get("ledger", [])
    result = service.next_week()
    after = service.dump()["economy"].get("ledger", [])
    assert result["week"] == 2
    assert len(after) >= len(before) + 1


def test_set_tactics_updates_club(service: GameService):
    contract = service.dump()
    team_id = contract["teams"][0]["id"]
    service.set_tactics(team_id, {"tactic": {"attacking": True, "tempo": 1.5}})
    state = service._load_state()
    club = next(
        c for div in state.league.divisions for c in div.clubs if getattr(c, "club_id", None) == team_id
    )
    assert club.tactic.attacking is True
    assert pytest.approx(club.tactic.tempo, rel=1e-3) == 1.5


def test_match_details_before_and_after_simulation(service: GameService):
    contract = service.dump()
    fixtures = contract.get("fixtures", [])
    assert fixtures, "en liga ska ha matcher schemalagda"
    match_id = fixtures[0]["match_id"]

    scheduled = service.get_match_details(match_id)
    assert scheduled["match"]["status"] == "scheduled"
    assert scheduled["events"] == []

    result = service.simulate_match(match_id, "viewer")
    assert result["ok"] is True
    assert result["match_id"] == match_id
    assert result["status"] == "final"

    details = service.get_match_details(match_id)
    assert details["match"]["status"] == "final"
    assert details["events"], "avslutad match ska ha händelser"
    assert details["lineups"]["home"], "hemmalaget ska lista spelare"
    assert set(details["ratings_by_unit"].keys()) == {"home", "away"}
    assert "possession" in details["stats"]
