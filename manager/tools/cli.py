from __future__ import annotations

import argparse
import time
from pathlib import Path

from manager.core import (
    LeagueRules,
    SeasonConfig,
    build_league_schedule,
    generate_league,
    play_round,
)
from manager.core.cup import CupRules
from manager.core.cup_state import advance_cup_round, create_cup_state
from manager.core.history import HistoryStore
from manager.core.livefeed import format_feed, format_match_report
from manager.core.season import Aggressiveness, Tactic
from manager.core.season_progression import end_season
from manager.core.standings import apply_result_to_table as apply_to_table
from manager.core.state import GameState
from manager.core.stats import update_stats_from_result
from manager.core.training import advance_week, list_training, start_form_training

# ---------------------------
# Hjälpare
# ---------------------------


def ensure_loaded(path: Path) -> GameState:
    if not path.exists():
        raise SystemExit(f"Sparfilen finns inte: {path}")
    return GameState.load(str(path))


def _update_table_snapshot(gs: GameState, results) -> None:
    snap = gs.table_snapshot or {}
    for res in results:
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


def _make_cfg(args) -> SeasonConfig:
    cfg = SeasonConfig()
    th = (
        float(args.tempo_home)
        if getattr(args, "tempo_home", None) is not None
        else cfg.home_tactic.tempo
    )
    ta = (
        float(args.tempo_away)
        if getattr(args, "tempo_away", None) is not None
        else cfg.away_tactic.tempo
    )
    cfg.home_tactic = Tactic(attacking=True, tempo=th)
    cfg.away_tactic = Tactic(defending=True, tempo=ta)
    return cfg


def _play_round_common(gs: GameState, target_round: int, cfg: SeasonConfig):
    div = gs.league.divisions[0]
    fixtures = gs.fixtures_by_division[div.name]
    return play_round(fixtures, target_round, cfg), cfg


def _find_club(gs: GameState, name: str):
    for div in gs.league.divisions:
        for c in div.clubs:
            if c.name.lower() == name.lower():
                return c
    return None


def _print_tactic(c) -> None:
    t = c.tactic
    a = c.aggressiveness
    print(
        f"Taktik för {c.name}:\n"
        f"  attacking={t.attacking}  defending={t.defending}  offside_trap={t.offside_trap}\n"
        f"  tempo={t.tempo:.2f}\n"
        f"Aggressivitet: {a.name}"
    )


def _max_league_round(gs: GameState) -> int:
    """Högsta rondnumret i nuvarande ligaschema (för första divisionen)."""
    div = gs.league.divisions[0]
    rounds = [m.round for m in gs.fixtures_by_division.get(div.name, [])]
    return max(rounds) if rounds else 1


# ---------------------------
# CLI-kommandon
# ---------------------------


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
    print(f"Matchlogg: {len(gs.match_log or [])} matcher")
    print(
        f"Spelare med stats: {len(gs.player_stats or {})}  Lag med stats: {len(gs.club_stats or {})}"
    )
    if gs.cup_state:
        print(
            f"Cup: pågår | kvar lag: {len(gs.cup_state.current_clubs)} "
            f"| klar: {gs.cup_state.finished} "
            f"| vinnare: {getattr(gs.cup_state.winner, 'name', None)}"
        )
    else:
        print("Cup: ej startad")
    if gs.training_orders:
        print(
            f"Träningsordrar: {len(gs.training_orders)} (kör 'training-status' för detaljer)"
        )


def cmd_play_round(args: argparse.Namespace) -> None:
    gs = ensure_loaded(Path(args.file))
    gs.ensure_containers()

    cfg = _make_cfg(args)
    target_round = gs.current_round

    # --- Steg 10.3: Spärra sista ligaomgången om cupen inte är klar
    if gs.cup_state and not gs.cup_state.finished:
        if target_round >= _max_league_round(gs):
            print("Cupen måste avslutas innan sista ligaomgången spelas.")
            print(
                "Kör 'start-cup' (om ej startad) och 'play-cup-round' eller 'watch --cup' tills cupen är klar."
            )
            return

    results, _cfg = _play_round_common(gs, target_round, cfg)

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


