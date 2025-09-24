from __future__ import annotations

from dataclasses import dataclass
from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

from .match import EventType, MatchResult, PlayerEvent, player_event_summary


UNIT_LABELS = {
    "GK": "Målvakt",
    "DF": "Backar",
    "MF": "Mittfält",
    "FW": "Anfall",
}


@dataclass(slots=True)
class FeedLine:
    minute: int
    text: str


def _name(p) -> str:
    if p is None:
        return ""
    if hasattr(p, "full_name"):
        return p.full_name
    fn = getattr(p, "first_name", "")
    ln = getattr(p, "last_name", "")
    return (f"{fn} {ln}").strip() or f"#{getattr(p, 'id', '?')}"


def _icon_string(events: Dict[str, object]) -> str:
    if not events:
        return ""

    parts: List[str] = []

    def _minute_list(value) -> List[int]:
        minutes: List[int] = []
        if isinstance(value, (list, tuple, set)):
            for raw in value:
                try:
                    minutes.append(int(raw))
                except (TypeError, ValueError):
                    continue
        return minutes

    def _count(value: object) -> int:
        if isinstance(value, (list, tuple, set)):
            return sum(1 for item in value if item is not None)
        try:
            return int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0

    def add(icon: str, raw_value: object, minute_key: str | None = None) -> None:
        if minute_key:
            minutes = _minute_list(events.get(minute_key))
            if minutes:
                parts.extend(f"{icon}{minute}'" for minute in minutes)
                return
        count = _count(raw_value)
        if count > 0:
            parts.append(icon if count == 1 else f"{icon}×{count}")

    add("⚽", events.get("goals"), "goal_minutes")
    add("🅰", events.get("assists"), "assist_minutes")
    add("🟨", events.get("yellows"), "yellows")
    add("🟥", events.get("reds"), "reds")
    add("❌", events.get("pens_missed"), "pens_missed")
    if events.get("injury"):
        parts.append("✚")
    if events.get("sub_in") is not None:
        parts.append(f"↩{events['sub_in']}'")
    if events.get("sub_out") is not None:
        parts.append(f"↪{events['sub_out']}'")
    return " ".join(parts)


def _player_row(
    player,
    minutes_map: Dict[int, int],
    ratings: Dict[int, float],
    summary: Dict[int, Dict[str, object]],
) -> str:
    pos_obj = getattr(player, "position", None)
    pos = getattr(getattr(pos_obj, "value", None), "upper", lambda: None)()
    if not pos:
        pos = getattr(getattr(pos_obj, "name", None), "upper", lambda: "?")()
    if not pos:
        pos = "?"
    name = _name(player)
    pid = getattr(player, "id", None)
    minutes = int(minutes_map.get(pid, 0)) if pid is not None else 0
    minutes_txt = f"{minutes:>3}'" if minutes else " -- "
    rating = ratings.get(pid) if pid is not None else None
    rating_txt = f"{rating:>4.1f}" if rating is not None else "  --"
    icons = _icon_string(summary.get(pid, {}))
    unused = "  – ej använd" if minutes == 0 else ""
    return f"{pos:<2} {name:<24} {minutes_txt}  {rating_txt}  {icons}{unused}"


def _collect_team_players(
    team,
    lineup: Iterable,
    bench: Iterable,
    minutes_map: Dict[int, int],
) -> Tuple[List, List]:
    lineup_list = list(lineup)
    bench_entries: List[Tuple[int, object]] = [(idx, player) for idx, player in enumerate(bench)]
    seen_ids = {getattr(p, "id", None) for p in lineup_list}
    seen_ids.update(getattr(p, "id", None) for _, p in bench_entries)

    extra_index = len(bench_entries)
    for pid in minutes_map.keys():
        if pid in seen_ids:
            continue
        extra = next((p for p in team.players if getattr(p, "id", None) == pid), None)
        if extra is not None:
            bench_entries.append((extra_index, extra))
            extra_index += 1
            seen_ids.add(pid)

    bench_sorted = sorted(
        bench_entries,
        key=lambda entry: (
            -int(minutes_map.get(getattr(entry[1], "id", None), 0)),
            entry[0],
        ),
    )

    bench_list = [player for _, player in bench_sorted]
    return lineup_list, bench_list


