from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, List, Tuple

from .club import Club
from .fixtures import Match, round_robin  # <-- använd direkt här
from .player import Player
from .history import HistoryStore, SeasonRecord
from .economy import roll_new_junior_offers
from .serialize import (
    club_stats_from_dict_map,
    club_stats_to_dict_map,
    player_stats_from_dict_map,
    player_stats_to_dict_map,
)
from .stats import ClubCareerStats, PlayerCareerStats

RETIREMENT_AGE = 51  # spelare som fyller 51 lämnar truppen inför nästa säsong


@dataclass(slots=True)
class PlayerProgress:
    player_id: int
    name: str
    club: str
    age: int
    minutes: int
    play_ratio: float
    form_season_before: float
    form_now_before: int
    bars_before: int
    hidden_before: int
    bars_delta: int
    hidden_after: int
    bars_after: int
    note: str = ""


def _has_trait(p: Player, *names: str) -> bool:
    traits = getattr(p, "traits", []) or []
    names_u = {n.upper() for n in names}
    for t in traits:
        nm = getattr(t, "name", str(t)).upper()
        if nm in names_u:
            return True
    return False


def _age_factors(age: int) -> Tuple[float, float]:
    """Returnerar (gain_factor, loss_factor) baserat på ålder."""
    if age <= 21:
        return 1.30, 0.70
    if 22 <= age <= 28:
        return 1.00, 1.00
    if 29 <= age <= 31:
        return 0.80, 1.10
    # 32+
    return 0.50, 1.50


def _apply_hidden_rollover(
    skill_open: int, hidden: int, max_delta_bars: int
) -> Tuple[int, int, int]:
    """
    Rulla hidden 1..99 → ändra bars (+/-), men begränsa total bar-förändring till max_delta_bars.
    Returnerar (bars, hidden, bars_delta).
    """
    bars_delta = 0
    # Uppåt
    while hidden > 99 and bars_delta < max_delta_bars:
        hidden -= 100
        skill_open += 1
        bars_delta += 1
    if hidden > 99 and bars_delta >= max_delta_bars:
        hidden = 99
    # Nedåt
    while hidden < 1 and bars_delta > -max_delta_bars:
        hidden += 100
        skill_open -= 1
        bars_delta -= 1
    if hidden < 1 and bars_delta <= -max_delta_bars:
        hidden = 1

    skill_open = max(1, min(30, skill_open))
    hidden = max(1, min(99, hidden))
    return skill_open, hidden, bars_delta


def _compute_expected_team_minutes(
    table_snapshot: Dict[str, Dict[str, int]], club: Club
) -> int:
    """
    Använd tabell-snapshot (uppdateras varje omgång) för uppskattning: matcher_spelade * 90.
    Om snapshot saknas → rimlig heuristik (ca 30 matcher = (16-1)*2).
    """
    row = (table_snapshot or {}).get(club.name)
    if row and "mp" in row:
        return int(row["mp"]) * 90
    teams = 16
    matches = (teams - 1) * 2
    return max(900, matches * 90)


