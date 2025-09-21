from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, List, Tuple

from .club import Club
from .fixtures import Match, round_robin  # <-- använd direkt här
from .player import Player


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
    # Sortera: poäng, målskillnad, gjorda mål
    rows.sort(key=lambda x: (x[1], x[2], x[3]), reverse=True)
    return [club for club, *_ in rows]


def _apply_promotion_relegation(league, table_snapshot, rules):
    """Flytta lag mellan intilliggande divisioner enligt rules.promote/relegate."""
    if rules.promote <= 0 and rules.relegate <= 0:
        return
    if len(league.divisions) < 2:
        return

    # Vi går uppifrån och parar varje division med den under
    for i in range(len(league.divisions) - 1):
        upper = league.divisions[i]
        lower = league.divisions[i + 1]

        upper_sorted = _final_table_for_div(upper, table_snapshot)
        lower_sorted = _final_table_for_div(lower, table_snapshot)

        n_up = min(rules.promote, len(lower_sorted))
        n_down = min(rules.relegate, len(upper_sorted))

        if n_up == 0 and n_down == 0:
            continue

        up_candidates = lower_sorted[:n_up]  # bästa i lägre division
        down_candidates = (
            upper_sorted[-n_down:] if n_down > 0 else []
        )  # sämsta i högre division

        # Ta bort kandidater från nuvarande listor
        upper.clubs = [c for c in upper.clubs if c not in down_candidates]
        lower.clubs = [c for c in lower.clubs if c not in up_candidates]

        # Lägg till i nya divisioner
        for c in up_candidates:
            upper.clubs.append(c)
        for c in down_candidates:
            lower.clubs.append(c)


def end_season(gs) -> List[PlayerProgress]:
    """
    Kör säsongsavslut:
      1) Spelarutveckling baserad på form, speltid, ålder och traits (max ±2 bars).
      2) Tillämpa upp-/nedflyttning mellan divisioner enligt LeagueRules (promote/relegate).
      3) Bygg nytt ligaschema för nästa säsong.
      4) Nollställ ligaräknare och tabellsnapshot; töm cupläget.
      5) Returnera PlayerProgress-lista (används för säsongsrapporten i CLI).
    Obs: Karriärstatistik (player_stats/club_stats/match_log) lämnas intakt.
    """
    results: List[PlayerProgress] = []

    # (Valfritt) om vi senare lagrar kapten per klubb kan den hämtas här.
    # Nu: None → liten kaptenbonus används inte.
    captain_by_club: Dict[str, int | None] = {}

    # 1) Spelarutveckling
    for div in gs.league.divisions:
        for club in div.clubs:
            cap = captain_by_club.get(club.name)
            for p in club.players:
                try:
                    res = _progress_player(
                        p,
                        club,
                        player_stats_map=gs.player_stats,
                        table_snapshot=gs.table_snapshot,
                        captain_id=cap,
                    )
                    results.append(res)
                except Exception:
                    # Felskydd så en trasig post inte stoppar allt
                    continue

    # 2) Upp-/nedflyttning (måste ske INNAN nytt schema byggs)
    _apply_promotion_relegation(gs.league, gs.table_snapshot, gs.league.rules)

    # 3) Ny säsong + nytt schema
    gs.season += 1
    gs.fixtures_by_division = _build_new_league_schedule(gs.league)

    # 4) Nollställ inför ny säsong
    gs.current_round = 1
    gs.table_snapshot = {}
    gs.cup_state = None  # ny cup startas separat nästa säsong

    # 5) Returnera progressionen för rapport
    return results
