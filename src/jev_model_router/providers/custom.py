"""Endpoint compatible fourni par l'utilisateur."""
from __future__ import annotations

from ..errors import ConfigurationError
from ..models import ModelProfile, RouteRequest, RouteResult
from ..router import HeuristicRouter
from .http import post_json
from .scores import parse_score_list


class CustomProvider:
    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        timeout: float = 30.0,
        router: HeuristicRouter | None = None,
    ) -> None:
        if not base_url:
            raise ConfigurationError("JEV_BASE_URL est obligatoire pour le provider custom")
        self._base_url = base_url
        self._api_key = api_key
        self._timeout = timeout
        self._router = router or HeuristicRouter()

    def route(self, models: list[ModelProfile], request: RouteRequest) -> RouteResult:
        payload = {
            "task": request.task,
            "models": [
                {
                    "id": model.id,
                    "name": model.name,
                    "provider": model.provider,
                    "model": model.model,
                    "quality": model.quality,
                    "cost": model.cost,
                    "latency": model.latency,
                    "capabilities": list(model.capabilities),
                }
                for model in models
            ],
        }
        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        raw = post_json(self._base_url, payload, headers, timeout=self._timeout)
        scores = parse_score_list(raw)
        return self._router.route(models, request, jev_scores=scores)
