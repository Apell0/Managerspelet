from __future__ import annotations

from manager.core import MatchResult, generate_club


def main() -> None:
    home = generate_club("Hemma FC")
    away = generate_club("Borta IF")

    # Skapa ett tomt resultat (dvs inga mål, default-statistik)
    result = MatchResult(home=home, away=away)

    print(f"{home.name} vs {away.name} → {result.scoreline}")
    print(
        f"Skott på mål: {result.home_stats.shots_on_target}–{result.away_stats.shots_on_target}"
    )
    print(
        f"Bollinnehav: {result.home_stats.possession_pct}%–{result.away_stats.possession_pct}%"
    )
    print(
        f"Gula: {result.home_stats.yellow_cards}–{result.away_stats.yellow_cards} | "
        f"Röda: {result.home_stats.red_cards}–{result.away_stats.red_cards}"
    )


if __name__ == "__main__":
    main()
