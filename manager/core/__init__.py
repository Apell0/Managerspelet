# Gör det lättare att importera i resten av projektet
from .club import Club, SubstitutionRule
from .cup import Cup, CupMatch, CupRules, generate_cup_bracket
from .cup_state import (
    CupState,
    advance_cup_round,
    build_cup_bracket,
    competition_round_best_xi,
    create_cup_state,
    cup_match_records_by_round,
    cup_round_best_xi,
    finish_cup,
    match_records_by_competition,
)
from .fixtures import Match, round_robin
from .generator import generate_club, generate_league, to_preview_dict
from .history import HistoryStore, SeasonRecord
from .league import Division, League, LeagueRules
from .livefeed import build_timeline, format_feed, format_match_report
from .match import (  # <-- stubbarna
    EventType,
    MatchResult,
    PlayerEvent,
    Referee,
    TeamStats,
    simulate_match,
)
from .player import Player, Position, Trait
from .ratings import compute_ratings_for_match, player_match_rating
from .schedule import build_league_schedule
from .season import SeasonConfig, play_cup, play_league, play_round
from .serialize import (
    club_from_dict,
    club_to_dict,
    fixtures_from_dict,
    fixtures_to_dict,
    league_from_dict,
    league_to_dict,
    player_from_dict,
    player_to_dict,
)
from .standings import TableRow, apply_result_to_table, best_xi_442, sort_table
from .state import GameState
from .tactics import (
    TACTICS,
    Aggression,
    TacticName,
    TacticProfile,
    aggression_modifiers,
    unit_scores,
)

__all__ = [
    "Player",
    "Position",
    "Trait",
    "Club",
    "SubstitutionRule",
    "League",
    "Division",
    "LeagueRules",
    "generate_club",
    "generate_league",
    "to_preview_dict",
    "round_robin",
    "Match",
    "build_league_schedule",
    "Cup",
    "CupRules",
    "CupMatch",
    "generate_cup_bracket",
    "MatchResult",
    "TeamStats",
    "EventType",
    "MatchResult",
    "PlayerEvent",
    "Referee",
    "TeamStats",
    "simulate_match",
    "Aggression",
    "TACTICS",
    "TacticName",
    "TacticProfile",
    "unit_scores",
    "aggression_modifiers",
    "TableRow",
    "apply_result_to_table",
    "sort_table",
    "best_xi_442",
    "HistoryStore",
    "SeasonRecord",
    "SeasonConfig",
    "play_round",
    "play_league",
    "play_cup",
    "player_match_rating",
    "compute_ratings_for_match",
    "player_to_dict",
    "player_from_dict",
    "club_to_dict",
    "club_from_dict",
    "league_to_dict",
    "league_from_dict",
    "fixtures_to_dict",
    "fixtures_from_dict",
    "GameState",
    "CupState",
    "create_cup_state",
    "advance_cup_round",
    "finish_cup",
    "build_cup_bracket",
    "match_records_by_competition",
    "cup_match_records_by_round",
    "competition_round_best_xi",
    "cup_round_best_xi",
    "build_timeline",
    "format_feed",
    "format_match_report",
]
