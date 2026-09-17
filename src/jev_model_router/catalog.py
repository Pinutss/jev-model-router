"""Catalogue multi-LLM : fusionner presets, fichier et environnement.

Les cles restent dans l'environnement. Aucune serialisation de valeur brute.
"""
from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .errors import ConfigurationError
from .models import ModelProfile, lookup_env_key

_CUSTOM_BASE_RE = re.compile(r"^JEV_LLM_([A-Z][A-Z0-9]*)_BASE_URL$")
_RESERVED_LLM_NAMES = frozenset({"DEFAULT", "STRATEGY"})

PRESETS: dict[str, dict[str, Any]] = {
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_envs": ("OPENROUTER_API_KEY", "GATEWAY_API_KEY"),
        "models": (
            {
                "id": "anthropic/claude-sonnet-4",
                "quality": 0.95,
                "cost": 0.55,
                "latency": 0.45,
                "capabilities": ("chat", "tools", "json", "coding", "vision"),
                "context_window": 200000,
            },
            {
                "id": "anthropic/claude-3.5-sonnet",
                "quality": 0.90,
                "cost": 0.50,
                "latency": 0.40,
                "capabilities": ("chat", "tools", "json", "coding", "vision"),
                "context_window": 200000,
            },
            {
                "id": "openai/gpt-4o-mini",
                "quality": 0.78,
                "cost": 0.12,
                "latency": 0.22,
                "capabilities": ("chat", "tools", "json"),
                "context_window": 128000,
            },
            {
                "id": "google/gemini-2.0-flash",
                "quality": 0.82,
                "cost": 0.18,
                "latency": 0.20,
                "capabilities": ("chat", "tools", "json"),
                "context_window": 1000000,
            },
        ),
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "api_key_envs": ("OPENAI_API_KEY",),
        "models": (
            {
                "id": "gpt-4o",
                "quality": 0.92,
                "cost": 0.70,
                "latency": 0.40,
                "capabilities": ("chat", "tools", "json", "coding", "vision"),
                "context_window": 128000,
            },
            {
                "id": "gpt-4o-mini",
                "quality": 0.78,
                "cost": 0.15,
                "latency": 0.20,
                "capabilities": ("chat", "tools", "json"),
                "context_window": 128000,
            },
        ),
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_envs": ("GROQ_API_KEY",),
        "models": (
            {
                "id": "llama-3.3-70b-versatile",
                "quality": 0.80,
                "cost": 0.10,
                "latency": 0.12,
                "capabilities": ("chat", "tools", "json"),
                "context_window": 128000,
            },
            {
                "id": "mixtral-8x7b-32768",
                "quality": 0.72,
                "cost": 0.08,
                "latency": 0.10,
                "capabilities": ("chat", "json"),
                "context_window": 32768,
            },
        ),
    },
    "together": {
        "base_url": "https://api.together.xyz/v1",
        "api_key_envs": ("TOGETHER_API_KEY",),
        "models": (
            {
                "id": "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
                "quality": 0.80,
                "cost": 0.20,
                "latency": 0.28,
                "capabilities": ("chat", "json"),
                "context_window": 128000,
            },
        ),
    },
    "fireworks": {
        "base_url": "https://api.fireworks.ai/inference/v1",
        "api_key_envs": ("FIREWORKS_API_KEY",),
        "models": (
            {
                "id": "accounts/fireworks/models/llama-v3p1-70b-instruct",
                "quality": 0.79,
                "cost": 0.20,
                "latency": 0.25,
                "capabilities": ("chat", "json"),
                "context_window": 128000,
            },
        ),
    },
    "mistral": {
        "base_url": "https://api.mistral.ai/v1",
        "api_key_envs": ("MISTRAL_API_KEY",),
        "models": (
            {
                "id": "mistral-large-latest",
                "quality": 0.88,
                "cost": 0.45,
                "latency": 0.35,
                "capabilities": ("chat", "tools", "json", "coding"),
                "context_window": 128000,
            },
            {
                "id": "mistral-small-latest",
                "quality": 0.72,
                "cost": 0.12,
                "latency": 0.20,
                "capabilities": ("chat", "tools", "json"),
                "context_window": 32000,
            },
        ),
    },
    "ollama": {
        "base_url": "http://127.0.0.1:11434/v1",
        "api_key_envs": ("OLLAMA_API_KEY",),
        "optional_key": True,
        "models": (
            {
                "id": "llama3.2",
                "quality": 0.58,
                "cost": 0.0,
                "latency": 0.50,
                "capabilities": ("chat", "json"),
                "context_window": 128000,
            },
            {
                "id": "qwen2.5",
                "quality": 0.62,
                "cost": 0.0,
                "latency": 0.48,
                "capabilities": ("chat", "json"),
                "context_window": 128000,
            },
        ),
    },
}


