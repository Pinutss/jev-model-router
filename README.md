# jev-model-router

Routage LLM sous contraintes de qualité, coût et latence.

Auteur : [Pinuts](https://github.com/Pinutss). Licence MIT.

Fait partie de [JEV Labs](https://github.com/Pinutss/jev-labs).

Stack : Python 3.10+, HTTP, MCP stdio, Docker, HTML de démo.

Après `jev-model serve` : [démo](http://127.0.0.1:8080/)

## Local, sans clé

```bash
git clone https://github.com/Pinutss/jev-model-router
cd jev-model-router
uv sync
uv run jev-model demo
uv run jev-model serve
```

`provider=local` par défaut si tu ne mets pas de clés. Docker :

```bash
docker compose up
```

## Ce que fait le prototype

Le routeur choisit un modèle dans un catalogue (OpenRouter, OpenAI, Groq,
Together, Fireworks, Mistral, Ollama, ou un fichier JSON). Il justifie,
s'abstient s'il n'y a pas de candidat sûr, et n'autorise qu'un seul saut
de repli.

Il n'appelle pas le LLM pour générer le texte utilisateur, sauf le juge
optionnel JEV quand `provider=jev`. En local, le score est déterministe.

Les capacités viennent uniquement du catalogue et des contraintes de
l'appelant. La tâche ne peut pas en ajouter. Les clés restent dans
l'environnement : jamais dans le corps HTTP ou MCP, jamais dans la
réponse.

## Python

```python
from jev_model_router import ModelRouter, DEFAULT_MODELS

result = ModelRouter(provider="local").route(
    task="Summarize this meeting and draft a follow-up email",
    models=DEFAULT_MODELS,
    prefer="balanced",
    scope="demo",
)
print(result.decision, result.selected.id if result.selected else result.abstain_reason)
```

## Catalogue multi-LLM

`load_catalog()` fusionne presets, `JEV_MODELS_FILE` et les overlays
`JEV_LLM_<NAME>_*`. `GET /v1/llms` et `jev-model llms` exposent le
catalogue public (`has_key`, jamais la clé).

```bash
uv run jev-model llms
```

Exemple JSON : `examples/models.json`.

## Hermes et OpenClaw

Oui, en local. Le process MCP n'a pas besoin de JEV ni de gateway :

```bash
uv run jev-model mcp
```

Un tool : `model_route`. Tu lui passes `task` et éventuellement `models`.
Tes clés restent dans l'environnement du process, pas dans l'appel.

**Hermes** (`~/.hermes/config.yaml`) :

```yaml
mcp_servers:
  jev-model:
    command: uv
    args: ["run", "--directory", "/chemin/vers/jev-model-router", "jev-model", "mcp"]
    env:
      JEV_PROVIDER: local
```

**OpenClaw** (`~/.openclaw/openclaw.json`, ou Settings > MCP > Stdio) :

```json
{
  "mcp": {
    "servers": {
      "jev-model": {
        "command": "uv",
        "args": ["run", "--directory", "/chemin/vers/jev-model-router", "jev-model", "mcp"],
        "env": { "JEV_PROVIDER": "local" }
      }
    }
  }
}
```

Exemples prêts à copier : `examples/hermes.yaml`, `examples/openclaw.json`.

## JEV + gateway (optionnel)

Si tu branches le cloud plus tard, deux clés suffisent : `JEV_API_KEY` /
`JEV_BASE_URL`, et ta gateway. Si `GATEWAY_*` est incomplet, le catalogue
multi-LLM résout le juge (`OPENROUTER_API_KEY`, `OPENAI_API_KEY`, etc.).

Pas de clé dans le corps HTTP ou MCP.

```bash
cp .env.example .env
```

`JEV_PROVIDER=jev` refuse de démarrer si JEV ou la gateway résolue
manque. Un modèle sans clé résoluble est rejeté (`missing_key`), sauf
Ollama.

## HTTP

```bash
uv run jev-model serve
```

`GET /`, `/demo`, `/healthz`, `/v1/llms`. `POST /v1/route`. Bind
`127.0.0.1`. Le body ne contient pas de clés.

## Validation locale

```bash
uv run jev-model benchmark
```

Jeu annoté dans `benchmarks/annotated_tasks.json`. C'est une baseline
locale, pas un essai JEV réel.

## Limites

Le tri local est déterministe (qualité, coût, latence, plus un bonus
lexical). Le scope isole des listes, ce n'est pas une auth. Un seul
saut de repli. Pas de génération de texte utilisateur. Pas de store,
pas de PyPI pour l'instant.

`docs/vision.md` est une cible longue, pas le contrat actuel.