def _progress_player(
    p: Player,
    club: Club,
    player_stats_map: Dict[int, any],
    table_snapshot: Dict[str, Dict[str, int]],
    captain_id: int | None = None,
    max_bars_change_per_season: int = 2,
) -> PlayerProgress:
    bars_before = int(getattr(p, "skill_open", 5))
    hidden_before = int(getattr(p, "skill_hidden", 50))
    form_now_before = int(getattr(p, "form_now", 10))
    form_season_before = float(getattr(p, "form_season", 10.0))
    age = int(getattr(p, "age", 24))

    s = player_stats_map.get(p.id)
    minutes = int(getattr(s, "minutes", 0)) if s is not None else 0
    team_minutes = _compute_expected_team_minutes(table_snapshot, club)
    play_ratio = minutes / team_minutes if team_minutes > 0 else 0.0

    gain = False
    loss = False
    if form_season_before > 10.0 and play_ratio >= 0.25:
        gain = True
    if form_season_before < 10.0 or play_ratio < 0.25:
        loss = True

    if gain and random.random() < 0.15:
        gain = False
    if loss and random.random() < 0.15:
        loss = False

    gain_f, loss_f = _age_factors(age)
    if _has_trait(p, "TRÄNINGSVILLIG", "TRAININGSVILLIG"):
        gain_f *= 1.20
    if _has_trait(p, "LEDARE"):
        gain_f *= 1.05
    if _has_trait(p, "INTELLIGENT"):
        gain_f *= 1.05
    if _has_trait(p, "SKADEBENÄGEN", "SKADBENÄGEN", "SKADEBENAGEN"):
        loss_f *= 1.25
    if captain_id is not None and p.id == captain_id:
        gain_f *= 1.05

    hidden = hidden_before
    bars = bars_before
    note_parts: List[str] = []
    bars_delta_sum = 0

    if gain and not loss:
        delta = random.randint(8, 20)
        delta = int(delta * (1.0 + 0.03 * (form_season_before - 10.0)))
        delta = int(delta * (0.6 + 1.2 * min(1.0, play_ratio)))
        delta = max(1, int(delta * gain_f))
        hidden += delta
        bars, hidden, bars_delta = _apply_hidden_rollover(
            bars, hidden, max_bars_change_per_season
        )
        bars_delta_sum += bars_delta
        note_parts.append(
            f"+{bars_delta} bar" if bars_delta > 0 else f"+{delta} hidden"
        )
    elif loss and not gain:
        delta = random.randint(5, 15)
        delta = int(delta * (1.0 + 0.03 * (10.0 - form_season_before)))
        delta = int(delta * (0.8 + 1.1 * (1.0 - min(1.0, play_ratio))))
        delta = max(1, int(delta * loss_f))
        hidden -= delta
        bars, hidden, bars_delta = _apply_hidden_rollover(
            bars, hidden, max_bars_change_per_season
        )
        bars_delta_sum += bars_delta
        note_parts.append(f"{bars_delta} bar" if bars_delta < 0 else f"-{delta} hidden")
    else:
        jitter = random.randint(-3, 3)
        hidden = max(1, min(99, hidden + jitter))
        note_parts.append("stabil")

    setattr(p, "skill_open", bars)
    setattr(p, "skill_hidden", hidden)
    setattr(p, "form_now", random.randint(9, 11))
    setattr(p, "form_season", 10.0)

    return PlayerProgress(
        player_id=p.id,
        name=f"{getattr(p, 'first_name', '')} {getattr(p, 'last_name', '')}".strip(),
        club=club.name,
        age=age,
        minutes=minutes,
        play_ratio=play_ratio,
        form_season_before=form_season_before,
        form_now_before=form_now_before,
        bars_before=bars_before,
        hidden_before=hidden_before,
        bars_delta=bars_delta_sum,
        hidden_after=hidden,
        bars_after=bars,
        note=", ".join(note_parts),
    )


def _build_new_league_schedule(league) -> Dict[str, List[Match]]:
    """
    Bygg nytt ligaschema från round_robin(div.clubs), oavsett hur den råkar
    returnera sina poster (par/list/Match). Vi normaliserar alltid till
    en lista av Match och säkrar att 'round' är satt.
    """
    fixtures: Dict[str, List[Match]] = {}

    for div in league.divisions:
        fixtures[div.name] = []
        rr = round_robin(div.clubs)

        if not rr:
            continue

        # Hjälpare: lägg till en Match med given round
        def add_m(m: Match, rno: int):
            # säkerställ att vi sätter rätt round-nummer (överskriv om det saknas)
            fixtures[div.name].append(Match(home=m.home, away=m.away, round=rno))

        # Fall A: rr[0] är en lista → vi tolkar det som "rundor"
        if isinstance(rr[0], list):
            for round_no, round_items in enumerate(rr, start=1):
                for itm in round_items:
                    if isinstance(itm, Match):
                        add_m(itm, round_no)
                    else:
                        home, away = itm
                        fixtures[div.name].append(
                            Match(home=home, away=away, round=round_no)
                        )
            continue

        # Fall B: platt lista. Kontrollera om posterna är Match-objekt eller tuples.
        if isinstance(rr[0], Match):
            # Om Match-objekten redan har .round, gruppera/sortera efter den.
            rounds: Dict[int, List[Match]] = {}
            mixed_without_round: List[Match] = []
            for m in rr:
                r = getattr(m, "round", None)
                if isinstance(r, int) and r > 0:
                    rounds.setdefault(r, []).append(m)
                else:
                    mixed_without_round.append(m)

            if rounds:
                # Använd rounds från datat själv
                for rno in sorted(rounds.keys()):
                    for m in rounds[rno]:
                        add_m(m, rno)

            if mixed_without_round:
                # Sätt ronder sekventiellt för de som saknade round
                # (enkelt: alla får nya ronder i följd efter de som fanns)
                start = (max(rounds.keys()) if rounds else 0) + 1
                for i, m in enumerate(mixed_without_round, start=start):
                    add_m(m, i)
            continue

        # Fall C: platt lista med tuples (home, away)
        # Sätt rundor sekventiellt (1..N)
        for i, pair in enumerate(rr, start=1):
            home, away = pair
            fixtures[div.name].append(Match(home=home, away=away, round=i))

    return fixtures


