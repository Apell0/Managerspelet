from manager.core import LeagueRules, generate_league, round_robin


def main():
    rules = LeagueRules(format="rak", teams_per_div=6, levels=1)
    league = generate_league("MiniLiga", rules)
    clubs = league.divisions[0].clubs
    matches = round_robin(clubs, double_round=True)
    for m in matches[:12]:  # skriv bara ut första 12 matcherna
        print(m)
    print(f"Totalt {len(matches)} matcher för {len(clubs)} lag")


if __name__ == "__main__":
    main()
