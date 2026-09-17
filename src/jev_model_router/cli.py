"""Interface en ligne de commande."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .catalog import public_catalog
from .config import Settings, load_dotenv
from .facade import ModelRouter
from .mcp_server import run_mcp
from .registry import DEFAULT_MODELS


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="jev-model", description="Routeur de modeles LLM JEV")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("demo", help="Demonstration locale sans cle ni reseau")
    route = sub.add_parser("route", help="Routage selon JEV_PROVIDER")
    route.add_argument("--file", required=True, help="JSON {task?, models?}")
    route.add_argument("--task", default=None)
    route.add_argument("--prefer", default=None)
    route.add_argument("--scope", default="default")
    sub.add_parser("serve", help="Serveur HTTP /v1/route")
    sub.add_parser("mcp", help="Serveur MCP stdio (model_route)")
    bench = sub.add_parser("benchmark", help="Jeu annote local, hors JEV")
    bench.add_argument(
        "--file",
        default=str(Path(__file__).resolve().parents[2] / "benchmarks" / "annotated_tasks.json"),
    )
    sub.add_parser("llms", help="Catalogue public (jamais de cle brute)")

    args = parser.parse_args(argv)
    if args.command == "demo":
        return _demo()
    if args.command == "route":
        return _route(args.file, args.task, args.scope, args.prefer)
    if args.command == "serve":
        from .api.server import serve

        serve(Settings.from_env())
        return 0
    if args.command == "mcp":
        run_mcp(Settings.from_env())
        return 0
    if args.command == "benchmark":
        return _benchmark(args.file)
    if args.command == "llms":
        return _llms()
    parser.error("commande inconnue")
    return 2


def _demo() -> int:
    router = ModelRouter(provider="mock")
    result = router.route(
        task="Summarize this meeting and draft a follow-up email",
        models=DEFAULT_MODELS,
        prefer="balanced",
        scope="demo",
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0


def _route(path: str, task: str | None, scope: str, prefer: str | None) -> int:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        print("objet JSON requis", file=sys.stderr)
        return 2
    chosen_task = task or payload.get("task")
    if not chosen_task:
        print("task manquante (--task ou champ JSON)", file=sys.stderr)
        return 2
    settings = Settings.from_env()
    result = ModelRouter(provider=settings.provider, settings=settings).route(
        task=str(chosen_task),
        models=payload.get("models"),
        required_capabilities=payload.get("required_capabilities") or (),
        prefer=prefer or payload.get("prefer"),
        min_quality=float(payload.get("min_quality", 0.0)),
        max_cost=float(payload.get("max_cost", 1.0)),
        max_latency=float(payload.get("max_latency", 1.0)),
        min_context=int(payload.get("min_context", 0)),
        allow_fallback=payload.get("allow_fallback", True),
        failed_model_id=payload.get("failed_model_id"),
        provider=payload.get("provider"),
        model=payload.get("model"),
        scope=str(payload.get("scope") or scope),
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0


def _benchmark(path: str) -> int:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    cases = payload.get("cases") if isinstance(payload, dict) else payload
    if not isinstance(cases, list):
        print("cases (array) obligatoire", file=sys.stderr)
        return 2
    router = ModelRouter(provider="local")
    ok = 0
    for case in cases:
        models = case.get("models") or DEFAULT_MODELS
        result = router.route(
            task=str(case["task"]),
            models=models,
            required_capabilities=case.get("required_capabilities") or (),
            prefer=case.get("prefer"),
            min_quality=float(case.get("min_quality", 0.0)),
            max_cost=float(case.get("max_cost", 1.0)),
            max_latency=float(case.get("max_latency", 1.0)),
            min_context=int(case.get("min_context", 0)),
            allow_fallback=case.get("allow_fallback", True),
            failed_model_id=case.get("failed_model_id"),
            provider=case.get("provider"),
            model=case.get("model"),
            scope=str(case.get("scope") or "demo"),
        )
        expected_decision = case.get("expected_decision")
        expected_model = case.get("expected")
        decision_ok = expected_decision is None or result.decision == expected_decision
        model_ok = expected_model is None or (
            result.selected is not None and result.selected.id == expected_model
        )
        passed = decision_ok and model_ok
        ok += int(passed)
        mark = "ok" if passed else "ko"
        chosen = result.selected.id if result.selected else result.abstain_reason
        print(f"{mark} {case.get('id', '?')} -> {result.decision}:{chosen}")
    total = len(cases)
    print(f"{ok}/{total} local baseline")
    return 0 if ok == total else 1


def _llms() -> int:
    print(json.dumps({"llms": public_catalog()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