def cmd_watch(args: argparse.Namespace) -> None:
    gs = ensure_loaded(Path(args.file))
    gs.ensure_containers()
    delay = float(args.slow) if args.slow else None

    cfg = _make_cfg(args)

    if args.cup:
        if not gs.cup_state:
            print("Ingen cup är startad. Kör: start-cup")
            return

        results = advance_cup_round(
            gs.cup_state,
            referee=cfg.referee,
            home_tactic=cfg.home_tactic,
            away_tactic=cfg.away_tactic,
            home_aggr=cfg.home_aggr,
            away_aggr=cfg.away_aggr,
        )

        print(f"=== Cuprunda ({len(results)} matcher) ===")
        for i, res in enumerate(results, start=1):
            print(f"\n### Cupmatch {i}")
            print(format_feed(res))
            print()
            print(format_match_report(res))
            if delay:
                time.sleep(delay)

        round_index = (
            max(
                (mr.round for mr in (gs.match_log or []) if mr.competition == "cup"),
                default=0,
            )
            + 1
        )
        for res in results:
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
            f"\nCuprunda klar. Sparat → {args.file}. "
            f"Kvar lag: {len(gs.cup_state.current_clubs)} | Klar: {gs.cup_state.finished}"
        )
        if gs.cup_state.finished and gs.cup_state.winner:
            print(f"Cupvinnare: {gs.cup_state.winner.name}")

    else:
        # --- Steg 10.3: Spärra sista ligaomgången om cupen inte är klar
        if gs.cup_state and not gs.cup_state.finished:
            if gs.current_round >= _max_league_round(gs):
                print("Cupen måste avslutas innan sista ligaomgången spelas.")
                print(
                    "Kör 'start-cup' (om ej startad) och 'play-cup-round' eller 'watch --cup' tills cupen är klar."
                )
                return

        target_round = gs.current_round
        results, _cfg = _play_round_common(gs, target_round, cfg)

        print(f"=== Omgång {target_round} ({len(results)} matcher) ===")
        for i, res in enumerate(results, start=1):
            print(f"\n### Match {i}")
            print(format_feed(res))
            print()
            print(format_match_report(res))
            if delay:
                time.sleep(delay)

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
            f"\nOmgång {target_round} klar. Sparat → {args.file}. Nästa omgång: {gs.current_round}"
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

    cfg = _make_cfg(args)
    rnd = advance_cup_round(
        gs.cup_state,
        referee=cfg.referee,
        home_tactic=cfg.home_tactic,
        away_tactic=cfg.away_tactic,
        home_aggr=cfg.home_aggr,
        away_aggr=cfg.away_aggr,
    )

    round_index = (
        max(
            (mr.round for mr in (gs.match_log or []) if mr.competition == "cup"),
            default=0,
        )
        + 1
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
        f"Spelade {len(rnd)} cupmatcher. Kvar: {len(gs.cup_state.current_clubs)} lag. "
        f"Klar: {gs.cup_state.finished}."
    )
    if gs.cup_state.finished and gs.cup_state.winner:
        print(f"Cupvinnare: {gs.cup_state.winner.name}")


# ---------------------------
# Topplistor & matchlogg
# ---------------------------


def _top_players(gs: GameState, by: str, limit: int) -> None:
    gs.ensure_containers()
    stats = list(gs.player_stats.values())

    def key_rating(s):
        return (s.rating_avg, s.goals, s.assists)

    def key_goals(s):
        return (s.goals, s.assists, s.rating_avg)

    def key_assists(s):
        return (s.assists, s.goals, s.rating_avg)

    def key_yellows(s):
        return (s.yellows, s.reds)

    def key_reds(s):
        return (s.reds, s.yellows)

    if by == "rating":
        key = key_rating
    elif by == "goals":
        key = key_goals
    elif by == "assists":
        key = key_assists
    elif by == "yellows":
        key = key_yellows
    elif by == "reds":
        key = key_reds
    else:
        raise SystemExit(f"Okänt fält för players: {by}")

    stats.sort(key=key, reverse=True)
    print(f"TOP PLAYERS by {by} (limit {limit})")
    print(
        f"{'#':>2}  {'PlayerID':>7}  {'Club':<18}  {'App':>3} {'Min':>4}  {'G':>2} {'A':>2}  {'Y':>2} {'R':>2}  {'Rt':>4}"
    )
    for i, s in enumerate(stats[:limit], start=1):
        print(
            f"{i:>2}  {s.player_id:>7}  {s.club_name:<18}  "
            f"{s.appearances:>3} {s.minutes:>4}  {s.goals:>2} {s.assists:>2}  "
            f"{s.yellows:>2} {s.reds:>2}  {s.rating_avg:>4.1f}"
        )


