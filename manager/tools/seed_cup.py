from __future__ import annotations

from manager.core import (
    CupRules,
    LeagueRules,
    generate_cup_bracket,
    generate_league,
)


def main() -> None:
    print("SEED_CUP startar...")  # debug-rad

    rules = LeagueRules(format="rak", teams_per_div=8, levels=1)
    league = generate_league("CupTest-Liga", rules)
    clubs = league.divisions[0].clubs

    # Cup: dubbelmöte i alla rundor, finalen enkelmöte
    cup_rules = CupRules(two_legged=True, final_two_legged=False)
    cup = generate_cup_bracket("Svenska Cupen (demo)", clubs, cup_rules)

    for round_name, matches in cup.bracket.items():
        print(f"\n=== {round_name} ===")
        if not matches:
            print("(Endast byes i denna runda)")
        for m in matches:
            print(f"Leg {m.leg}: {m.home.name} vs {m.away.name}")


if __name__ == "__main__":
    main()
