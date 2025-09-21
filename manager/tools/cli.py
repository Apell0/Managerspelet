from __future__ import annotations

import argparse
from pathlib import Path

from manager.core import (
    LeagueRules,
    SeasonConfig,
    build_league_schedule,
    generate_league,
    play_round,
)
from manager.core.cup import CupRules
from manager.core.cup_state import advance_cup_round, create_cup_state, finish_cup
from manager.core.history import HistoryStore
from manager.core.standings import apply_result_to_table as apply_to_table
from manager.core.state import GameState
from manager.core.stats import update_stats_from_result


def ensure_loaded(path: Path) -> GameState:
    if not path.exists():
        raise SystemExit(f"Sparfilen finns inte: {path}")
    return GameState.load(str(path))


def cmd_new(args: argparse.Namespace) -> None:
    path = Path(args.file)
    if path.exists() and not args.force:
        raise SystemExit(
            f"Filen {path} finns redan. Använd --force för att skriva över."
        )
    rules = LeagueRules(
        format="rak",
        teams_per_div=args.teams,
        levels=1,
        double_round=not args.single_round,
    )
    league = generate_league(args.name, rules)
    fixtures = build_league_schedule(league)
    gs = GameState(
        season=1,
        league=league,
        fixtures_by_division=fixtures,
        current_round=1,
        history=HistoryStore(),
        cup_state=None,
    )
    gs.ensure_containers()
    path.parent.mkdir(parents=True, exist_ok=True)
    gs.save(str(path))
    print(
        f"Ny karriär skapad: {path}  (Liga: {league.name}, Div: {league.divisions[0].name})"
    )


def cmd_status(args: argparse.Namespace) -> None:
    gs = ensure_loaded(Path(args.file))
    div = gs.league.divisions[0]
    print(f"Säsong: {gs.season}")
    print(f"Liga: {gs.league.name}  Division: {div.name}  Klubbar: {len(div.clubs)}")
    print(f"Nästa ligaomgång: {gs.current_round}")
    print(f"Matchlogg: {len(gs.match_log)} matcher")
    print(
        f"Spelare med stats: {len(gs.player_stats)}  Lag med stats: {len(gs.club_stats)}"
    )
    if gs.cup_state:
        print(
            f"Cup: pågår | kvar lag: {len(gs.cup_state.current_clubs)} | klar: {gs.cup_state.finished} | vinnare: {getattr(gs.cup_state.winner, 'name', None)}"
        )
    else:
        print("Cup: ej startad")


def _update_table_snapshot(gs: GameState, results) -> None:
    """
    Uppdatera tabell-snapshotten (mp, w, d, losses, gf, ga, pts) baserat på en lista matchresultat.
    """
    snap = gs.table_snapshot or {}

    for res in results:
        # använd standings.apply_result_to_table på en temporär tabell och slå ihop värdena
        tmp = {}
        apply_to_table(tmp, res)
        for _, row in tmp.items():
            key = row.club.name
            r = snap.get(
                key,
                {"mp": 0, "w": 0, "d": 0, "losses": 0, "gf": 0, "ga": 0, "pts": 0},
            )

            r["mp"] += row.mp
            r["w"] += row.w
            r["d"] += row.d
            r["losses"] += row.losses
            r["gf"] += row.gf
            r["ga"] += row.ga
            r["pts"] += row.pts

            snap[key] = r

    gs.table_snapshot = snap


def cmd_play_round(args: argparse.Namespace) -> None:
    gs = ensure_loaded(Path(args.file))
    gs.ensure_containers()
    div = gs.league.divisions[0]
    fixtures = gs.fixtures_by_division[div.name]

    cfg = SeasonConfig()
    target_round = gs.current_round
    results = play_round(fixtures, target_round, cfg)

    # uppdatera stats + logg + tabell-snapshot
    for res in results:
        mr = update_stats_from_result(
            res,
            competition="league",
            round_no=target_round,
            player_stats=gs.player_stats,
            club_stats=gs.club_stats,
        )
        gs.match_log.append(mr)
    _update_table_snapshot(gs, results)

    gs.current_round = target_round + 1
    gs.save(args.file)
    print(
        f"Spelade ligaomgång {target_round}: {len(results)} matcher. Sparat → {args.file}"
    )


def cmd_start_cup(args: argparse.Namespace) -> None:
    gs = ensure_loaded(Path(args.file))
    if gs.cup_state and not gs.cup_state.finished:
        print("Cup finns redan och pågår.")
        return
    div = gs.league.divisions[0]
    gs.cup_state = create_cup_state(
        div.clubs[:],
        CupRules(
            two_legged=not args.single_leg, final_two_legged=args.final_two_legged
        ),
    )
    gs.save(args.file)
    print(f"Cup startad: {len(gs.cup_state.current_clubs)} lag i spel.")


