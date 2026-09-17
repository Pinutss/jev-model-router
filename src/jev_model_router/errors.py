"""Erreurs publiques du routeur de modeles."""


class RouterError(Exception):
    """Erreur de base du routeur."""


class ConfigurationError(RouterError):
    """Configuration manquante ou invalide."""


class ProviderError(RouterError):
    """Echec d'un provider distant."""