@dataclass(frozen=True)
class CatalogEntry:
    provider: str
    model: str
    base_url: str
    api_key_env: str
    api_key_envs: tuple[str, ...]
    quality: float
    cost: float
    latency: float
    optional_key: bool = False
    capabilities: tuple[str, ...] = ()
    context_window: int = 8192
    name: str = ""
    enabled: bool = True
    fallback_id: str | None = None
    scope: str = "default"

    def key_lookup(self) -> tuple[str | None, str]:
        return lookup_env_key(*self.api_key_envs)

    @property
    def has_key(self) -> bool:
        if self.optional_key or self.provider == "ollama":
            return True
        value, _name = self.key_lookup()
        return bool(value)

    @property
    def ref(self) -> str:
        return f"{self.provider}:{self.model}"

    def public_dict(self) -> dict[str, Any]:
        return {
            "id": self.ref,
            "name": self.name or self.model,
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "quality": self.quality,
            "cost": self.cost,
            "latency": self.latency,
            "has_key": self.has_key,
            "api_key_env": self.api_key_env,
            "capabilities": list(self.capabilities),
            "context_window": self.context_window,
            "enabled": self.enabled,
            "scope": self.scope,
        }

    def to_profile(self) -> ModelProfile:
        return ModelProfile(
            id=self.ref,
            name=self.name or self.model,
            provider=self.provider,
            model=self.model,
            base_url=self.base_url,
            api_key_env=self.api_key_env,
            api_key_envs=self.api_key_envs,
            quality=self.quality,
            cost=self.cost,
            latency=self.latency,
            capabilities=self.capabilities,
            context_window=self.context_window,
            enabled=self.enabled,
            fallback_id=self.fallback_id,
            scope=self.scope,
            optional_key=self.optional_key or self.provider == "ollama",
        )


@dataclass(frozen=True)
class GatewayEndpoint:
    """Point de terminaison resolu. api_key n'est jamais serialise."""

    base_url: str
    model: str
    api_key: str | None
    api_key_env: str
    provider: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "base_url": self.base_url,
            "model": self.model,
            "api_key_env": self.api_key_env,
            "has_key": bool(self.api_key),
        }


def _env(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None or value == "":
        return None
    return value


def _split_ref(
    value: str | None, *, default_as_provider: bool = False
) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    stripped = value.strip()
    if not stripped:
        return None, None
    if ":" in stripped and not stripped.startswith("http"):
        left, right = stripped.split(":", 1)
        if left and "/" not in left:
            return left.strip().lower(), right.strip() or None
    if default_as_provider and "/" not in stripped:
        return stripped.lower(), None
    return None, stripped


def _as_models(value: object) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, str):
        return [{"id": item.strip()} for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple)):
        rows: list[dict[str, Any]] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                rows.append({"id": item.strip()})
            elif isinstance(item, Mapping) and item.get("id"):
                caps = item.get("capabilities", ())
                if isinstance(caps, str):
                    caps = tuple(part.strip() for part in caps.split(",") if part.strip())
                elif isinstance(caps, (list, tuple)):
                    caps = tuple(str(part).strip() for part in caps if str(part).strip())
                else:
                    caps = ()
                rows.append(
                    {
                        "id": str(item["id"]),
                        "name": str(item.get("name") or item["id"]),
                        "quality": float(item.get("quality", 0.5)),
                        "cost": float(item.get("cost", 0.5)),
                        "latency": float(item.get("latency", 0.5)),
                        "capabilities": caps,
                        "context_window": int(item.get("context_window", 8192)),
                        "enabled": item.get("enabled", True),
                        "fallback_id": item.get("fallback_id") or item.get("fallback"),
                        "scope": str(item.get("scope") or "default"),
                    }
                )
        return rows
    return []


