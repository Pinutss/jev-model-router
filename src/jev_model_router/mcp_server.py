"""Serveur MCP stdio : un tool model_route. Les cles restent dans l'env."""
from __future__ import annotations

import json
import sys
from typing import Any

from .config import Settings
from .facade import ModelRouter
from .models import FORBIDDEN_KEY_FIELDS, reject_secret_fields
from .version import __version__

PROTOCOL_VERSION = "2024-11-05"


def run_mcp(settings: Settings | None = None) -> None:
    conf = settings or Settings.from_env()
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer
    while True:
        message = _read_message(stdin)
        if message is None:
            return
        if message.get("method") == "notifications/initialized":
            continue
        response = _dispatch(message, conf)
        if response is not None:
            _write_message(stdout, response)


def _dispatch(message: dict[str, Any], settings: Settings) -> dict[str, Any] | None:
    method = message.get("method")
    msg_id = message.get("id")
    if method == "initialize":
        return _ok(
            msg_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "jev-model-router", "version": __version__},
            },
        )
    if method == "tools/list":
        return _ok(msg_id, {"tools": [_tool_schema()]})
    if method == "tools/call":
        params = message.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        if name != "model_route":
            return _ok(msg_id, _tool_error(f"outil inconnu : {name}"))
        if any(str(key).lower() in FORBIDDEN_KEY_FIELDS for key in args):
            return _ok(msg_id, _tool_error("les cles ne doivent pas figurer dans les arguments"))
        try:
            reject_secret_fields(args, where="arguments")
            result = ModelRouter(provider=settings.provider, settings=settings).route(
                task=str(args.get("task") or ""),
                models=args.get("models"),
                required_capabilities=args.get("required_capabilities") or (),
                prefer=args.get("prefer"),
                min_quality=float(args.get("min_quality", 0.0)),
                max_cost=float(args.get("max_cost", 1.0)),
                max_latency=float(args.get("max_latency", 1.0)),
                min_context=int(args.get("min_context", 0)),
                allow_fallback=args.get("allow_fallback", True),
                failed_model_id=args.get("failed_model_id"),
                provider=args.get("provider"),
                model=args.get("model"),
                scope=str(args.get("scope") or "default"),
                max_alternatives=args.get("max_alternatives"),
            )
        except Exception as exc:  # noqa: BLE001, surface MCP
            return _ok(msg_id, _tool_error(str(exc)))
        show_rejected = bool(settings.auth_token) or settings.host not in {"0.0.0.0", "::"}
        text = json.dumps(result.to_dict(include_rejected=show_rejected), ensure_ascii=False)
        return _ok(msg_id, {"content": [{"type": "text", "text": text}]})
    if msg_id is None:
        return None
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": -32601, "message": f"methode inconnue : {method}"},
    }


def _tool_schema() -> dict[str, Any]:
    return {
        "name": "model_route",
        "description": (
            "Choisit un modele LLM sous contraintes de qualite, cout et latence. "
            "N'appelle pas le modele pour generer du texte utilisateur."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {"type": "string"},
                "models": {"type": "array", "items": {"type": "object"}},
                "required_capabilities": {"type": "array", "items": {"type": "string"}},
                "prefer": {
                    "type": "string",
                    "enum": ["balanced", "best", "cheapest", "fastest", "named"],
                },
                "min_quality": {"type": "number"},
                "max_cost": {"type": "number"},
                "max_latency": {"type": "number"},
                "min_context": {"type": "integer"},
                "allow_fallback": {"type": "boolean"},
                "failed_model_id": {"type": "string"},
                "provider": {"type": "string"},
                "model": {"type": "string"},
                "scope": {"type": "string"},
                "max_alternatives": {"type": "integer"},
            },
            "required": ["task"],
        },
    }


def _ok(msg_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _tool_error(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "isError": True}


def _read_message(stdin: Any) -> dict[str, Any] | None:
    header = stdin.readline()
    if not header:
        return None
    if header.lower().startswith(b"content-length:"):
        length = int(header.split(b":", 1)[1].strip())
        while True:
            line = stdin.readline()
            if line in (b"\r\n", b"\n", b""):
                break
        body = stdin.read(length)
        return json.loads(body.decode("utf-8"))
    line = header.decode("utf-8").strip()
    if not line:
        return _read_message(stdin)
    return json.loads(line)


def _write_message(stdout: Any, message: dict[str, Any]) -> None:
    raw = json.dumps(message, ensure_ascii=False).encode("utf-8")
    stdout.write(f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii") + raw)
    stdout.flush()