# --- NYTT: tabell & promotion/relegation -------------------------------


def _final_table_for_div(division, table_snapshot: Dict[str, Dict[str, int]]):
    """Returnera klubbar i 'division' sorterade som slutlig tabell."""
    rows = _division_standings(division, table_snapshot)
    return [club for club, *_ in rows]


def _division_standings(
    division, table_snapshot: Dict[str, Dict[str, int]]
) -> List[tuple]:
    rows = []
    for club in division.clubs:
        r = (table_snapshot or {}).get(
            club.name, {"pts": 0, "gf": 0, "ga": 0, "w": 0, "d": 0}
        )
        pts = int(r.get("pts", 0))
        gf = int(r.get("gf", 0))
        ga = int(r.get("ga", 0))
        gd = gf - ga
        rows.append((club, pts, gd, gf))
    rows.sort(key=lambda x: (x[1], x[2], x[3], x[0].name), reverse=True)
    return rows


def _level_rankings(divisions, table_snapshot: Dict[str, Dict[str, int]]):
    """Sammanställ ranking över alla divisioner på samma nivå (sämst först)."""
    aggregated: List[tuple] = []
    for div in sorted(divisions, key=lambda d: d.name):
        for club, pts, gd, gf in _division_standings(div, table_snapshot):
            aggregated.append((club, div, pts, gd, gf))
    aggregated.sort(key=lambda x: (x[2], x[3], x[4], x[0].name))
    return aggregated


def _cup_result_labels(gs) -> Dict[str, str]:
    """Returnera textetiketter för lagens cupresultat baserat på matchloggen."""
    log = getattr(gs, "match_log", []) or []
    cup_matches = [mr for mr in log if getattr(mr, "competition", "") == "cup"]
    if not cup_matches:
        return {}

    max_round = max(int(getattr(mr, "round", 0)) for mr in cup_matches)
    if max_round <= 0:
        return {}

    stage_names = {}
    labels = ["Final", "Semifinal", "Kvartsfinal", "Åttondelsfinal"]
    for offset, label in enumerate(labels):
        stage = max_round - offset
        if stage > 0:
            stage_names[stage] = label

    progress: Dict[str, int] = {}
    for mr in cup_matches:
        round_no = int(getattr(mr, "round", 0))
        if round_no <= 0:
            continue
        for name in (getattr(mr, "home", None), getattr(mr, "away", None)):
            if not name:
                continue
            progress[name] = max(progress.get(name, 0), round_no)

    winner = None
    if getattr(gs, "cup_state", None) and getattr(gs.cup_state, "finished", False):
        winner = getattr(getattr(gs.cup_state, "winner", None), "name", None)
    elif cup_matches:
        # om sparfilen laddades efter cupen avslutats men innan winner hann skrivas
        finals = [mr for mr in cup_matches if int(getattr(mr, "round", 0)) == max_round]
        if finals:
            final = finals[-1]
            if final.home_goals != final.away_goals:
                winner = (
                    final.home
                    if final.home_goals > final.away_goals
                    else final.away
                )

    labels_by_club: Dict[str, str] = {}
    for club_name, stage in progress.items():
        if winner and club_name == winner:
            labels_by_club[club_name] = "Vinnare"
            continue
        label = stage_names.get(stage)
        if not label:
            label = f"Runda {stage}"
        labels_by_club[club_name] = label
    return labels_by_club


