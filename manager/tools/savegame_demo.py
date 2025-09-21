from __future__ import annotations

from manager.core import (
    LeagueRules,
    SeasonConfig,
    apply_result_to_table,
    build_league_schedule,
    generate_league,
    play_round,
    sort_table,
)
from manager.core.state import GameState


def main() -> None:
    # 1) Skapa ny säsong och schema
    rules = LeagueRules(format="rak", teams_per_div=8, levels=1, double_round=True)
    league = generate_league("SaveGameLiga", rules)
    fixtures = build_league_schedule(league)

    # 2) Skapa GameState (vi spelar Division 1 i detta demo)
    gs = GameState(
        season=1,
        league=league,
        fixtures_by_division=fixtures,
        current_round=1,  # startar på omgång 1
        history=None,  # fylls strax
    )
    from manager.core.history import HistoryStore

    gs.history = HistoryStore()

    cfg = SeasonConfig()

    # 3) Spela 2 omgångar, uppdatera tabell, spara
    table = {}
    for rnd in (1, 2):
        for res in play_round(fixtures[league.divisions[0].name], rnd, cfg):
            apply_result_to_table(table, res)
        gs.current_round = rnd + 1

    gs.save("saves/savegame.json")
    print("Sparade spel till saves/savegame.json")

    # 4) Ladda igen och fortsätt säsongen till slut
    loaded = GameState.load("saves/savegame.json")
    print(f"Laddade spel: säsong {loaded.season}, nästa omgång: {loaded.current_round}")

    max_round = max(
        m.round for m in loaded.fixtures_by_division[loaded.league.divisions[0].name]
    )
    for rnd in range(loaded.current_round, max_round + 1):
        for res in play_round(
            loaded.fixtures_by_division[loaded.league.divisions[0].name], rnd, cfg
        ):
            apply_result_to_table(table, res)
        loaded.current_round = rnd + 1

    # 5) Skriv ut sluttabell
    rows = sort_table(table)
    print(f"\n=== SLUTTABELL: {loaded.league.divisions[0].name} ===")
    print(
        f"{'Pl':>2}  {'Lag':<20} {'MP':>2} {'W':>2} {'D':>2} {'L':>2}  {'GF':>3} {'GA':>3} {'GD':>3}  {'Pts':>3}"
    )
    for i, r in enumerate(rows, start=1):
        losses = r.losses if hasattr(r, "losses") else getattr(r, "l", 0)
        print(
            f"{i:>2}  {r.club.name:<20} {r.mp:>2} {r.w:>2} {r.d:>2} {losses:>2}  {r.gf:>3} {r.ga:>3} {r.gd:>3}  {r.pts:>3}"
        )


if __name__ == "__main__":
    main()
