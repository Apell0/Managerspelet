from __future__ import annotations

from pprint import pprint

from manager.core import LeagueRules, generate_league, to_preview_dict


def main() -> None:
    rules = LeagueRules(format="rak", teams_per_div=16, levels=1)
    league = generate_league("Testligan", rules)
    pprint(to_preview_dict(league))


if __name__ == "__main__":
    main()
