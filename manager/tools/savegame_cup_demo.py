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
from manager.core.cup import CupRules
from manager.core.cup_state import (
    advance_cup_round,
    create_cup_state,
    finish_cup,
)
from manager.core.state import GameState


def main() -> None:
    # Skapa liga + schema
    rules = LeagueRules(format="rak", teams_per_div=8, levels=1, double_round=True)
    league = generate_league("CupSaveLiga", rules)
    fixtures = build_league_schedule(league)
    div = league.divisions[0]

    cfg = SeasonConfig()

    # Skapa GameState och påbörja säsongen
    gs = GameState(
        season=1,
        league=league,
        fixtures_by_division=fixtures,
        current_round=1,
        history=None,
    )
    from manager.core.history import HistoryStore

    gs.history = HistoryStore()

    table = {}
    # Spela 1 ligaomgång
    for res in play_round(fixtures[div.name], 1, cfg):
        apply_result_to_table(table, res)
    gs.current_round = 2

    # Starta cupen (mitt i säsongen)
    gs.cup_state = create_cup_state(
        div.clubs[:], CupRules(two_legged=True, final_two_legged=False)
    )

    # Spela EN cuprunda → spara
    round_results = advance_cup_round(
        gs.cup_state,
        referee=cfg.referee,
        home_tactic=cfg.home_tactic,
        away_tactic=cfg.away_tactic,
        home_aggr=cfg.home_aggr,
        away_aggr=cfg.away_aggr,
    )
    print(
        f"Spelade en cuprunda ({len(round_results)} matcher), {len(gs.cup_state.current_clubs)} lag kvar."
    )

    gs.save("saves/savegame_cup.json")
    print("Sparade med pågående cup till saves/savegame_cup.json")

    # Ladda igen
    loaded = GameState.load("saves/savegame_cup.json")
    print(
        f"Laddade: säsong {loaded.season}, nästa ligaomgång {loaded.current_round}, cup finished={bool(loaded.cup_state and loaded.cup_state.finished)}"
    )

    # Spela klart cupen
    if loaded.cup_state and not loaded.cup_state.finished:
        remaining_rounds = finish_cup(
            loaded.cup_state,
            referee=cfg.referee,
            home_tactic=cfg.home_tactic,
            away_tactic=cfg.away_tactic,
            home_aggr=cfg.home_aggr,
            away_aggr=cfg.away_aggr,
        )
        total_matches = sum(len(r) for r in remaining_rounds)
        print(
            f"Cupen färdig! Vinnare: {loaded.cup_state.winner.name} (spelade {total_matches} matcher i de återstående rundorna)"
        )

    # Fortsätt ligan 1 runda till
    for res in play_round(
        loaded.fixtures_by_division[div.name], loaded.current_round, cfg
    ):
        apply_result_to_table(table, res)
    loaded.current_round += 1

    # Visa enkel tabellrad count
    rows = sort_table(table)
    print(f"Tabellrader: {len(rows)}; Topp: {rows[0].club.name} ({rows[0].pts}p)")


if __name__ == "__main__":
    main()