def _team_block(
    result: MatchResult,
    *,
    is_home: bool,
    summary: Dict[int, Dict[str, object]],
) -> List[str]:
    team = result.home if is_home else result.away
    lineup = result.home_lineup if is_home else result.away_lineup
    bench = result.home_bench if is_home else result.away_bench
    minutes_map = result.home_minutes if is_home else result.away_minutes
    lineup_list, bench_list = _collect_team_players(team, lineup, bench, minutes_map)

    lines = [team.name]
    dark_flag = getattr(result, "home_dark_arts" if is_home else "away_dark_arts", False)
    if dark_flag:
        lines[0] = f"{team.name} 🕶️ (tjuvknep)"
    if lineup_list:
        lines.append("  Startelva:")
        for player in lineup_list:
            lines.append(
                "    "
                + _player_row(player, minutes_map, result.ratings, summary)
            )
    else:
        lines.append("  Startelva: saknas")

    if bench_list:
        lines.append("  Bänk:")
        for player in bench_list:
            lines.append(
                "    "
                + _player_row(player, minutes_map, result.ratings, summary)
            )
    return lines


def _unit_rating_lines(
    result: MatchResult,
    *,
    is_home: bool,
) -> List[str]:
    team = result.home if is_home else result.away
    lineup = result.home_lineup if is_home else result.away_lineup
    bench = result.home_bench if is_home else result.away_bench
    minutes_map = result.home_minutes if is_home else result.away_minutes

    players = list(lineup) + list(bench)
    ids = {getattr(p, "id", None) for p in players}
    for pid in minutes_map.keys():
        if pid in ids:
            continue
        extra = next((p for p in team.players if getattr(p, "id", None) == pid), None)
        if extra is not None:
            players.append(extra)
            ids.add(pid)

    buckets: Dict[str, List[Tuple[float, int]]] = {key: [] for key in UNIT_LABELS}
    for player in players:
        pid = getattr(player, "id", None)
        if pid is None:
            continue
        minutes = int(minutes_map.get(pid, 0))
        if minutes <= 0:
            continue
        rating = result.ratings.get(pid)
        if rating is None:
            continue
        pos_obj = getattr(player, "position", None)
        pos = getattr(getattr(pos_obj, "value", None), "upper", lambda: None)()
        if not pos:
            pos = getattr(getattr(pos_obj, "name", None), "upper", lambda: "")()
        if pos in buckets:
            buckets[pos].append((rating, minutes))

    lines = [f"{team.name}:"]
    for key, label in UNIT_LABELS.items():
        entries = buckets.get(key, [])
        if not entries:
            bar = "○" * 10
            rating_txt = "--"
        else:
            total_minutes = sum(m for _, m in entries)
            weighted = (
                sum(r * m for r, m in entries) / total_minutes if total_minutes else None
            )
            if weighted is None:
                bar = "○" * 10
                rating_txt = "--"
            else:
                filled = max(0, min(10, round(weighted)))
                bar = "●" * filled + "○" * (10 - filled)
                rating_txt = f"{weighted:.1f}"
        lines.append(f"  {label:<10} {bar} {rating_txt}")
    return lines


