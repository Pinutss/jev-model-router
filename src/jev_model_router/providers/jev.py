"""Client HTTP de l'API de decision JEV."""
from __future__ import annotations

from ..errors import ConfigurationError
from ..models import ModelProfile
from .http import post_json
from .scores import parse_score_list


class JevClient:
    """POST batch vers JEV_BASE_URL. N'accepte que JEV_API_KEY."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str = "jev-latest",
        timeout: float = 30.0,
    ) -> None:
        if not api_key:
            raise ConfigurationError("JEV_API_KEY est obligatoire pour le provider jev")
        if not base_url:
            raise ConfigurationError("JEV_BASE_URL est obligatoire pour le provider jev")
        self._api_key = api_key
        self._base_url = base_url
        self._model = model
        self._timeout = timeout

    def score(self, task: str, models: list[ModelProfile]) -> dict[str, float]:
        payload = {
            "task": task,
            "model": self._model,
            "models": [
                {
                    "id": item.id,
                    "name": item.name,
                    "provider": item.provider,
                    "model": item.model,
                    "quality": item.quality,
                    "cost": item.cost,
                    "latency": item.latency,
                    "capabilities": list(item.capabilities),
                }
                for item in models
            ],
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        return parse_score_list(post_json(self._base_url, payload, headers, timeout=self._timeout))