def _apply_promotion_relegation(league, table_snapshot, rules):
    """Flytta lag mellan intilliggande divisioner enligt rules.promote/relegate."""
    if max(rules.promote, rules.relegate) <= 0:
        return

    divisions_by_level: Dict[int, List] = {}
    for div in league.divisions:
        divisions_by_level.setdefault(int(getattr(div, "level", 1)), []).append(div)

    if len(divisions_by_level) < 2:
        return

    max_level = max(divisions_by_level)
    for level in range(1, max_level):
        upper_divs = divisions_by_level.get(level) or []
        lower_divs = divisions_by_level.get(level + 1) or []
        if not upper_divs or not lower_divs:
            continue

        lower_ranked = list(reversed(_level_rankings(lower_divs, table_snapshot)))
        upper_ranked = _level_rankings(upper_divs, table_snapshot)

        n_up = min(rules.promote, len(lower_ranked))
        n_down = min(rules.relegate, len(upper_ranked))
        move = min(n_up, n_down)
        if move <= 0:
            continue

        up_candidates = lower_ranked[:move]
        down_candidates = upper_ranked[:move]

        for club, div, *_ in up_candidates:
            if club in div.clubs:
                div.clubs.remove(club)
        for club, div, *_ in down_candidates:
            if club in div.clubs:
                div.clubs.remove(club)

        for club, _src_div, *_ in up_candidates:
            target = min(upper_divs, key=lambda d: (len(d.clubs), d.name))
            target.clubs.append(club)
        for club, _src_div, *_ in down_candidates:
            target = min(lower_divs, key=lambda d: (len(d.clubs), d.name))
            target.clubs.append(club)


