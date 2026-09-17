"""Modeles de donnees du routeur LLM."""
from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from .errors import ConfigurationError

Decision = Literal["select", "fallback", "abstain"]
Prefer = Literal["balanced", "best", "cheapest", "fastest", "named"]

FORBIDDEN_KEY_FIELDS = frozenset(
    {
        "api_key",
        "jev_api_key",
        "gateway_api_key",
        "openai_api_key",
        "openrouter_api_key",
    }
)
PREFER_VALUES = frozenset({"balanced", "best", "cheapest", "fastest", "named"})


def reject_secret_fields(data: Any, *, where: str = "corps") -> None:
    """Refuse toute cle brute, y compris imbriquee."""
    if isinstance(data, Mapping):
        for key, value in data.items():
            if str(key).lower() in FORBIDDEN_KEY_FIELDS:
                raise ConfigurationError(f"les cles ne doivent pas figurer dans le {where}")
            reject_secret_fields(value, where=where)
    elif isinstance(data, (list, tuple)):
        for item in data:
            reject_secret_fields(item, where=where)


def _as_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(",")]
        return tuple(part for part in parts if part)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    raise ValueError("attendu une liste ou une chaine")


def _as_bool(value: object, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def normalize_token(value: str) -> str:
    """Normalise une capacite pour les comparaisons."""
    return value.strip().lower()


def lookup_env_key(*names: str) -> tuple[str | None, str]:
    """Lit une cle dans l'environnement. Ne la serialise jamais."""
    last = names[-1] if names else ""
    for name in names:
        if not name:
            continue
        value = os.environ.get(name)
        if value:
            return value, name
    return None, last


@dataclass(frozen=True)
class ModelProfile:
    """Un modele declare dans le catalogue.

    api_key_env nomme la variable, jamais la valeur. Les capacites
    viennent uniquement du catalogue, pas de la tache.
    """

    id: str
    name: str
    provider: str
    model: str
    base_url: str = ""
    api_key_env: str = ""
    api_key_envs: tuple[str, ...] = ()
    quality: float = 0.7
    cost: float = 0.5
    latency: float = 0.5
    capabilities: tuple[str, ...] = ()
    context_window: int = 8192
    enabled: bool = True
    fallback_id: str | None = None
    scope: str = "default"
    optional_key: bool = False

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("id est obligatoire")
        if not self.name:
            raise ValueError("name est obligatoire")
        if not self.provider:
            raise ValueError("provider est obligatoire")
        if not self.model:
            raise ValueError("model est obligatoire")
        for field_name, value in (
            ("quality", self.quality),
            ("cost", self.cost),
            ("latency", self.latency),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{field_name} doit etre compris entre 0.0 et 1.0")
        if self.context_window < 1:
            raise ValueError("context_window doit etre >= 1")
        envs = self.api_key_envs or ((self.api_key_env,) if self.api_key_env else ())
        object.__setattr__(self, "api_key_envs", tuple(item for item in envs if item))
        if self.api_key_envs and not self.api_key_env:
            object.__setattr__(self, "api_key_env", self.api_key_envs[0])

    @property
    def capability_set(self) -> frozenset[str]:
        return frozenset(normalize_token(item) for item in self.capabilities)

    @property
    def ref(self) -> str:
        return f"{self.provider}:{self.model}"

    @property
    def has_key(self) -> bool:
        if self.optional_key or self.provider == "ollama":
            return True
        value, _name = lookup_env_key(*self.api_key_envs)
        return bool(value)

    def with_name(self, name: str) -> ModelProfile:
        return ModelProfile(
            id=self.id,
            name=name,
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
            optional_key=self.optional_key,
        )

    @classmethod
    def from_mapping(cls, data: ModelProfile | Mapping[str, Any]) -> ModelProfile:
        if isinstance(data, cls):
            return data
        reject_secret_fields(data, where="modele")
        fallback = data.get("fallback_id") or data.get("fallback")
        provider = str(data.get("provider") or "demo")
        model = str(data.get("model") or data.get("id") or "")
        ident = str(data.get("id") or (f"{provider}:{model}" if provider and model else ""))
        env_names = _as_tuple(data.get("api_key_envs") or data.get("api_key_env"))
        optional = _as_bool(data.get("optional_key"), provider == "ollama")
        return cls(
            id=ident,
            name=str(data.get("name") or ident or model),
            provider=provider,
            model=model,
            base_url=str(data.get("base_url") or ""),
            api_key_env=str(data.get("api_key_env") or (env_names[0] if env_names else "")),
            api_key_envs=env_names,
            quality=float(data.get("quality", 0.7)),
            cost=float(data.get("cost", 0.5)),
            latency=float(data.get("latency", 0.5)),
            capabilities=_as_tuple(data.get("capabilities")),
            context_window=int(data.get("context_window", 8192)),
            enabled=_as_bool(data.get("enabled"), True),
            fallback_id=None if not fallback else str(fallback),
            scope=str(data.get("scope") or data.get("namespace") or "default"),
            optional_key=optional,
        )


@dataclass(frozen=True)
class RouteRequest:
    """Une demande de routage.

    required_capabilities est declare par l'appelant, jamais extrait
    de la tache.
    """

    task: str
    required_capabilities: tuple[str, ...] = ()
    prefer: Prefer = "balanced"
    min_quality: float = 0.0
    max_cost: float = 1.0
    max_latency: float = 1.0
    min_context: int = 0
    allow_fallback: bool = True
    failed_model_id: str | None = None
    provider: str | None = None
    model: str | None = None
    scope: str = "default"
    max_alternatives: int = 3

    def __post_init__(self) -> None:
        if not self.task.strip():
            raise ValueError("task est obligatoire")
        prefer = self.prefer.strip().lower()
        if prefer not in PREFER_VALUES:
            raise ValueError(f"prefer inconnu : {self.prefer}")
        object.__setattr__(self, "prefer", prefer)
        for field_name, value in (
            ("min_quality", self.min_quality),
            ("max_cost", self.max_cost),
            ("max_latency", self.max_latency),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{field_name} doit etre compris entre 0.0 et 1.0")
        if self.min_context < 0:
            raise ValueError("min_context doit etre >= 0")
        if self.max_alternatives < 0:
            raise ValueError("max_alternatives doit etre >= 0")
        provider = None if not self.provider else self.provider.strip().lower()
        object.__setattr__(self, "provider", provider or None)
        model = None if not self.model else str(self.model).strip()
        object.__setattr__(self, "model", model or None)

    @property
    def required_capability_set(self) -> frozenset[str]:
        return frozenset(normalize_token(item) for item in self.required_capabilities)

    @classmethod
    def from_mapping(
        cls, data: Mapping[str, Any], defaults: RouteRequest | None = None
    ) -> RouteRequest:
        reject_secret_fields(data)
        base = defaults
        failed = data.get("failed_model_id")
        prefer = data.get("prefer", base.prefer if base else "balanced")
        provider = data.get("provider", base.provider if base else None)
        model = data.get("model", base.model if base else None)
        return cls(
            task=str(data.get("task") or (base.task if base else "")),
            required_capabilities=_as_tuple(
                data.get("required_capabilities", base.required_capabilities if base else ())
            ),
            prefer=str(prefer or "balanced"),
            min_quality=float(data.get("min_quality", base.min_quality if base else 0.0)),
            max_cost=float(data.get("max_cost", base.max_cost if base else 1.0)),
            max_latency=float(data.get("max_latency", base.max_latency if base else 1.0)),
            min_context=int(data.get("min_context", base.min_context if base else 0)),
            allow_fallback=_as_bool(
                data.get("allow_fallback"), base.allow_fallback if base else True
            ),
            failed_model_id=None if failed in (None, "") else str(failed),
            provider=None if provider in (None, "") else str(provider),
            model=None if model in (None, "") else str(model),
            scope=str(data.get("scope") or (base.scope if base else "default")),
            max_alternatives=int(
                data.get("max_alternatives", base.max_alternatives if base else 3)
            ),
        )


@dataclass(frozen=True)
class SelectedModel:
    """Un modele retenu, sans jamais exposer api_key."""

    id: str
    name: str
    provider: str
    model: str
    base_url: str
    api_key_env: str
    has_key: bool
    quality: float
    cost: float
    latency: float
    capabilities: tuple[str, ...]
    score: float
    reasons: tuple[str, ...]
    context_window: int = 8192

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "api_key_env": self.api_key_env,
            "has_key": self.has_key,
            "quality": self.quality,
            "cost": self.cost,
            "latency": self.latency,
            "capabilities": list(self.capabilities),
            "context_window": self.context_window,
            "score": self.score,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class RejectedModel:
    """Un modele ecarte, avec la cause du rejet."""

    id: str
    reason: str


@dataclass(frozen=True)
class RouteResult:
    """Le resultat d'un routage."""

    decision: Decision
    selected: SelectedModel | None
    fallback: SelectedModel | None = None
    alternatives: tuple[SelectedModel, ...] = ()
    rejected: tuple[RejectedModel, ...] = ()
    reasons: tuple[str, ...] = ()
    abstain_reason: str | None = None

    def to_dict(self, *, include_rejected: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "decision": self.decision,
            "selected": None if self.selected is None else self.selected.to_dict(),
            "fallback": None if self.fallback is None else self.fallback.to_dict(),
            "alternatives": [item.to_dict() for item in self.alternatives],
            "reasons": list(self.reasons),
            "abstain_reason": self.abstain_reason,
        }
        if include_rejected:
            payload["rejected"] = [
                {"id": item.id, "reason": item.reason} for item in self.rejected
            ]
        return payload
