"""Routeur heuristique deterministe, sans generation de texte utilisateur."""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from .models import (
    ModelProfile,
    RejectedModel,
    RouteRequest,
    RouteResult,
    SelectedModel,
)

_WORD_RE = re.compile(r"[a-z0-9àâäéèêëíìîïòóôöùúûüçñ]+")
_STOPWORDS = frozenset(
    """au aux avec ce ces dans de des du elle en et eux il je la le les leur lui ma
    mais me meme mes moi mon ne nos notre nous on ou par pas pour qu que qui sa se
    ses son sur ta te tes toi ton tu un une vos votre vous c d j l à m n s t y été
    the a an and or of to in for with without is are was were be been this that
    """.split()
)

Candidate = tuple[float, float, ModelProfile]


def tokenize(text: str) -> frozenset[str]:
    """Jetons minuscules, sans mots vides, pour le scoring lexical."""
    return frozenset(
        word
        for word in _WORD_RE.findall(text.lower())
        if (len(word) > 1 or word.isdigit()) and word not in _STOPWORDS
    )


def model_tokens(model: ModelProfile) -> frozenset[str]:
    tokens = set(tokenize(f"{model.name} {model.model} {model.provider} {model.id}"))
    for value in model.capabilities:
        tokens.update(tokenize(value))
        tokens.add(value.strip().lower())
    return frozenset(tokens)


def strategy_score(model: ModelProfile, prefer: str) -> float:
    """Score deterministe selon la strategie demandee."""
    if prefer == "cheapest":
        return (1.0 - model.cost) * 0.7 + model.quality * 0.2 + (1.0 - model.latency) * 0.1
    if prefer == "fastest":
        return (1.0 - model.latency) * 0.7 + model.quality * 0.2 + (1.0 - model.cost) * 0.1
    if prefer == "best":
        return model.quality * 0.7 + (1.0 - model.latency) * 0.15 + (1.0 - model.cost) * 0.15
    return model.quality * 0.4 + (1.0 - model.cost) * 0.3 + (1.0 - model.latency) * 0.3


def matches_pin(model: ModelProfile, pin: str) -> bool:
    target = pin.strip()
    if not target:
        return False
    if model.id == target or model.model == target or model.ref == target:
        return True
    if ":" in target and not target.startswith("http"):
        provider, _, name = target.partition(":")
        if provider and "/" not in provider:
            return model.provider == provider.strip().lower() and model.model == name.strip()
    return False


def _hard_reject(
    model: ModelProfile,
    request: RouteRequest,
    *,
    require_keys: bool,
) -> str | None:
    if model.scope != request.scope:
        return "out_of_scope"
    if not model.enabled:
        return "disabled"
    if request.failed_model_id and model.id == request.failed_model_id:
        return "already_failed"
    if request.provider and model.provider != request.provider:
        return "provider_mismatch"
    if request.model and not matches_pin(model, request.model):
        return "pin_mismatch"
    required_caps = request.required_capability_set
    if required_caps and not required_caps <= model.capability_set:
        return "missing_capabilities"
    if model.quality < request.min_quality:
        return "below_min_quality"
    if model.cost > request.max_cost:
        return "above_max_cost"
    if model.latency > request.max_latency:
        return "above_max_latency"
    if model.context_window < request.min_context:
        return "below_min_context"
    if require_keys and not model.has_key:
        return "missing_key"
    return None


