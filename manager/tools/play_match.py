from __future__ import annotations

from manager.core import Referee, generate_club, simulate_match


def main() -> None:
    home = generate_club("Hemma FC")
    away = generate_club("Borta IF")
    ref = Referee(skill=7, hard=6)

    result = simulate_match(home, away, referee=ref, seed=42)

    print(f"\n{home.name} vs {away.name} → {result.scoreline}")
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

    print("\nHändelser:")
    for ev in result.events:
        if ev.event.name == "GOAL":
            a = f" (assist: {ev.assist_by.full_name})" if ev.assist_by else ""
            print(f"{ev.minute}' MÅL: {ev.player.full_name}{a}")
        elif ev.event.name == "YELLOW":
            print(f"{ev.minute}' GULT: {ev.player.full_name}")
        elif ev.event.name == "RED":
            print(f"{ev.minute}' RÖTT: {ev.player.full_name}")


if __name__ == "__main__":
    main()