def _load_models_file() -> dict[str, dict[str, Any]]:
    path = _env("JEV_MODELS_FILE")
    if not path or not os.path.isfile(path):
        return {}
    raw = _read(path)
    providers = raw.get("providers") if isinstance(raw, dict) else None
    if not isinstance(providers, dict):
        return {}
    cleaned: dict[str, dict[str, Any]] = {}
    for name, spec in providers.items():
        if not isinstance(spec, dict):
            continue
        spec = dict(spec)
        spec.pop("api_key", None)
        spec.pop("jev_api_key", None)
        spec.pop("gateway_api_key", None)
        spec.pop("openai_api_key", None)
        spec.pop("openrouter_api_key", None)
        cleaned[str(name).strip().lower()] = spec
    return cleaned


def _read(path: str) -> Any:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _provider_env_overrides() -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for key, value in os.environ.items():
        match = _CUSTOM_BASE_RE.match(key)
        if not match:
            continue
        name = match.group(1)
        if name in _RESERVED_LLM_NAMES:
            continue
        provider = name.lower()
        models_raw = _env(f"JEV_LLM_{name}_MODELS")
        found[provider] = {
            "base_url": value,
            "api_key_envs": (f"JEV_LLM_{name}_API_KEY",),
            "models": _as_models(models_raw) if models_raw else [],
        }
    return found


def _classic_gateway_spec() -> dict[str, Any] | None:
    base = _env("GATEWAY_BASE_URL")
    if not base:
        return None
    models = _as_models(_env("GATEWAY_MODELS"))
    if _env("GATEWAY_MODEL"):
        model_id = _env("GATEWAY_MODEL")
        if model_id and not any(row.get("id") == model_id for row in models):
            models = [{"id": model_id, "quality": 0.5, "cost": 0.5, "latency": 0.5}, *models]
    if not models:
        models = [{"id": "default", "quality": 0.5, "cost": 0.5, "latency": 0.5}]
    return {
        "base_url": base,
        "api_key_envs": ("GATEWAY_API_KEY",),
        "models": models,
    }


def load_catalog() -> list[CatalogEntry]:
    """Fusionne presets, fichier JSON et overlays d'environnement."""
    merged: dict[str, dict[str, Any]] = {name: dict(spec) for name, spec in PRESETS.items()}
    for name, spec in _load_models_file().items():
        current = merged.get(name, {})
        combined = dict(current)
        combined.update({k: v for k, v in spec.items() if v not in (None, "")})
        if spec.get("models"):
            combined["models"] = spec["models"]
        if spec.get("api_key_env") and not spec.get("api_key_envs"):
            combined["api_key_envs"] = (str(spec["api_key_env"]),)
        merged[name] = combined
    for name, spec in _provider_env_overrides().items():
        current = merged.get(name, {})
        combined = dict(current)
        combined["base_url"] = spec["base_url"] or current.get("base_url")
        extra_envs = tuple(spec.get("api_key_envs") or ())
        existing = tuple(current.get("api_key_envs") or ())
        combined["api_key_envs"] = extra_envs + existing
        if spec.get("models"):
            combined["models"] = spec["models"]
        merged[name] = combined
    classic = _classic_gateway_spec()
    if classic:
        merged.setdefault("gateway", classic)

    ollama_base = _env("OLLAMA_BASE_URL")
    if ollama_base and "ollama" in merged:
        merged["ollama"] = dict(merged["ollama"])
        merged["ollama"]["base_url"] = ollama_base

    entries: list[CatalogEntry] = []
    for provider, spec in merged.items():
        base_url = str(spec.get("base_url") or "")
        if not base_url:
            continue
        envs = spec.get("api_key_envs") or ()
        if isinstance(envs, str):
            envs = (envs,)
        env_names = tuple(str(item) for item in envs if item)
        if spec.get("api_key_env") and str(spec["api_key_env"]) not in env_names:
            env_names = (str(spec["api_key_env"]),) + env_names
        custom_key = f"JEV_LLM_{provider.upper()}_API_KEY"
        if custom_key not in env_names:
            env_names = env_names + (custom_key,)
        if not env_names:
            env_names = (custom_key,)
        optional = bool(spec.get("optional_key")) or provider == "ollama"
        for row in _as_models(spec.get("models")):
            model_id = str(row.get("id") or "").strip()
            if not model_id:
                continue
            caps = row.get("capabilities") or ()
            if isinstance(caps, str):
                caps = tuple(part.strip() for part in caps.split(",") if part.strip())
            fallback = row.get("fallback_id")
            entries.append(
                CatalogEntry(
                    provider=provider,
                    model=model_id,
                    base_url=base_url,
                    api_key_env=env_names[0],
                    api_key_envs=env_names,
                    quality=float(row.get("quality", 0.5)),
                    cost=float(row.get("cost", 0.5)),
                    latency=float(row.get("latency", 0.5)),
                    optional_key=optional,
                    capabilities=tuple(caps) if caps else ("chat",),
                    context_window=int(row.get("context_window", 8192)),
                    name=str(row.get("name") or model_id),
                    enabled=bool(row.get("enabled", True)),
                    fallback_id=None if not fallback else str(fallback),
                    scope=str(row.get("scope") or "default"),
                )
            )
    return entries


