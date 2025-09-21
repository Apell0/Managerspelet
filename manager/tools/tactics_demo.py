from __future__ import annotations

from manager.core import (
    TACTICS,
    Aggression,
    Referee,
    TacticName,
    generate_club,
    simulate_match,
)


def main() -> None:
    home = generate_club("Hemma FC")
    away = generate_club("Borta IF")
    ref = Referee(skill=7, hard=6)

    # Testa en taktisk matchup: 4-2-3-1 high press vs 4-1-4-1 counter
    result = simulate_match(
        home,
        away,
        referee=ref,
        seed=123,
        home_tactic=TACTICS[TacticName.HIGH_PRESS_4231],
        away_tactic=TACTICS[TacticName.COUNTER_4141],
        home_aggr=Aggression.AGGRESSIV,
        away_aggr=Aggression.LUGN,
    )

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
        tag = (
            "MÅL"
            if ev.event.name == "GOAL"
            else ("GULT" if ev.event.name == "YELLOW" else "RÖTT")
        )
        extra = (
            f" (assist: {ev.assist_by.full_name})"
            if getattr(ev, "assist_by", None)
            else ""
        )
        print(f"{ev.minute}' {tag}: {ev.player.full_name}{extra}")


if __name__ == "__main__":
    main()
