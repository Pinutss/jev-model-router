"""Client HTTP JSON minimal, sans journaliser les en-tetes d'auth."""
from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from ..errors import ProviderError


def host_of(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc or url


def join_url(base: str, path: str) -> str:
    return base.rstrip("/") + "/" + path.lstrip("/")


def completions_url(base: str) -> str:
    normalized = base.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    return join_url(normalized, "chat/completions")


def post_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout: float = 30.0,
) -> Any:
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json", **headers},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except HTTPError as exc:
        raise ProviderError(f"HTTP {exc.code} depuis {host_of(url)}") from None
    except URLError as exc:
        raise ProviderError(f"reseau indisponible pour {host_of(url)}") from exc
    if not raw:
        raise ProviderError(f"reponse vide depuis {host_of(url)}")
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ProviderError(f"JSON invalide depuis {host_of(url)}") from exc