@dataclass
class HeuristicRouter:
    """Selection deterministe avec abstention et repli d'un seul saut.

    Les capacites exigeees viennent de l'appelant. La tache ne peut
    pas en ajouter. Un juge distant ne peut pas reintroduire un
    modele rejete par les filtres durs.
    """

    w_relevance: float = 0.15
    w_jev: float = 0.0
    w_gateway: float = 0.0
    require_keys: bool = False

    def collect(
        self,
        models: list[ModelProfile],
        request: RouteRequest,
        jev_scores: Mapping[str, float] | None = None,
        gateway_scores: Mapping[str, float] | None = None,
    ) -> tuple[list[Candidate], list[RejectedModel], dict[str, ModelProfile]]:
        jev_scores = jev_scores or {}
        gateway_scores = gateway_scores or {}
        task_tokens = tokenize(request.task)
        rejected: list[RejectedModel] = []
        seen: set[str] = set()
        by_id: dict[str, ModelProfile] = {}
        candidates: list[Candidate] = []

        for model in models:
            if model.id in seen:
                rejected.append(RejectedModel(model.id, "duplicate_input"))
                continue
            seen.add(model.id)
            by_id[model.id] = model
            reason = _hard_reject(model, request, require_keys=self.require_keys)
            if reason is not None:
                rejected.append(RejectedModel(model.id, reason))
                continue

            tokens = model_tokens(model)
            relevance = len(task_tokens & tokens) / len(task_tokens) if task_tokens else 0.0
            base = strategy_score(model, request.prefer)
            jev_score = float(jev_scores.get(model.id, 0.0))
            gateway_score = float(gateway_scores.get(model.id, 0.0))
            score = (
                (1.0 - self.w_relevance) * base
                + self.w_relevance * relevance
                + self.w_jev * jev_score
                + self.w_gateway * gateway_score
            )
            candidates.append((score, relevance, model))

        candidates.sort(key=lambda item: (-round(item[0], 6), item[2].id))
        return candidates, rejected, by_id

    def route(
        self,
        models: list[ModelProfile],
        request: RouteRequest,
        jev_scores: Mapping[str, float] | None = None,
        gateway_scores: Mapping[str, float] | None = None,
    ) -> RouteResult:
        jev_scores = jev_scores or {}
        gateway_scores = gateway_scores or {}
        candidates, rejected, by_id = self.collect(
            models, request, jev_scores=jev_scores, gateway_scores=gateway_scores
        )
        selected_rows = [
            self._to_selected(score, relevance, model, jev_scores, gateway_scores, request.prefer)
            for score, relevance, model in candidates
        ]

        if request.failed_model_id:
            return self._after_failure(request, selected_rows, rejected, by_id)

        if request.prefer == "named":
            return self._named(request, selected_rows, rejected)

        if not selected_rows:
            return RouteResult(
                decision="abstain",
                selected=None,
                rejected=tuple(rejected),
                reasons=("no_candidate",),
                abstain_reason="no_candidate",
            )

        top = selected_rows[0]
        fallback = selected_rows[1] if request.allow_fallback and len(selected_rows) > 1 else None
        alternatives = tuple(selected_rows[1 : request.max_alternatives + 1])
        return RouteResult(
            decision="select",
            selected=top,
            fallback=fallback,
            alternatives=alternatives,
            rejected=tuple(rejected),
            reasons=("best_match",) + top.reasons,
        )

    def _named(
        self,
        request: RouteRequest,
        selected_rows: list[SelectedModel],
        rejected: list[RejectedModel],
    ) -> RouteResult:
        pin = request.model
        if not pin:
            return RouteResult(
                decision="abstain",
                selected=None,
                alternatives=tuple(selected_rows[: request.max_alternatives]),
                rejected=tuple(rejected),
                reasons=("named_without_pin",),
                abstain_reason="named_without_pin",
            )
        chosen = next((row for row in selected_rows if _matches_selected(row, pin)), None)
        if chosen is None:
            return RouteResult(
                decision="abstain",
                selected=None,
                alternatives=tuple(selected_rows[: request.max_alternatives]),
                rejected=tuple(rejected),
                reasons=("named_unavailable",),
                abstain_reason="named_unavailable",
            )
        remaining = [row for row in selected_rows if row.id != chosen.id]
        return RouteResult(
            decision="select",
            selected=chosen,
            fallback=remaining[0] if request.allow_fallback and remaining else None,
            alternatives=tuple(remaining[: request.max_alternatives]),
            rejected=tuple(rejected),
            reasons=("named_pin",) + chosen.reasons,
        )

    def _after_failure(
        self,
        request: RouteRequest,
        selected_rows: list[SelectedModel],
        rejected: list[RejectedModel],
        by_id: dict[str, ModelProfile],
    ) -> RouteResult:
        failed_id = request.failed_model_id or ""
        if failed_id not in by_id:
            rejected.append(RejectedModel(failed_id, "model_absent"))
        if not request.allow_fallback:
            return RouteResult(
                decision="abstain",
                selected=None,
                rejected=tuple(rejected),
                reasons=("fallback_disabled",),
                abstain_reason="fallback_disabled",
            )

        preferred_id = None
        failed = by_id.get(failed_id)
        if failed is not None:
            preferred_id = failed.fallback_id

        chosen = None
        if preferred_id:
            chosen = next((row for row in selected_rows if row.id == preferred_id), None)
            if chosen is None:
                rejected.append(RejectedModel(preferred_id, "fallback_unavailable"))
        if chosen is None and selected_rows:
            chosen = selected_rows[0]
        if chosen is None:
            return RouteResult(
                decision="abstain",
                selected=None,
                rejected=tuple(rejected),
                reasons=("no_fallback",),
                abstain_reason="no_fallback",
            )

        remaining = [row for row in selected_rows if row.id != chosen.id]
        return RouteResult(
            decision="fallback",
            selected=chosen,
            fallback=None,
            alternatives=tuple(remaining[: request.max_alternatives]),
            rejected=tuple(rejected),
            reasons=(f"failed:{failed_id}", "bounded_fallback") + chosen.reasons,
        )

    def _to_selected(
        self,
        score: float,
        relevance: float,
        model: ModelProfile,
        jev_scores: Mapping[str, float],
        gateway_scores: Mapping[str, float],
        prefer: str,
    ) -> SelectedModel:
        reasons = [
            f"prefer={prefer}",
            f"quality={model.quality:.2f}",
            f"cost={model.cost:.2f}",
            f"latency={model.latency:.2f}",
            f"relevance={relevance:.2f}",
        ]
        if model.id in jev_scores:
            reasons.append(f"jev={float(jev_scores[model.id]):.2f}")
        if model.id in gateway_scores:
            reasons.append(f"gateway={float(gateway_scores[model.id]):.2f}")
        return SelectedModel(
            id=model.id,
            name=model.name,
            provider=model.provider,
            model=model.model,
            base_url=model.base_url,
            api_key_env=model.api_key_env,
            has_key=model.has_key,
            quality=model.quality,
            cost=model.cost,
            latency=model.latency,
            capabilities=model.capabilities,
            score=round(score, 6),
            reasons=tuple(reasons),
            context_window=model.context_window,
        )


def _matches_selected(row: SelectedModel, pin: str) -> bool:
    probe = ModelProfile(
        id=row.id,
        name=row.name,
        provider=row.provider,
        model=row.model,
        base_url=row.base_url,
        api_key_env=row.api_key_env,
        quality=row.quality,
        cost=row.cost,
        latency=row.latency,
        capabilities=row.capabilities,
        context_window=row.context_window,
    )
    return matches_pin(probe, pin)