def build_timeline(result: MatchResult) -> List[FeedLine]:
    lines: List[FeedLine] = [FeedLine(0, f"Avspark: {result.home.name} – {result.away.name}")]

    events = sorted(result.events, key=lambda e: getattr(e, "minute", 0))
    score_h = 0
    score_a = 0
    home_ids = {getattr(p, "id", None) for p in result.home.players}
    away_ids = {getattr(p, "id", None) for p in result.away.players}

    for ev in events:
        minute = int(getattr(ev, "minute", 0) or 0)
        player = getattr(ev, "player", None)
        pid = getattr(player, "id", None)

        if ev.event in {EventType.GOAL, EventType.PENALTY_SCORED}:
            if pid in home_ids:
                score_h += 1
            elif pid in away_ids:
                score_a += 1
            icon = "⚽"
            label = "MÅL" if ev.event is EventType.GOAL else "Straffmål"
            assist = f" (assist: {_name(ev.assist_by)})" if ev.assist_by else ""
            text = (
                f"{icon} {label}: {_name(player)}{assist}  "
                f"({result.home.name} {score_h}–{score_a} {result.away.name})"
            )
        elif ev.event is EventType.PENALTY_MISSED:
            text = f"❌ Straff missad: {_name(player)}"
        elif ev.event is EventType.YELLOW:
            text = f"🟨 Gult kort: {_name(player)}"
        elif ev.event is EventType.RED:
            text = f"🟥 Rött kort: {_name(player)}"
        elif ev.event is EventType.SHOT_ON:
            text = f"🎯 Skott på mål: {_name(player)}"
        elif ev.event is EventType.SHOT_OFF:
            text = f"➖ Skott utanför: {_name(player)}"
        elif ev.event is EventType.SAVE:
            text = "🧤 Målvaktsräddning"
        elif ev.event is EventType.WOODWORK:
            text = f"🔔 Stolpe/ribba: {_name(player)}"
        elif ev.event is EventType.CORNER:
            text = "⚑ Hörna"
        elif ev.event is EventType.FOUL:
            text = f"🚫 Foul på {_name(player)}"
        elif ev.event is EventType.PENALTY_AWARDED:
            text = f"⚖️ Straff tilldelad ({_name(player)})"
        elif ev.event is EventType.OFFSIDE:
            text = f"⛔ Offside: {_name(player)}"
        elif ev.event is EventType.INJURY:
            text = f"✚ Skada: {_name(player)}"
        elif ev.event is EventType.SUBSTITUTION:
            if ev.assist_by:
                text = f"🔁 Byte: {_name(player)} in, {_name(ev.assist_by)} ut"
            else:
                note = f" ({ev.note})" if getattr(ev, "note", "") else ""
                text = f"🔁 Byte: {_name(player)} in{note}"
        else:
            continue

        lines.append(FeedLine(minute, text))

    lines.append(FeedLine(45, "⏸️ Halvtid"))
    lines.append(
        FeedLine(
            90,
            f"🔚 Slut: {result.home.name} {result.home_stats.goals}–{result.away_stats.goals} {result.away.name}",
        )
    )
    return sorted(lines, key=lambda fl: fl.minute)


def format_feed(result: MatchResult) -> str:
    summary = player_event_summary(result.events)
    out_lines = [f"=== {result.home.name} vs {result.away.name} ===", "", "Laguppställningar:"]

    home_block = _team_block(result, is_home=True, summary=summary)
    away_block = _team_block(result, is_home=False, summary=summary)

    out_lines.extend(f"  {line}" if idx == 0 else line for idx, line in enumerate(home_block))
    out_lines.append("")
    out_lines.extend(f"  {line}" if idx == 0 else line for idx, line in enumerate(away_block))

    out_lines.append("")
    out_lines.append("Lagdelsbetyg:")
    for line in _unit_rating_lines(result, is_home=True):
        out_lines.append(f"  {line}")
    for line in _unit_rating_lines(result, is_home=False):
        out_lines.append(f"  {line}")

    out_lines.append("")
    out_lines.append("Matchhändelser:")
    for fl in build_timeline(result):
        out_lines.append(f"  {fl.minute:>2}'  {fl.text}")

    return "\n".join(out_lines)


def format_match_report(result: MatchResult) -> str:
    h, a = result.home.name, result.away.name
    hs, as_ = result.home_stats, result.away_stats
    resline = f"{h} {hs.goals}–{as_.goals} {a}"
    return "\n".join(
        [
            "--- Matchrapport ---",
            f"Resultat: {resline}",
            f"Skott: {h} {hs.shots} ({hs.shots_on} på mål) – {as_.shots} ({as_.shots_on} på mål) {a}",
            f"Hörnor: {hs.corners}-{as_.corners}  Offside: {hs.offsides}-{as_.offsides}",
            f"Kort: Gula {hs.yellows}-{as_.yellows}  Röda {hs.reds}-{as_.reds}",
            f"Fouls: {hs.fouls}-{as_.fouls}  Räddningar: {hs.saves}-{as_.saves}",
            f"Bollinnehav: {hs.possession_pct}% – {as_.possession_pct}%",
        ]
    )
