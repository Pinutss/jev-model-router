"""Provider local : heuristique deterministe, hors reseau."""
from __future__ import annotations

from ..models import ModelProfile, RouteRequest, RouteResult
from ..router import HeuristicRouter


class LocalProvider:
    def __init__(self, router: HeuristicRouter | None = None) -> None:
        self._router = router or HeuristicRouter()

    def route(self, models: list[ModelProfile], request: RouteRequest) -> RouteResult:
        return self._router.route(models, request)
