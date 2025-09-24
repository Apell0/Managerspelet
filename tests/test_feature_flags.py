from __future__ import annotations

from pathlib import Path

import pytest

from manager.api import FeatureFlags, GameService, ServiceContext


def test_feature_flags_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MANAGER_FEATURES", "mock")
    monkeypatch.setenv("MANAGER_MOCK_SEED", "42")
    monkeypatch.setenv("MANAGER_MOCK_PATH", str(tmp_path / "mock_state.json"))
    monkeypatch.setenv("MANAGER_PERSIST_CHANGES", "1")
    flags = FeatureFlags.from_env()
    assert flags.mock_mode is True
    assert flags.mock_seed == 42
    assert flags.mock_data_path == tmp_path / "mock_state.json"
    assert flags.persist_changes is True


def test_game_service_mock_mode_does_not_touch_disk(tmp_path: Path) -> None:
    flags = FeatureFlags(mock_mode=True)
    ctx = ServiceContext.from_paths(tmp_path, tmp_path / "active.json", flags=flags)
    service = GameService(ctx)

    contract = service.dump()

    assert contract["meta"]["career_id"] == flags.mock_career_id
    assert not (tmp_path / "active.json").exists()

    def _set_title(gs):
        gs.meta["name"] = "Mock Career"
        return gs.meta["name"]

    result = service.apply(_set_title)
    assert result == "Mock Career"
    assert service.dump()["meta"]["name"] == "Mock Career"


def test_transaction_persists_changes(tmp_path: Path) -> None:
    ctx = ServiceContext.from_paths(tmp_path, tmp_path / "career.json")
    service = GameService(ctx)
    payload = {
        "league_structure": "rak",
        "divisions": 1,
        "teams_per_division": 4,
        "user_team": {"name": "Testare"},
    }
    service.create(payload)

    with service.transaction() as state:
        state.meta["custom"] = "demo"

    refreshed = service.dump()
    assert refreshed["meta"].get("custom") == "demo"
