"""Facade publique ModelRouter."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from typing import Any

from .catalog import catalog_profiles, resolve_gateway
from .config import Settings
from .errors import ConfigurationError
from .models import ModelProfile, RejectedModel, RouteRequest, RouteResult, reject_secret_fields
from .providers.custom import CustomProvider
from .providers.gateway import GatewayClient
from .providers.jev import JevClient
from .providers.local import LocalProvider
from .providers.mock import MockProvider
from .registry import DEFAULT_MODELS
from .router import HeuristicRouter
from .security.redaction import redact_model, redact_text


def merge_models(
    catalog: Sequence[ModelProfile],
    extra: Sequence[ModelProfile],
) -> list[ModelProfile]:
    """Les modeles fournis remplacent ou etendent le catalogue par id."""
    merged = {item.id: item for item in catalog}
    for item in extra:
        merged[item.id] = item
    return list(merged.values())


class ModelRouter:
    """Point d'entree unique : local, mock, custom ou jev+gateway.

    Ne genere jamais le texte utilisateur. En local/mock, aucune cle
    n'est exigee. En jev, missing_key s'applique.
    """

    def __init__(
        self,
        provider: str = "local",
        *,
        api_key: str | None = None,
        jev_base_url: str | None = None,
        gateway_api_key: str | None = None,
        gateway_base_url: str | None = None,
        gateway_model: str | None = None,
        settings: Settings | None = None,
        llm_prefer: str | None = None,
    ) -> None:
        env = settings or Settings.from_env()
        name = provider.strip().lower()
        use_env_defaults = settings is not None
        self.provider_name = name
        self.settings = Settings(
            provider=name,
            jev_api_key=_coalesce(api_key, env.jev_api_key),
            jev_base_url=_coalesce(jev_base_url, env.jev_base_url),
            jev_model=env.jev_model,
            gateway_base_url=_coalesce(gateway_base_url, env.gateway_base_url),
            gateway_api_key=_coalesce(gateway_api_key, env.gateway_api_key),
            gateway_model=_coalesce(gateway_model, env.gateway_model),
            models_file=env.models_file,
            llm_default=env.llm_default,
            llm_strategy=_coalesce(llm_prefer, env.llm_strategy) or "balanced",
            max_alternatives=env.max_alternatives,
            max_candidates=env.max_candidates,
            redact_secrets=env.redact_secrets if use_env_defaults else name in {"jev", "custom"},
            host=env.host,
            port=env.port,
            auth_token=env.auth_token,
            w_jev=env.w_jev,
            w_gateway=env.w_gateway,
            w_relevance=env.w_relevance,
            request_timeout=env.request_timeout,
            require_keys=name == "jev",
        )
        self._apply_catalog(llm_prefer=llm_prefer)
        self._validate()

    def _apply_catalog(self, llm_prefer: str | None = None) -> None:
        if self.provider_name != "jev":
            return
        settings = self.settings
        incomplete = not (
            settings.gateway_base_url and settings.gateway_model and settings.gateway_api_key
        )
        explicit = bool(llm_prefer and llm_prefer != "named")
        if not incomplete and not explicit:
            return
        prefer = llm_prefer if llm_prefer and llm_prefer != "named" else None
        endpoint = resolve_gateway(prefer=prefer)
        self.settings = replace(
            settings,
            gateway_base_url=settings.gateway_base_url or endpoint.base_url,
            gateway_api_key=settings.gateway_api_key or endpoint.api_key,
            gateway_model=settings.gateway_model or endpoint.model,
        )

    def _validate(self) -> None:
        if self.provider_name not in {"local", "mock", "custom", "jev"}:
            raise ConfigurationError(f"provider inconnu : {self.provider_name}")
        if self.provider_name == "jev":
            missing = [
                name
                for name, value in (
                    ("JEV_API_KEY", self.settings.jev_api_key),
                    ("JEV_BASE_URL", self.settings.jev_base_url),
                    ("GATEWAY_API_KEY", self.settings.gateway_api_key),
                    ("GATEWAY_BASE_URL", self.settings.gateway_base_url),
                    ("GATEWAY_MODEL", self.settings.gateway_model),
                )
                if not value
            ]
            ollama = (self.settings.gateway_base_url or "").rstrip("/").endswith("11434/v1")
            if ollama:
                missing = [name for name in missing if name != "GATEWAY_API_KEY"]
            if missing:
                raise ConfigurationError("provider jev exige " + ", ".join(missing))
        if self.provider_name == "custom" and not self.settings.jev_base_url:
            raise ConfigurationError("JEV_BASE_URL est obligatoire pour le provider custom")

    def route(
        self,
        task: str,
        models: Sequence[ModelProfile | Mapping[str, Any]] | None = None,
        *,
        required_capabilities: Sequence[str] = (),
        prefer: str | None = None,
        min_quality: float = 0.0,
        max_cost: float = 1.0,
        max_latency: float = 1.0,
        min_context: int = 0,
        allow_fallback: bool = True,
        failed_model_id: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        scope: str = "default",
        max_alternatives: int | None = None,
    ) -> RouteResult:
        if models is not None:
            reject_secret_fields(models, where="modele")
        incoming = [ModelProfile.from_mapping(item) for item in (models or ())]
        catalog = list(DEFAULT_MODELS) + catalog_profiles()
        profiles = merge_models(catalog, incoming) if incoming else catalog
        if incoming and not catalog:
            profiles = incoming
        clean_task = redact_text(task) if self.settings.redact_secrets else task
        if self.settings.redact_secrets:
            profiles = [redact_model(item) for item in profiles]
        request = RouteRequest(
            task=clean_task,
            required_capabilities=tuple(required_capabilities),
            prefer=str(prefer or self.settings.llm_strategy or "balanced"),
            min_quality=min_quality,
            max_cost=max_cost,
            max_latency=max_latency,
            min_context=min_context,
            allow_fallback=allow_fallback,
            failed_model_id=failed_model_id,
            provider=provider,
            model=model,
            scope=scope,
            max_alternatives=(
                self.settings.max_alternatives if max_alternatives is None else max_alternatives
            ),
        )
        if self.provider_name == "jev":
            return self._route_jev(profiles, request)
        if self.provider_name == "custom":
            return CustomProvider(
                base_url=self.settings.jev_base_url or "",
                api_key=self.settings.jev_api_key,
                timeout=self.settings.request_timeout,
                router=self._local_router(),
            ).route(profiles, request)
        if self.provider_name == "mock":
            return MockProvider().route(profiles, request)
        return LocalProvider(self._local_router()).route(profiles, request)

    def _local_router(self) -> HeuristicRouter:
        return HeuristicRouter(
            w_relevance=self.settings.w_relevance,
            require_keys=self.settings.require_keys,
        )

    def _hybrid_router(self) -> HeuristicRouter:
        settings = self.settings
        return HeuristicRouter(
            w_relevance=settings.w_relevance,
            w_jev=settings.w_jev,
            w_gateway=settings.w_gateway,
            require_keys=True,
        )

    def _route_jev(self, models: list[ModelProfile], request: RouteRequest) -> RouteResult:
        prefilter = HeuristicRouter(require_keys=True)
        candidates, rejected, _by_id = prefilter.collect(models, request)
        limited = candidates[: self.settings.max_candidates]
        extra = [
            RejectedModel(item.id, "max_candidates")
            for _score, _rel, item in candidates[self.settings.max_candidates :]
        ]
        top = [item for _score, _rel, item in limited]
        if not top:
            return RouteResult(
                decision="abstain",
                selected=None,
                rejected=tuple(rejected) + tuple(extra),
                reasons=("no_candidate",),
                abstain_reason="no_candidate",
            )

        jev = JevClient(
            api_key=self.settings.jev_api_key or "",
            base_url=self.settings.jev_base_url or "",
            model=self.settings.jev_model,
            timeout=self.settings.request_timeout,
        )
        ollama = (self.settings.gateway_base_url or "").rstrip("/").endswith("11434/v1")
        gateway = GatewayClient(
            api_key=self.settings.gateway_api_key or "",
            base_url=self.settings.gateway_base_url or "",
            model=self.settings.gateway_model or "",
            timeout=self.settings.request_timeout,
            optional_key=ollama,
        )
        with ThreadPoolExecutor(max_workers=2) as pool:
            jev_future = pool.submit(jev.score, request.task, top)
            gw_future = pool.submit(gateway.score, request.task, top)
            jev_scores = jev_future.result()
            gateway_scores = gw_future.result()

        result = self._hybrid_router().route(
            top, request, jev_scores=jev_scores, gateway_scores=gateway_scores
        )
        return RouteResult(
            decision=result.decision,
            selected=result.selected,
            fallback=result.fallback,
            alternatives=result.alternatives,
            rejected=tuple(rejected) + tuple(extra) + result.rejected,
            reasons=result.reasons,
            abstain_reason=result.abstain_reason,
        )


def _coalesce(explicit: str | None, fallback: str | None) -> str | None:
    return explicit if explicit is not None else fallback
