from __future__ import annotations

from manager.core import (
    TACTICS,
    Aggression,
    CupRules,
    HistoryStore,
    LeagueRules,
    Referee,
    SeasonConfig,
    SeasonRecord,
    TacticName,
    apply_result_to_table,
    best_xi_442,
    build_league_schedule,
    generate_league,
    play_cup,
    play_round,
    sort_table,
)


def main() -> None:
    # 1) Setup liga + schema
    rules = LeagueRules(format="rak", teams_per_div=8, levels=1, double_round=True)
    league = generate_league("SäsongsLiga", rules)
    schedules = build_league_schedule(league)
    div = league.divisions[0]
    fixtures = schedules[div.name]
    max_round = max(m.round for m in fixtures)

    # 2) Säsongskonfig
    cfg = SeasonConfig(
        season_number=1,
        cup_before_last_n_rounds=3,
        referee=Referee(skill=7, hard=6),
        home_tactic=TACTICS[TacticName.BALANCED_442],
        away_tactic=TACTICS[TacticName.ATTACKING_433],
        home_aggr=Aggression.MEDEL,
        away_aggr=Aggression.MEDEL,
    )

    history = HistoryStore()

    # 3) Spela ligan t.o.m. (max_round - cup_before_last_n_rounds)
    table = {}
    all_results = []
    stop_before = max_round - cfg.cup_before_last_n_rounds
    for rnd in range(1, stop_before + 1):
        r = play_round(fixtures, rnd, cfg)
        all_results.extend(r)
        for res in r:
            apply_result_to_table(table, res)

    # 4) Spela cupen klart här emellan
    entrants = div.clubs[:]  # alla lag deltar
    cup_rules = CupRules(two_legged=True, final_two_legged=False)
    cup_rounds, cup_winner, final_txt = play_cup(entrants, cup_rules, cfg)
    print("\n=== Cupen ===")
    print(final_txt)

    # 5) Spela färdigt ligan
    last_round_results = []
    for rnd in range(stop_before + 1, max_round + 1):
        r = play_round(fixtures, rnd, cfg)
        if rnd == max_round:
            last_round_results.extend(r)
        all_results.extend(r)
        for res in r:
            apply_result_to_table(table, res)

    final_rows = sort_table(table)
    print(f"\n=== SLUTTABELL: {div.name} ===")
    print(
        f"{'Pl':>2}  {'Lag':<20} {'MP':>2} {'W':>2} {'D':>2} {'L':>2}  {'GF':>3} {'GA':>3} {'GD':>3}  {'Pts':>3}"
    )
    for i, row in enumerate(final_rows, start=1):
        losses = row.losses if hasattr(row, "losses") else getattr(row, "l", 0)
        print(
            f"{i:>2}  {row.club.name:<20} {row.mp:>2} {row.w:>2} {row.d:>2} {losses:>2}  {row.gf:>3} {row.ga:>3} {row.gd:>3}  {row.pts:>3}"
        )

    # 6) Bästa elvan för sista omgången
    if last_round_results:
        xi = best_xi_442(last_round_results)

        def _fmt(slot):
            return (
                ", ".join([f"{p.full_name} ({score:.1f})" for p, score in slot])
                if slot
                else "-"
            )

        print("\n=== BÄSTA ELVAN (1–4–4–2) – Sista omgången ===")
        from manager.core import Position

        print("GK:", _fmt(xi[Position.GK]))
        print("DF:", _fmt(xi[Position.DF]))
        print("MF:", _fmt(xi[Position.MF]))
        print("FW:", _fmt(xi[Position.FW]))

    # 7) Historik
    for i, row in enumerate(final_rows, start=1):
        history.add_record(
            row.club.name, SeasonRecord(season=cfg.season_number, league_position=i)
        )
    history.add_record(
        cup_winner.name, SeasonRecord(season=cfg.season_number, cup_result="Vinnare")
    )

    print("\n=== Historik (snapshot) ===")
    for club, records in history.snapshot().items():
        lines = [
            (
                f"s{r.season}: liga {r.league_position}"
                if r.league_position
                else f"s{r.season}: cup {r.cup_result}"
            )
            for r in records
        ]
        print(f"- {club}: " + "; ".join(lines))


if __name__ == "__main__":
    main()