def _top_clubs(gs: GameState, by: str, limit: int) -> None:
    gs.ensure_containers()
    stats = list(gs.club_stats.values())

    def key_points(c):
        return (c.points, c.goals_for - c.goals_against, c.goals_for)

    def key_gf(c):
        return (c.goals_for,)

    def key_ga(c):
        return (-c.goals_against,)

    def key_cs(c):
        return (c.clean_sheets,)

    def key_yellows(c):
        return (c.yellows,)

    def key_reds(c):
        return (c.reds,)

    if by == "points":
        key = key_points
    elif by == "gf":
        key = key_gf
    elif by == "ga":
        key = key_ga
    elif by == "clean_sheets":
        key = key_cs
    elif by == "yellows":
        key = key_yellows
    elif by == "reds":
        key = key_reds
    else:
        raise SystemExit(f"Okänt fält för clubs: {by}")

    stats.sort(key=key, reverse=True)
    print(f"TOP CLUBS by {by} (limit {limit})")
    print(
        f"{'#':>2}  {'Club':<20} {'P':>3} {'W':>3} {'D':>3} {'L':>3}  {'GF':>3} {'GA':>3} {'CS':>3}  {'Y':>3} {'R':>3}  {'Pts':>3}"
    )
    for i, c in enumerate(stats[:limit], start=1):
        print(
            f"{i:>2}  {c.club_name:<20} {c.played:>3} {c.wins:>3} {c.draws:>3} "
            f"{c.losses:>3}  {c.goals_for:>3} {c.goals_against:>3} {c.clean_sheets:>3}  "
            f"{c.yellows:>3} {c.reds:>3}  {c.points:>3}"
        )


def _show_match_log(gs: GameState, limit: int) -> None:
    gs.ensure_containers()
    log = gs.match_log[-limit:] if limit > 0 else gs.match_log
    print(f"LAST {len(log)} MATCHES")
    for i, mr in enumerate(log, start=max(1, len(gs.match_log or []) - len(log) + 1)):
        tag = "L" if mr.competition == "league" else "C"
        print(
            f"{i:>3} [{tag}] R{mr.round:<2}  {mr.home} {mr.home_goals}-{mr.away_goals} {mr.away}"
        )


# ---------------------------
# Taktik per klubb
# ---------------------------


def cmd_tactic_show(args):
    gs = ensure_loaded(Path(args.file))
    club = _find_club(gs, args.club)
    if not club:
        raise SystemExit(f"Hittade ingen klubb med namn: {args.club}")
    _print_tactic(club)


def cmd_tactic_set(args):
    gs = ensure_loaded(Path(args.file))
    gs.ensure_containers()
    club = _find_club(gs, args.club)
    if not club:
        raise SystemExit(f"Hittade ingen klubb med namn: {args.club}")

    if args.attacking is not None:
        club.tactic.attacking = bool(args.attacking)
        if club.tactic.attacking and args.defending is None:
            club.tactic.defending = False
    if args.defending is not None:
        club.tactic.defending = bool(args.defending)
        if club.tactic.defending and args.attacking is None:
            club.tactic.attacking = False
    if args.offside_trap is not None:
        club.tactic.offside_trap = bool(args.offside_trap)
    if args.tempo is not None:
        club.tactic.tempo = float(args.tempo)

    if args.aggr is not None:
        name = args.aggr.capitalize()
        if name not in ("Aggressiv", "Medel", "Lugn"):
            raise SystemExit("Ogiltig aggressivitet. Använd: Aggressiv | Medel | Lugn")
        club.aggressiveness = Aggressiveness(name)

    gs.save(args.file)
    print("Uppdaterad taktik:")
    _print_tactic(club)


# ---------------------------
# Training (Steg 9.3)
# ---------------------------


