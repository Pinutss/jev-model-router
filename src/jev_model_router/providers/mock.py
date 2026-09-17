"""Provider de demonstration, deterministe, hors reseau."""
from __future__ import annotations

from ..models import ModelProfile, RouteRequest, RouteResult
from ..router import HeuristicRouter


class MockProvider:
    """Classement local fixe, pour `jev-model demo` et la CI."""

    def __init__(self) -> None:
        self._router = HeuristicRouter(require_keys=False)

    def route(self, models: list[ModelProfile], request: RouteRequest) -> RouteResult:
        return self._router.route(models, request)
