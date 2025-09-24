from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from manager.api import CareerManager, GameService, ServiceContext, ServiceError


def _parse_json_payload(args: argparse.Namespace) -> Dict[str, Any]:
    if getattr(args, "data", None):
        return json.loads(args.data)
    if not sys.stdin.isatty():
        raw = sys.stdin.read().strip()
        if raw:
            return json.loads(raw)
    return {}


def _print_json(data: Any, pretty: bool = True) -> None:
    if pretty:
        json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
    else:
        json.dump(data, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


def _build_context(args: argparse.Namespace) -> ServiceContext:
    saves_dir = Path(getattr(args, "saves", "saves"))
    file_path = Path(args.file) if getattr(args, "file", None) else None
    return ServiceContext.from_paths(saves_dir, file_path)


def cmd_career_list(args: argparse.Namespace) -> None:
    ctx = _build_context(args)
    manager = CareerManager(ctx)
    result = manager.list_careers()
    _print_json(result)


def cmd_game_new(args: argparse.Namespace) -> None:
    ctx = _build_context(args)
    service = GameService(ctx)
    payload = _parse_json_payload(args)
    result = service.create(payload)
    _print_json(result)


def cmd_game_dump(args: argparse.Namespace) -> None:
    ctx = _build_context(args)
    service = GameService(ctx)
    contract = service.dump()
    _print_json(contract)


def cmd_game_save(args: argparse.Namespace) -> None:
    ctx = _build_context(args)
    service = GameService(ctx)
    result = service.save_as(args.name)
    _print_json(result)


def cmd_game_load(args: argparse.Namespace) -> None:
    ctx = _build_context(args)
    service = GameService(ctx)
    contract = service.load_career(args.career)
    _print_json(contract)


def cmd_options_set(args: argparse.Namespace) -> None:
    ctx = _build_context(args)
    service = GameService(ctx)
    payload = _parse_json_payload(args)
    result = service.update_options(payload)
    _print_json(result)


def cmd_table_get(args: argparse.Namespace) -> None:
    ctx = _build_context(args)
    service = GameService(ctx)
    contract = service.dump()
    standings = contract.get("standings", {})
    scope = getattr(args, "scope", "total")
    _print_json(standings.get(scope, []))


def cmd_fixtures_list(args: argparse.Namespace) -> None:
    ctx = _build_context(args)
    service = GameService(ctx)
    contract = service.dump()
    fixtures = contract.get("fixtures", [])
    data = []
    for fixture in fixtures:
        if args.type and args.type != "all" and fixture.get("competition") != args.type:
            continue
        if args.round and fixture.get("round") != args.round:
            continue
        data.append(fixture)
    _print_json(data)


def cmd_match_get(args: argparse.Namespace) -> None:
    ctx = _build_context(args)
    service = GameService(ctx)
    details = service.get_match_details(args.id)
    _print_json(details)


def cmd_match_set_result(args: argparse.Namespace) -> None:
    ctx = _build_context(args)
    service = GameService(ctx)
    payload = _parse_json_payload(args)
    result = service.set_match_result(args.id, payload)
    _print_json(result)


def cmd_match_simulate(args: argparse.Namespace) -> None:
    ctx = _build_context(args)
    service = GameService(ctx)
    result = service.simulate_match(args.id, getattr(args, "mode", "quick"))
    _print_json(result)


def cmd_team_get(args: argparse.Namespace) -> None:
    ctx = _build_context(args)
    service = GameService(ctx)
    contract = service.dump()
    teams = contract.get("teams", [])
    team = next((t for t in teams if t.get("id") == args.id), None)
    if not team:
        raise ServiceError(f"Lag '{args.id}' hittades inte.")
    team_data = dict(team)
    team_data["squad"] = contract.get("squads", {}).get(args.id, [])
    team_data["history"] = contract.get("history", {}).get(args.id, {})
    _print_json(team_data)


def cmd_squad_get(args: argparse.Namespace) -> None:
    ctx = _build_context(args)
    service = GameService(ctx)
    contract = service.dump()
    squad = contract.get("squads", {}).get(args.team, [])
    _print_json(squad)


def cmd_player_get(args: argparse.Namespace) -> None:
    ctx = _build_context(args)
    service = GameService(ctx)
    contract = service.dump()
    player = next((p for p in contract.get("players", []) if p.get("id") == args.id), None)
    if not player:
        raise ServiceError(f"Spelare '{args.id}' hittades inte.")
    stats = [row for row in contract.get("stats", {}).get("players_current", []) if row.get("player_id") == args.id]
    data = dict(player)
    data["stats"] = stats
    _print_json(data)


def cmd_stats_get(args: argparse.Namespace) -> None:
    ctx = _build_context(args)
    service = GameService(ctx)
    contract = service.dump()
    data = contract.get("stats", {}).get(args.scope)
    _print_json(data)


def cmd_youth_get(args: argparse.Namespace) -> None:
    ctx = _build_context(args)
    service = GameService(ctx)
    contract = service.dump()
    _print_json(contract.get("youth", {}))


def cmd_youth_set_preference(args: argparse.Namespace) -> None:
    ctx = _build_context(args)
    service = GameService(ctx)
    result = service.set_youth_preference(args.preference)
    _print_json(result)


def cmd_transfers_market(args: argparse.Namespace) -> None:
    ctx = _build_context(args)
    service = GameService(ctx)
    contract = service.dump()
    listings = contract.get("transfers", {}).get("market", [])
    if not args.affordable:
        _print_json(listings)
        return
    economy = contract.get("economy", {})
    balance = economy.get("balance")
    if balance is None:
        _print_json(listings)
        return
    filtered = [item for item in listings if item.get("price", 0) <= balance]
    _print_json(filtered)


def cmd_transfers_buy(args: argparse.Namespace) -> None:
    ctx = _build_context(args)
    service = GameService(ctx)
    result = service.buy_from_market(args.club, args.index)
    _print_json(result)


def cmd_transfers_bid(args: argparse.Namespace) -> None:
    ctx = _build_context(args)
    service = GameService(ctx)
    payload = _parse_json_payload(args)
    result = service.submit_transfer_bid(payload)
    _print_json(result)


def cmd_economy_get(args: argparse.Namespace) -> None:
    ctx = _build_context(args)
    service = GameService(ctx)
    contract = service.dump()
    _print_json(contract.get("economy", {}))


def cmd_economy_sponsor(args: argparse.Namespace) -> None:
    ctx = _build_context(args)
    service = GameService(ctx)
    result = service.sponsor_activity(args.club, args.amount)
    _print_json(result)


def cmd_mail_list(args: argparse.Namespace) -> None:
    ctx = _build_context(args)
    service = GameService(ctx)
    contract = service.dump()
    _print_json(contract.get("mail", []))


def cmd_mail_read(args: argparse.Namespace) -> None:
    ctx = _build_context(args)
    service = GameService(ctx)
    result = service.mark_mail_read(args.id)
    _print_json(result)


def cmd_cup_get(args: argparse.Namespace) -> None:
    ctx = _build_context(args)
    service = GameService(ctx)
    contract = service.dump()
    cups = contract.get("cups", {}).get("by_id", {})
    if args.id:
        data = cups.get(args.id)
        if not data:
            raise ServiceError(f"Cup '{args.id}' hittades inte.")
        _print_json(data)
        return
    if cups:
        _print_json(next(iter(cups.values())))
    else:
        _print_json({})


def cmd_season_start(args: argparse.Namespace) -> None:
    ctx = _build_context(args)
    service = GameService(ctx)
    result = service.start_season()
    _print_json(result)


def cmd_season_end(args: argparse.Namespace) -> None:
    ctx = _build_context(args)
    service = GameService(ctx)
    result = service.end_season()
    _print_json(result)


def cmd_calendar_next_week(args: argparse.Namespace) -> None:
    ctx = _build_context(args)
    service = GameService(ctx)
    result = service.next_week()
    _print_json(result)


def cmd_tactics_set(args: argparse.Namespace) -> None:
    ctx = _build_context(args)
    service = GameService(ctx)
    payload = _parse_json_payload(args)
    result = service.set_tactics(args.team, payload)
    _print_json(result)


def cmd_youth_accept(args: argparse.Namespace) -> None:
    ctx = _build_context(args)
    service = GameService(ctx)
    result = service.accept_junior(args.club, args.index)
    _print_json(result)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Managerspelet JSON CLI")
    parser.add_argument("--file", help="Sökväg till sparfil")
    parser.add_argument("--saves", default="saves", help="Sökväg till katalog med sparfiler")
    parser.add_argument("--data", help="JSON-data för muterande kommandon")

    sub = parser.add_subparsers(dest="command", required=True)

    # career
    career = sub.add_parser("career")
    career_sub = career.add_subparsers(dest="action", required=True)
    career_list = career_sub.add_parser("list")
    career_list.set_defaults(func=cmd_career_list)

    # game
    game = sub.add_parser("game")
    game_sub = game.add_subparsers(dest="action", required=True)
    game_new = game_sub.add_parser("new")
    game_new.set_defaults(func=cmd_game_new)
    game_dump = game_sub.add_parser("dump")
    game_dump.set_defaults(func=cmd_game_dump)
    game_save = game_sub.add_parser("save")
    game_save.add_argument("--name", required=True)
    game_save.set_defaults(func=cmd_game_save)
    game_load = game_sub.add_parser("load")
    game_load.add_argument("--career", required=True)
    game_load.set_defaults(func=cmd_game_load)

    # options
    options = sub.add_parser("options")
    options_sub = options.add_subparsers(dest="action", required=True)
    options_set = options_sub.add_parser("set")
    options_set.set_defaults(func=cmd_options_set)

    # table
    table = sub.add_parser("table")
    table_sub = table.add_subparsers(dest="action", required=True)
    table_get = table_sub.add_parser("get")
    table_get.add_argument("--scope", choices=["total", "home", "away"], default="total")
    table_get.set_defaults(func=cmd_table_get)

    # fixtures
    fixtures = sub.add_parser("fixtures")
    fixtures_sub = fixtures.add_subparsers(dest="action", required=True)
    fixtures_list = fixtures_sub.add_parser("list")
    fixtures_list.add_argument("--type", choices=["league", "cup", "all"], default=None)
    fixtures_list.add_argument("--round", type=int)
    fixtures_list.set_defaults(func=cmd_fixtures_list)

    # match
    match = sub.add_parser("match")
    match_sub = match.add_subparsers(dest="action", required=True)
    match_get = match_sub.add_parser("get")
    match_get.add_argument("--id", required=True)
    match_get.set_defaults(func=cmd_match_get)
    match_set = match_sub.add_parser("set-result")
    match_set.add_argument("--id", required=True)
    match_set.set_defaults(func=cmd_match_set_result)
    match_sim = match_sub.add_parser("simulate")
    match_sim.add_argument("--id", required=True)
    match_sim.add_argument("--mode", choices=["quick", "viewer"], default="quick")
    match_sim.set_defaults(func=cmd_match_simulate)

    # team
    team = sub.add_parser("team")
    team_sub = team.add_subparsers(dest="action", required=True)
    team_get = team_sub.add_parser("get")
    team_get.add_argument("--id", required=True)
    team_get.set_defaults(func=cmd_team_get)

    # squad
    squad = sub.add_parser("squad")
    squad_sub = squad.add_subparsers(dest="action", required=True)
    squad_get = squad_sub.add_parser("get")
    squad_get.add_argument("--team", required=True)
    squad_get.set_defaults(func=cmd_squad_get)

    # player
    player = sub.add_parser("player")
    player_sub = player.add_subparsers(dest="action", required=True)
    player_get = player_sub.add_parser("get")
    player_get.add_argument("--id", required=True)
    player_get.set_defaults(func=cmd_player_get)

    # stats
    stats = sub.add_parser("stats")
    stats_sub = stats.add_subparsers(dest="action", required=True)
    stats_get = stats_sub.add_parser("get")
    stats_get.add_argument(
        "--scope",
        choices=["players_current", "players_all", "club_current", "club_all", "leaders", "best_eleven"],
        required=True,
    )
    stats_get.set_defaults(func=cmd_stats_get)

    # youth
    youth = sub.add_parser("youth")
    youth_sub = youth.add_subparsers(dest="action", required=True)
    youth_get = youth_sub.add_parser("get")
    youth_get.set_defaults(func=cmd_youth_get)
    youth_set = youth_sub.add_parser("set-preference")
    youth_set.add_argument("--preference", choices=["GK", "DF", "MF", "FW"], required=True)
    youth_set.set_defaults(func=cmd_youth_set_preference)
    youth_accept = youth_sub.add_parser("accept")
    youth_accept.add_argument("--club", required=True)
    youth_accept.add_argument("--index", type=int, required=True)
    youth_accept.set_defaults(func=cmd_youth_accept)

    # transfers
    transfers = sub.add_parser("transfers")
    transfers_sub = transfers.add_subparsers(dest="action", required=True)
    transfers_market = transfers_sub.add_parser("market")
    transfers_market.add_argument("--affordable", action="store_true")
    transfers_market.set_defaults(func=cmd_transfers_market)
    transfers_buy = transfers_sub.add_parser("buy")
    transfers_buy.add_argument("--club", required=True)
    transfers_buy.add_argument("--index", type=int, required=True)
    transfers_buy.set_defaults(func=cmd_transfers_buy)
    transfers_bid = transfers_sub.add_parser("bid")
    transfers_bid.set_defaults(func=cmd_transfers_bid)

    # economy
    economy = sub.add_parser("economy")
    economy_sub = economy.add_subparsers(dest="action", required=True)
    economy_get = economy_sub.add_parser("get")
    economy_get.set_defaults(func=cmd_economy_get)
    economy_sponsor = economy_sub.add_parser("sponsor")
    economy_sponsor.add_argument("--club", required=True)
    economy_sponsor.add_argument("--amount", type=int, default=1_000_000)
    economy_sponsor.set_defaults(func=cmd_economy_sponsor)

    # mail
    mail = sub.add_parser("mail")
    mail_sub = mail.add_subparsers(dest="action", required=True)
    mail_list = mail_sub.add_parser("list")
    mail_list.set_defaults(func=cmd_mail_list)
    mail_read = mail_sub.add_parser("read")
    mail_read.add_argument("--id", required=True)
    mail_read.set_defaults(func=cmd_mail_read)

    # cup
    cup = sub.add_parser("cup")
    cup_sub = cup.add_subparsers(dest="action", required=True)
    cup_get = cup_sub.add_parser("get")
    cup_get.add_argument("--id")
    cup_get.set_defaults(func=cmd_cup_get)

    # season
    season = sub.add_parser("season")
    season_sub = season.add_subparsers(dest="action", required=True)
    season_start = season_sub.add_parser("start")
    season_start.set_defaults(func=cmd_season_start)
    season_end = season_sub.add_parser("end")
    season_end.set_defaults(func=cmd_season_end)

    # calendar
    calendar = sub.add_parser("calendar")
    calendar_sub = calendar.add_subparsers(dest="action", required=True)
    calendar_next = calendar_sub.add_parser("next-week")
    calendar_next.set_defaults(func=cmd_calendar_next_week)

    # tactics
    tactics = sub.add_parser("tactics")
    tactics_sub = tactics.add_subparsers(dest="action", required=True)
    tactics_set = tactics_sub.add_parser("set")
    tactics_set.add_argument("--team", required=True)
    tactics_set.set_defaults(func=cmd_tactics_set)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
        return 0
    except ServiceError as exc:
        _print_json({"ok": False, "error": {"code": "SERVICE_ERROR", "message": str(exc)}})
        return 1
    except json.JSONDecodeError as exc:
        _print_json({"ok": False, "error": {"code": "INVALID_JSON", "message": str(exc)}})
        return 1
    except Exception as exc:  # pragma: no cover - unexpected failure
        _print_json({"ok": False, "error": {"code": "UNEXPECTED_ERROR", "message": str(exc)}})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
