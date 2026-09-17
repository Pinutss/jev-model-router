"""Juge LLM via une gateway OpenAI-compatible. Jamais de texte utilisateur."""
from __future__ import annotations

import json
import re
from typing import Any

from ..errors import ConfigurationError, ProviderError
from ..models import ModelProfile
from .http import completions_url, post_json
from .scores import parse_score_list

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.I)


class GatewayClient:
    """POST /chat/completions. N'accepte que la cle resolue hors corps HTTP."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout: float = 30.0,
        optional_key: bool = False,
    ) -> None:
        if not api_key and not optional_key:
            raise ConfigurationError("GATEWAY_API_KEY est obligatoire pour le provider jev")
        if not base_url:
            raise ConfigurationError("GATEWAY_BASE_URL est obligatoire pour le provider jev")
        if not model:
            raise ConfigurationError("GATEWAY_MODEL est obligatoire pour le provider jev")
        self._api_key = api_key
        self._url = completions_url(base_url)
        self._model = model
        self._timeout = timeout

    def score(self, task: str, models: list[ModelProfile]) -> dict[str, float]:
        catalog = [
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
        ]
        prompt = (
            "Tu es un juge de routage de modeles LLM. "
            "Reponds uniquement par un JSON : "
            '{"scores":[{"id":"...","score":0.0,"reason":"..."}]} '
            "score entre 0 et 1. "
            "Tu ne generes pas de texte utilisateur. "
            "Tu ne peux pas accorder de capacites.\n"
            f"Tache : {task}\n"
            f"Modeles : {json.dumps(catalog, ensure_ascii=False)}"
        )
        payload = {
            "model": self._model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": "Tu renvoies uniquement du JSON valide."},
                {"role": "user", "content": prompt},
            ],
        }
        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        response = post_json(self._url, payload, headers, timeout=self._timeout)
        return parse_score_list(_content_from_chat(response))


def _content_from_chat(response: Any) -> Any:
    if not isinstance(response, dict):
        raise ProviderError("reponse gateway invalide")
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ProviderError("reponse gateway sans choices")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        raise ProviderError("reponse gateway sans message")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ProviderError("reponse gateway vide")
    cleaned = _FENCE_RE.sub("", content.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ProviderError("JSON juge gateway invalide") from exc