def cmd_training_start(args):
    gs = ensure_loaded(Path(args.file))
    gs.ensure_containers()
    try:
        order = start_form_training(gs, args.club, args.player)
    except ValueError as e:
        raise SystemExit(str(e))
    gs.save(args.file)
    print(
        f"Startade formträning: order #{order.id} för spelare {order.player_id} i {order.club_name} (200 000 kr)."
    )


def cmd_training_status(args):
    gs = ensure_loaded(Path(args.file))
    rows = list_training(gs)
    if not rows:
        print("Inga träningsordrar.")
        return
    print("Aktiva & avslutade träningsordrar:")
    for o in rows:
        print(
            f"#{o.id:>3}  {o.club_name:<18}  pid={o.player_id:<6}  weeks_left={o.weeks_left}  status={o.status}  {o.note}"
        )


def cmd_advance_week(args):
    gs = ensure_loaded(Path(args.file))
    gs.ensure_containers()
    logs = advance_week(gs)
    gs.save(args.file)
    if not logs:
        print("Veckan passerade. Inga formboostar den här gången.")
        return
    print("Veckan passerade – resultat:")
    for line in logs:
        print(" -", line)


# ---------------------------
# End Season (Steg 9.4)
# ---------------------------


def cmd_end_season(args):
    gs = ensure_loaded(Path(args.file))
    gs.ensure_containers()

    results = end_season(gs)

    # Rapport
    report_path = Path(args.report or "saves/season_report.txt")
    report_path.parent.mkdir(parents=True, exist_ok=True)

    # Gruppera per klubb
    by_club: dict[str, list] = {}
    for r in results:
        by_club.setdefault(r.club, []).append(r)

    club_names = sorted(by_club.keys(), key=lambda s: s.lower())
    for club in club_names:
        by_club[club].sort(
            key=lambda r: (r.bars_delta, r.bars_after, r.name), reverse=True
        )

    with report_path.open("w", encoding="utf-8") as f:
        f.write(f"SÄSONGSRAPPORT – Slut på säsong {gs.season - 1}\n")
        f.write("=" * 72 + "\n\n")
        f.write(
            "Kolumner:  Namn  (Ålder)  Minuter  Form_säs  Bars before→after  (Δ)  Not\n\n"
        )

        total_up = total_down = 0

        for club in club_names:
            rows = by_club[club]
            ups = sum(1 for r in rows if r.bars_delta > 0)
            downs = sum(1 for r in rows if r.bars_delta < 0)
            total_up += ups
            total_down += downs

            f.write(f"{club}\n")
            f.write("-" * len(club) + "\n")

            for r in rows:
                pr = int(round(r.play_ratio * 100))
                delta = f"{r.bars_delta:+d}"
                f.write(
                    f"  {r.name:<22}  ({r.age:>2})  "
                    f"min {r.minutes:>4} ({pr:>3}%)  "
                    f"form_säs {r.form_season_before:>4.1f}  "
                    f"bars {r.bars_before:>2}→{r.bars_after:>2}  ({delta:>+3})  "
                    f"{r.note}\n"
                )
            f.write(f"  └─ Summering: förbättrades: {ups}, försämrades: {downs}\n\n")

        f.write("-" * 72 + "\n")
        f.write(f"TOTALT – förbättrades: {total_up}, försämrades: {total_down}\n")

    gs.save(args.file)
    print(f"Säsong avslutad. Ny säsong: {gs.season}. Rapport sparad → {report_path}")
    print("Tips: kör 'status' och 'watch' för att se nya omgång 1.")


