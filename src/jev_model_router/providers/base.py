"""Interface commune des providers."""
from __future__ import annotations

from typing import Protocol

from ..models import ModelProfile, RouteRequest, RouteResult


class DecisionProvider(Protocol):
    def route(
        self,
        models: list[ModelProfile],
        request: RouteRequest,
    ) -> RouteResult:
        """Retourne une decision de routage."""
        ...