def end_season(gs) -> List[PlayerProgress]:
    """
    Kör säsongsavslut:
      1) Spelarutveckling baserad på form, speltid, ålder och traits (max ±2 bars).
      2) Tillämpa upp-/nedflyttning mellan divisioner enligt LeagueRules (promote/relegate).
      3) Uppdatera historik och troféer.
      4) Arkivera säsongsstatistik, uppdatera karriärtotaler och nollställ säsongsräknare.
      5) Bygg nytt ligaschema för nästa säsong.
      6) Återställ ligaräknare/tabellsnapshot och töm cupläget.
      7) Returnera PlayerProgress-lista (används för säsongsrapporten i CLI).
    Obs: Karriärstatistik (player_stats/club_stats/match_log) lämnas intakt.
    """
    gs.ensure_containers()
    season_no = int(getattr(gs, "season", 1))
    results: List[PlayerProgress] = []
    progress_by_player: Dict[int, PlayerProgress] = {}
    retirements: List[tuple[Club, Player, int]] = []

    # 1) Spelarutveckling
    for div in gs.league.divisions:
        for club in div.clubs:
            cap = getattr(club, "captain_id", None)
            for p in list(club.players):
                res: PlayerProgress | None = None
                try:
                    res = _progress_player(
                        p,
                        club,
                        player_stats_map=gs.player_stats,
                        table_snapshot=gs.table_snapshot,
                        captain_id=cap,
                    )
                except Exception:
                    # Felskydd så en trasig post inte stoppar allt men åldra spelaren ändå
                    res = None

                if res is not None:
                    progress = res
                else:
                    progress = PlayerProgress(
                        player_id=p.id,
                        name=f"{getattr(p, 'first_name', '')} {getattr(p, 'last_name', '')}".strip(),
                        club=club.name,
                        age=int(getattr(p, "age", 24)),
                        minutes=0,
                        play_ratio=0.0,
                        form_season_before=float(getattr(p, "form_season", 10.0)),
                        form_now_before=int(getattr(p, "form_now", 10)),
                        bars_before=int(getattr(p, "skill_open", 5)),
                        hidden_before=int(getattr(p, "skill_hidden", 50)),
                        bars_delta=0,
                        hidden_after=int(getattr(p, "skill_hidden", 50)),
                        bars_after=int(getattr(p, "skill_open", 5)),
                        note="oförändrad",
                    )

                results.append(progress)
                progress_by_player[p.id] = progress

                new_age = int(getattr(p, "age", 24)) + 1
                setattr(p, "age", new_age)
                if new_age >= RETIREMENT_AGE:
                    retirements.append((club, p, new_age))
                    progress = progress_by_player.get(p.id)
                    if progress is not None:
                        note = "pensionerar sig"
                        if progress.note:
                            note = f"{progress.note}; {note}"
                        progress.note = note

    # Ta bort pensionerade spelare efter progressionen men före tabellhantering
    if retirements:
        retired_ids = {player.id for _club, player, _age in retirements}
        for club, player, _age in retirements:
            club.players = [p for p in club.players if getattr(p, "id", None) != player.id]
            if getattr(club, "preferred_lineup", None):
                club.preferred_lineup = [
                    pid for pid in club.preferred_lineup if pid != player.id
                ]
            if getattr(club, "bench_order", None):
                club.bench_order = [pid for pid in club.bench_order if pid != player.id]
            if getattr(club, "substitution_plan", None):
                club.substitution_plan = [
                    rule
                    for rule in club.substitution_plan
                    if getattr(rule, "player_in", None) != player.id
                    and getattr(rule, "player_out", None) != player.id
                ]

        listings = []
        for listing in getattr(gs, "transfer_list", []) or []:
            if listing.player_id and listing.player_id in retired_ids:
                continue
            listings.append(listing)
        gs.transfer_list = listings

    # 2) Upp-/nedflyttning (måste ske INNAN nytt schema byggs)
    _apply_promotion_relegation(gs.league, gs.table_snapshot, gs.league.rules)

    # 3) Historik + troféer
    history = getattr(gs, "history", None)
    if history is None or not isinstance(history, HistoryStore):
        history = HistoryStore()
        gs.history = history

    cup_labels = _cup_result_labels(gs)

    for div in gs.league.divisions:
        standings = _division_standings(div, gs.table_snapshot)
        for position, (club, *_rest) in enumerate(standings, start=1):
            cup_label = cup_labels.get(club.name)
            record = SeasonRecord(
                season=gs.season,
                league_position=position,
                cup_result=cup_label,
            )
            history.add_record(club.name, record)

            trophies = getattr(club, "trophies", None)
            if trophies is None:
                club.trophies = []
                trophies = club.trophies
            if position == 1:
                if int(getattr(div, "level", 1)) == 1:
                    trophies.append(f"🏆 {gs.league.name} säsong {gs.season}")
                else:
                    trophies.append(f"🥇 {div.name} säsong {gs.season}")

    # 4) Statistik – arkivera säsong och uppdatera karriärer
    player_snapshot_map = player_stats_from_dict_map(
        player_stats_to_dict_map(getattr(gs, "player_stats", {}) or {})
    )
    club_snapshot_map = club_stats_from_dict_map(
        club_stats_to_dict_map(getattr(gs, "club_stats", {}) or {})
    )

    if player_snapshot_map:
        player_history = getattr(gs, "player_stats_history", None)
        if not isinstance(player_history, dict):
            player_history = {}
            gs.player_stats_history = player_history
        player_history[season_no] = player_snapshot_map

    if club_snapshot_map:
        club_history_map = getattr(gs, "club_stats_history", None)
        if not isinstance(club_history_map, dict):
            club_history_map = {}
            gs.club_stats_history = club_history_map
        club_history_map[season_no] = club_snapshot_map

    player_career = getattr(gs, "player_career_stats", None)
    if not isinstance(player_career, dict):
        player_career = {}
        gs.player_career_stats = player_career
    for pid, stats in player_snapshot_map.items():
        appearances = int(getattr(stats, "appearances", 0))
        if appearances <= 0:
            continue
        career_obj = player_career.get(pid)
        if career_obj is None:
            career_obj = PlayerCareerStats(player_id=stats.player_id, club_name=stats.club_name)
            player_career[pid] = career_obj
        else:
            setattr(career_obj, "club_name", stats.club_name)
        if hasattr(career_obj, "seasons"):
            career_obj.seasons += 1

    club_career = getattr(gs, "club_career_stats", None)
    if not isinstance(club_career, dict):
        club_career = {}
        gs.club_career_stats = club_career
    for club_name, stats in club_snapshot_map.items():
        career_obj = club_career.get(club_name)
        if career_obj is None:
            career_obj = ClubCareerStats(club_name=club_name)
            club_career[club_name] = career_obj
        if hasattr(career_obj, "seasons") and int(getattr(stats, "played", 0)) > 0:
            career_obj.seasons += 1

    gs.player_stats = {}
    gs.club_stats = {}

    # 5) Ny säsong + nytt schema
    gs.season += 1
    gs.fixtures_by_division = _build_new_league_schedule(gs.league)
    roll_new_junior_offers(gs)

    # 6) Nollställ inför ny säsong
    gs.current_round = 1
    gs.table_snapshot = {}
    gs.cup_state = None  # ny cup startas separat nästa säsong

    # 7) Returnera progressionen för rapport
    return results
