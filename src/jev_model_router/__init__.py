"""jev-model-router : routage explicable de modeles LLM."""
from .catalog import public_catalog, resolve_gateway
from .errors import ConfigurationError, ProviderError, RouterError
from .facade import ModelRouter
from .models import (
    ModelProfile,
    RejectedModel,
    RouteRequest,
    RouteResult,
    SelectedModel,
)
from .registry import DEFAULT_MODELS
from .router import HeuristicRouter, tokenize
from .security.redaction import redact_text
from .version import __version__

__all__ = [
    "ConfigurationError",
    "DEFAULT_MODELS",
    "HeuristicRouter",
    "ModelProfile",
    "ModelRouter",
    "ProviderError",
    "RejectedModel",
    "RouteRequest",
    "RouteResult",
    "RouterError",
    "SelectedModel",
    "public_catalog",
    "redact_text",
    "resolve_gateway",
    "tokenize",
    "__version__",
]
