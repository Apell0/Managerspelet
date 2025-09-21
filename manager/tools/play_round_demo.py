from __future__ import annotations

from manager.core import (
    TACTICS,
    Aggression,
    LeagueRules,
    Position,  # <-- viktigt: för att indexera bästa elvan
    Referee,
    TacticName,
    apply_result_to_table,
    best_xi_442,
    build_league_schedule,
    generate_league,
    simulate_match,
    sort_table,
)


def main() -> None:
    # 1) Skapa liga och schema
    rules = LeagueRules(format="rak", teams_per_div=8, levels=1, double_round=True)
    league = generate_league("DemoLiga", rules)
    schedules = build_league_schedule(league)
    div = league.divisions[0]
    fixtures = schedules[div.name]

    # 2) Omgång 1
    round1 = [m for m in fixtures if m.round == 1]

    # 3) Spela alla matcher i omgång 1
    results = []
    ref = Referee(skill=7, hard=6)
    for match in round1:
        res = simulate_match(
            match.home,
            match.away,
            referee=ref,
            seed=None,
            home_tactic=TACTICS[TacticName.BALANCED_442],
            away_tactic=TACTICS[TacticName.ATTACKING_433],
            home_aggr=Aggression.MEDEL,
            away_aggr=Aggression.MEDEL,
        )
        results.append(res)

    # 4) Uppdatera tabell
    table = {}
    for res in results:
        apply_result_to_table(table, res)

    sorted_rows = sort_table(table)

    # 5) Skriv ut tabellen
    print(f"\n=== TABELL efter omgång 1: {div.name} ===")
    print(
        f"{'Pl':>2}  {'Lag':<20} {'MP':>2} {'W':>2} {'D':>2} {'L':>2}  {'GF':>3} {'GA':>3} {'GD':>3}  {'Pts':>3}"
    )
    for i, row in enumerate(sorted_rows, start=1):
        print(
            f"{i:>2}  {row.club.name:<20} {row.mp:>2} {row.w:>2} {row.d:>2} {row.losses:>2}  {row.gf:>3} {row.ga:>3} {row.gd:>3}  {row.pts:>3}"
        )

    # 6) Bästa elvan (1–4–4–2)
    xi = best_xi_442(results)

    def _fmt(slot):
        return (
            ", ".join([f"{p.full_name} ({score:.1f})" for p, score in slot])
            if slot
            else "-"
        )

    print("\n=== BÄSTA ELVAN (1–4–4–2) – Omgång 1 ===")
    print("GK:", _fmt(xi[Position.GK]))
    print("DF:", _fmt(xi[Position.DF]))
    print("MF:", _fmt(xi[Position.MF]))
    print("FW:", _fmt(xi[Position.FW]))


if __name__ == "__main__":
    main()
