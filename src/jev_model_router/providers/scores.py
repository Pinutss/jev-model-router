"""Normalisation des scores distants."""
from __future__ import annotations

from typing import Any

from ..errors import ProviderError


def parse_score_list(payload: Any) -> dict[str, float]:
    """Accepte une liste, ou un objet {scores|selected|models}."""
    data = payload
    if isinstance(data, dict):
        for key in ("scores", "selected", "models"):
            if key in data:
                data = data[key]
                break
    if not isinstance(data, list):
        raise ProviderError("reponse de scores invalide")
    scores: dict[str, float] = {}
    for row in data:
        if not isinstance(row, dict) or "id" not in row:
            continue
        raw = row.get("score", row.get("confidence", 0.0))
        try:
            score = float(raw)
        except (TypeError, ValueError):
            continue
        scores[str(row["id"])] = min(1.0, max(0.0, score))
    return scores