def public_catalog() -> list[dict[str, Any]]:
    """Liste publique : jamais de cle brute."""
    return [entry.public_dict() for entry in load_catalog()]


def catalog_profiles() -> list[ModelProfile]:
    """Profils routables issus du catalogue fusionne."""
    return [entry.to_profile() for entry in load_catalog()]


def _strategy_key(entry: CatalogEntry, strategy: str) -> tuple[float, ...]:
    if strategy == "best":
        return (-entry.quality, entry.cost, entry.latency, entry.provider, entry.model)
    if strategy == "cheapest":
        return (entry.cost, -entry.quality, entry.latency, entry.provider, entry.model)
    if strategy == "fastest":
        return (entry.latency, -entry.quality, entry.cost, entry.provider, entry.model)
    return (
        -(entry.quality / (1.0 + entry.cost + entry.latency)),
        entry.cost,
        entry.latency,
        entry.provider,
        entry.model,
    )


def _pick(
    entries: list[CatalogEntry],
    *,
    provider: str | None,
    model: str | None,
    strategy: str,
) -> CatalogEntry:
    pool = entries
    if provider:
        pool = [item for item in pool if item.provider == provider]
    if model:
        exact = [item for item in pool if item.model == model]
        if exact:
            pool = exact
        elif strategy == "named":
            raise ConfigurationError(f"modele inconnu dans le catalogue : {model}")
    if not pool:
        raise ConfigurationError("aucun modele dans le catalogue pour cette selection")

    if strategy == "named":
        usable = [item for item in pool if item.has_key or item.optional_key]
        chosen_pool = usable or pool
        return chosen_pool[0]

    usable = [item for item in pool if item.has_key or item.optional_key]
    ranked = usable or pool
    ranked = sorted(ranked, key=lambda item: _strategy_key(item, strategy))
    return ranked[0]


def resolve_gateway(
    provider: str | None = None,
    model: str | None = None,
    prefer: str | None = None,
) -> GatewayEndpoint:
    """Resout un endpoint gateway. Ne serialise jamais api_key."""
    explicit_provider, explicit_model = _split_ref(provider, default_as_provider=True)
    model_provider, model_name = _split_ref(model)
    chosen_provider = explicit_provider or model_provider
    chosen_model = explicit_model or model_name

    strategy = (prefer or _env("JEV_LLM_STRATEGY") or "named").strip().lower()
    if strategy not in {"named", "best", "cheapest", "fastest", "balanced"}:
        raise ConfigurationError(f"strategie LLM inconnue : {strategy}")

    gw_url = _env("GATEWAY_BASE_URL")
    gw_key = _env("GATEWAY_API_KEY")
    gw_model = _env("GATEWAY_MODEL")
    complete = bool(gw_url and gw_model and gw_key)
    explicit_catalog = bool(chosen_provider or chosen_model or (strategy not in {"named", ""}))
    if complete and not explicit_catalog:
        return GatewayEndpoint(
            base_url=gw_url or "",
            model=gw_model or "",
            api_key=gw_key,
            api_key_env="GATEWAY_API_KEY",
            provider="gateway",
        )

    if strategy == "named" and not chosen_provider and not chosen_model:
        default_provider, default_model = _split_ref(
            _env("JEV_LLM_DEFAULT") or "openrouter:anthropic/claude-sonnet-4"
        )
        chosen_provider = chosen_provider or default_provider
        chosen_model = chosen_model or default_model

    entry = _pick(
        load_catalog(),
        provider=chosen_provider,
        model=chosen_model,
        strategy=strategy,
    )
    api_key, api_key_env = entry.key_lookup()
    return GatewayEndpoint(
        base_url=entry.base_url,
        model=entry.model,
        api_key=api_key,
        api_key_env=api_key_env,
        provider=entry.provider,
    )