# ---------------------------
# Parser
# ---------------------------


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

    def add_tempo_args(sp: argparse.ArgumentParser):
        sp.add_argument(
            "--tempo-home",
            type=float,
            default=None,
            help="Tempo för hemmalag (t.ex. 0.9, 1.0, 1.2)",
        )
        sp.add_argument(
            "--tempo-away",
            type=float,
            default=None,
            help="Tempo för bortalag (t.ex. 0.9, 1.0, 1.2)",
        )

    p_round = sub.add_parser("play-round", help="Spela exakt en ligaomgång och spara")
    add_tempo_args(p_round)
    p_round.set_defaults(func=cmd_play_round)

    p_watch = sub.add_parser(
        "watch",
        help="Spela nästa ligaomgång (default) eller cuprunda (--cup) med livefeed",
    )
    p_watch.add_argument(
        "--cup", action="store_true", help="Titta på cuprunda istället för ligaomgång"
    )
    p_watch.add_argument(
        "--slow",
        nargs="?",
        default=None,
        help="Sekunders paus mellan matcher (valfritt)",
    )
    add_tempo_args(p_watch)
    p_watch.set_defaults(func=cmd_watch)

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
        "play-cup-round", help="Spela exakt en cuprunda och spara (utan livefeed)"
    )
    add_tempo_args(p_cup_round)
    p_cup_round.set_defaults(func=cmd_play_cup_round)

    p_top_p = sub.add_parser("top-players", help="Visa topplista för spelare")
    p_top_p.add_argument(
        "--by",
        choices=["goals", "assists", "rating", "yellows", "reds"],
        default="goals",
    )
    p_top_p.add_argument("--limit", type=int, default=10)
    p_top_p.set_defaults(
        func=lambda a: _top_players(ensure_loaded(Path(a.file)), a.by, a.limit)
    )

    p_top_c = sub.add_parser("top-clubs", help="Visa topplista för klubbar")
    p_top_c.add_argument(
        "--by",
        choices=["points", "gf", "ga", "clean_sheets", "yellows", "reds"],
        default="points",
    )
    p_top_c.add_argument("--limit", type=int, default=10)
    p_top_c.set_defaults(
        func=lambda a: _top_clubs(ensure_loaded(Path(a.file)), a.by, a.limit)
    )

    p_mlog = sub.add_parser("match-log", help="Visa senaste matcher ur sparfilen")
    p_mlog.add_argument(
        "--limit", type=int, default=20, help="Hur många matcher att visa (0=alla)"
    )
    p_mlog.set_defaults(
        func=lambda a: _show_match_log(ensure_loaded(Path(a.file)), a.limit)
    )

    p_tshow = sub.add_parser("tactic-show", help="Visa taktik för en klubb")
    p_tshow.add_argument("club", help="Klubbnamn exakt som i spelet")
    p_tshow.set_defaults(func=cmd_tactic_show)

    p_tset = sub.add_parser(
        "tactic-set", help="Ändra taktik/aggressivitet för en klubb"
    )
    p_tset.add_argument("club", help="Klubbnamn exakt som i spelet")
    p_tset.add_argument(
        "--attacking", type=int, choices=[0, 1], default=None, help="1 eller 0"
    )
    p_tset.add_argument(
        "--defending", type=int, choices=[0, 1], default=None, help="1 eller 0"
    )
    p_tset.add_argument(
        "--offside-trap", type=int, choices=[0, 1], default=None, help="1 eller 0"
    )
    p_tset.add_argument("--tempo", type=float, default=None, help="t.ex. 0.9, 1.0, 1.2")
    p_tset.add_argument(
        "--aggr", type=str, default=None, help="Aggressiv | Medel | Lugn"
    )
    p_tset.set_defaults(func=cmd_tactic_set)

    # --- Training-kommandon ---
    p_tstart = sub.add_parser(
        "training-start", help="Starta formträning (1 vecka, 200k) för en spelare"
    )
    p_tstart.add_argument("--club", required=True, help="Klubbnamn")
    p_tstart.add_argument("--player", type=int, required=True, help="Spelar-ID")
    p_tstart.set_defaults(func=cmd_training_start)

    p_tstatus = sub.add_parser(
        "training-status", help="Visa status för alla träningsordrar"
    )
    p_tstatus.set_defaults(func=cmd_training_status)

    p_advw = sub.add_parser("advance-week", help="Processa en vecka (formträning m.m.)")
    p_advw.set_defaults(func=cmd_advance_week)

    # --- End Season ---
    p_end = sub.add_parser(
        "end-season", help="Avsluta säsongen: spelarförändringar, ny säsong & rapport"
    )
    p_end.add_argument(
        "--report", default="saves/season_report.txt", help="Sökväg för rapportfilen"
    )
    p_end.set_defaults(func=cmd_end_season)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
