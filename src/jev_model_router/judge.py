"""Point d'extension interne pour un juge externe.

Ce protocole n'est pas exporte. HeuristicRouter et les providers
JEV / gateway couvrent le classement public. Le juge ne genere
jamais le texte utilisateur.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from .models import ModelProfile, RouteRequest


class Judge(Protocol):
    """Reordonne des candidats deja filtres et valides.

    Contrat attendu : sortie deterministe pour une entree donnee, aucun
    effet de bord, aucune elevation de capacites. Un juge ne peut pas
    reintroduire un modele rejete par les filtres durs.
    """

    def rerank(
        self,
        request: RouteRequest,
        candidates: Sequence[ModelProfile],
    ) -> Sequence[tuple[ModelProfile, float, tuple[str, ...]]]:
        """Retourne les candidats ordonnes, avec score et justification."""
        ...
