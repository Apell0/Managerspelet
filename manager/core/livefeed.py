from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .match import EventType, MatchResult, PlayerEvent


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


def _fmt_goal(ev: PlayerEvent, res: MatchResult, score_h: int, score_a: int) -> str:
    assist = f" (assist: {_name(ev.assist_by)})" if ev.assist_by else ""
    return f"MÅL! {_name(ev.player)}{assist}  ({res.home.name} {score_h}–{score_a} {res.away.name})"


def build_timeline(result: MatchResult) -> List[FeedLine]:
    lines: List[FeedLine] = []
    lines.append(FeedLine(1, f"Avspark: {result.home.name} – {result.away.name}"))

    events = sorted(result.events, key=lambda e: getattr(e, "minute", 0))
    score_h = 0
    score_a = 0

    for ev in events:
        m = int(getattr(ev, "minute", 0) or 0)
        if ev.event is EventType.GOAL:
            if ev.player in result.home.players:
                score_h += 1
            else:
                score_a += 1
            lines.append(FeedLine(m, _fmt_goal(ev, result, score_h, score_a)))
        elif ev.event is EventType.SHOT_ON:
            lines.append(FeedLine(m, f"Skott på mål: {_name(ev.player)}"))
        elif ev.event is EventType.SHOT_OFF:
            lines.append(FeedLine(m, f"Skott utanför: {_name(ev.player)}"))
        elif ev.event is EventType.SAVE:
            lines.append(FeedLine(m, "Målvaktsräddning!"))
        elif ev.event is EventType.WOODWORK:
            lines.append(FeedLine(m, f"Stolpe/ribba! {_name(ev.player)}"))
        elif ev.event is EventType.CORNER:
            lines.append(FeedLine(m, "Hörna"))
        elif ev.event is EventType.FOUL:
            lines.append(FeedLine(m, f"Foul på {_name(ev.player)}"))
        elif ev.event is EventType.YELLOW:
            lines.append(FeedLine(m, "Gult kort"))
        elif ev.event is EventType.RED:
            lines.append(FeedLine(m, "RÖTT kort!"))
        elif ev.event is EventType.PENALTY_AWARDED:
            lines.append(FeedLine(m, f"Straff tilldelad ({_name(ev.player)})"))
        elif ev.event is EventType.PENALTY_SCORED:
            lines.append(FeedLine(m, f"Straffmål: {_name(ev.player)}"))
        elif ev.event is EventType.PENALTY_MISSED:
            lines.append(FeedLine(m, f"Straff missad: {_name(ev.player)}"))
        elif ev.event is EventType.OFFSIDE:
            lines.append(FeedLine(m, f"Offside: {_name(ev.player)}"))
        elif ev.event is EventType.INJURY:
            lines.append(FeedLine(m, f"Skada: {_name(ev.player)}"))
        elif ev.event is EventType.SUBSTITUTION:
            lines.append(FeedLine(m, "Byte"))

    lines.append(FeedLine(45, "Halvtid."))
    lines.append(
        FeedLine(
            90,
            f"SLUT! Resultat: {result.home.name} {result.home_stats.goals}–{result.away_stats.goals} {result.away.name}",
        )
    )
    return sorted(lines, key=lambda fl: fl.minute)


def format_feed(result: MatchResult) -> str:
    out = [f"=== {result.home.name} vs {result.away.name} ==="]
    for fl in build_timeline(result):
        out.append(f"{fl.minute:>2}'  {fl.text}")
    return "\n".join(out)


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