def cmd_play_cup_round(args: argparse.Namespace) -> None:
    gs = ensure_loaded(Path(args.file))
    gs.ensure_containers()
    if not gs.cup_state:
        raise SystemExit("Ingen cup är startad. Kör: start-cup")
    cfg = SeasonConfig()
    rnd = advance_cup_round(
        gs.cup_state,
        referee=cfg.referee,
        home_tactic=cfg.home_tactic,
        away_tactic=cfg.away_tactic,
        home_aggr=cfg.home_aggr,
        away_aggr=cfg.away_aggr,
    )
    # uppdatera stats/logg
    round_index = (
        max((mr.round for mr in gs.match_log if mr.competition == "cup"), default=0) + 1
    )
    for res in rnd:
        mr = update_stats_from_result(
            res,
            competition="cup",
            round_no=round_index,
            player_stats=gs.player_stats,
            club_stats=gs.club_stats,
        )
        gs.match_log.append(mr)

    gs.save(args.file)
    print(
        f"Spelade {len(rnd)} cupmatcher. Kvar: {len(gs.cup_state.current_clubs)} lag. Klar: {gs.cup_state.finished}."
    )
    if gs.cup_state.finished and gs.cup_state.winner:
        print(f"Cupvinnare: {gs.cup_state.winner.name}")


def cmd_finish_cup(args: argparse.Namespace) -> None:
    gs = ensure_loaded(Path(args.file))
    gs.ensure_containers()
    if not gs.cup_state:
        raise SystemExit("Ingen cup är startad. Kör: start-cup")
    cfg = SeasonConfig()
    rounds = finish_cup(
        gs.cup_state,
        referee=cfg.referee,
        home_tactic=cfg.home_tactic,
        away_tactic=cfg.away_tactic,
        home_aggr=cfg.home_aggr,
        away_aggr=cfg.away_aggr,
    )
    # logga alla matcher
    start_index = (
        max((mr.round for mr in gs.match_log if mr.competition == "cup"), default=0) + 1
    )
    idx = start_index
    total = 0
    for rnd in rounds:
        for res in rnd:
            mr = update_stats_from_result(
                res,
                competition="cup",
                round_no=idx,
                player_stats=gs.player_stats,
                club_stats=gs.club_stats,
            )
            gs.match_log.append(mr)
            total += 1
        idx += 1

    gs.save(args.file)
    print(
        f"Cupen färdig. Spelade {total} matcher i återstående rundor. Vinnare: {gs.cup_state.winner.name}"
    )


def main() -> None:
    p = argparse.ArgumentParser(prog="manager-cli", description="Managerspelet CLI")
    p.add_argument(
        "--file", "-f", default="saves/career.json", help="Sökväg till sparfilen (JSON)"
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_new = sub.add_parser("new", help="Skapa ny karriär")
    p_new.add_argument("--name", default="KarriärLiga")
    p_new.add_argument("--teams", type=int, default=8)
    p_new.add_argument(
        "--single-round", action="store_true", help="Spela bara enkelmöten i ligan"
    )
    p_new.add_argument("--force", action="store_true", help="Skriv över befintlig fil")
    p_new.set_defaults(func=cmd_new)

    p_status = sub.add_parser("status", help="Visa save-status")
    p_status.set_defaults(func=cmd_status)

    p_round = sub.add_parser("play-round", help="Spela exakt en ligaomgång och spara")
    p_round.set_defaults(func=cmd_play_round)

    p_start_cup = sub.add_parser(
        "start-cup", help="Starta cupen i den aktuella säsongen"
    )
    p_start_cup.add_argument(
        "--single-leg",
        action="store_true",
        help="Gör cupen enkelmöten (final styrs separat)",
    )
    p_start_cup.add_argument(
        "--final-two-legged",
        action="store_true",
        help="Gör även finalen dubbelmöte (default: enkel)",
    )
    p_start_cup.set_defaults(func=cmd_start_cup)

    p_cup_round = sub.add_parser(
        "play-cup-round", help="Spela exakt en cuprunda och spara"
    )
    p_cup_round.set_defaults(func=cmd_play_cup_round)

    p_finish_cup = sub.add_parser("finish-cup", help="Spela klart cupen och spara")
    p_finish_cup.set_defaults(func=cmd_finish_cup)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
