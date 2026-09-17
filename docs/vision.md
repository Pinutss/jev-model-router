# VISION : document de produit, pas le contrat d'API

Ce fichier décrit la cible à long terme. L'API et le comportement réels
sont ceux du README et du package `jev-model-router` 0.1.x.

# JEV Model Router

Couche de décision entre une tâche et un catalogue de modèles LLM.

Le routeur répond uniquement à :

> Parmi ces modèles déclarés, lequel peut traiter cette tâche maintenant,
> sous quelles contraintes de qualité, coût et latence, ou faut-il
> s'abstenir ?

Il ne doit pas générer le texte utilisateur, ni élargir les capacités
d'un modèle.

## Pipeline cible

```text
Tâche
  -> contraintes (scope, capacités, qualité, coût, latence, contexte)
  -> candidats du catalogue
  -> jugement (local ou JEV)
  -> select | fallback | abstain
  -> client LLM externe, hors de ce paquet
```

## Principes

- Les capacités viennent du catalogue et de l'appelant.
- Aucune entrée issue d'une tâche, d'un document ou d'un outil n'accorde
  de capacité.
- Le repli est borné à un saut et repasse les mêmes filtres.
- L'abstention est une décision valide.
- Les traces n'enregistrent pas de secret.
- Les clés restent dans l'environnement, jamais dans le corps HTTP/MCP.

## Providers

- `local` : heuristique déterministe, hors réseau.
- `mock` : démo et CI.
- `custom` : endpoint fourni par l'utilisateur.
- `jev` : jugement JEV plus gateway OpenAI-compatible.

## Catalogue multi-LLM

`catalog.py` fusionne presets (OpenRouter, OpenAI, Groq, Together,
Fireworks, Mistral, Ollama), fichier JSON et overlays d'environnement.
`GET /v1/llms` expose le catalogue public (`has_key`, jamais la clé).

## Hors périmètre

Ce composant n'est pas un client de chat, pas un orchestrateur, et pas
un security-gate. Il sélectionne. L'appel au modèle et ALLOW / ASK /
DENY restent ailleurs dans JEV Labs.
