"""API utilities for exposing GameState as JSON contracts."""

from .contracts import build_contract
from .services import (
    CareerManager,
    FeatureFlags,
    GameService,
    ServiceContext,
    ServiceError,
)

__all__ = [
    "build_contract",
    "CareerManager",
    "FeatureFlags",
    "GameService",
    "ServiceContext",
    "ServiceError",
]
