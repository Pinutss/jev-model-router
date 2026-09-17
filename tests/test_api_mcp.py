import io
import json

from jev_model_router.api.server import handle_llms, handle_route
from jev_model_router.cli import main
from jev_model_router.config import Settings
from jev_model_router.mcp_server import _dispatch


def _demo_models() -> list[dict]:
    return [
        {
            "id": "coding",
            "name": "Coding",
            "provider": "demo",
            "model": "coding-1",
            "quality": 0.9,
            "cost": 0.4,
            "latency": 0.3,
            "capabilities": ["chat", "coding"],
            "scope": "demo",
            "optional_key": True,
        }
    ]


def test_handle_route_rejects_keys_in_body() -> None:
    try:
        handle_route(
            {"task": "x", "models": [], "api_key": "secret"},
            Settings(provider="local"),
            show_rejected=True,
        )
    except Exception as exc:
        assert "cle" in str(exc)
    else:
        raise AssertionError("attendu un refus")


def test_handle_route_rejects_openai_key() -> None:
    try:
        handle_route(
            {"task": "x", "openai_api_key": "secret", "models": []},
            Settings(provider="local"),
            show_rejected=True,
        )
    except Exception as exc:
        assert "cle" in str(exc)
    else:
        raise AssertionError("attendu un refus")


def test_handle_route_rejects_openrouter_key() -> None:
    try:
        handle_route(
            {"task": "x", "openrouter_api_key": "secret", "models": []},
            Settings(provider="local"),
            show_rejected=True,
        )
    except Exception as exc:
        assert "cle" in str(exc)
    else:
        raise AssertionError("attendu un refus")


def test_handle_route_rejects_key_in_model() -> None:
    try:
        handle_route(
            {
                "task": "x",
                "models": [
                    {"id": "a", "name": "A", "provider": "demo", "model": "a", "api_key": "x"}
                ],
            },
            Settings(provider="local"),
            show_rejected=True,
        )
    except Exception as exc:
        assert "cle" in str(exc)
    else:
        raise AssertionError("attendu un refus")


def test_handle_route_selects() -> None:
    payload = handle_route(
        {
            "task": "fix python api bug",
            "scope": "demo",
            "prefer": "best",
            "models": _demo_models(),
        },
        Settings(provider="local"),
        show_rejected=True,
    )
    assert payload["decision"] == "select"
    assert payload["selected"]["id"] == "coding"
    assert "api_key" not in payload["selected"]


def test_handle_llms_is_public() -> None:
    payload = handle_llms()
    assert "llms" in payload
    blob = json.dumps(payload)
    assert "api_key" not in blob.replace("api_key_env", "")
    for row in payload["llms"]:
        assert "api_key" not in row


def test_mcp_lists_tool() -> None:
    response = _dispatch({"id": 1, "method": "tools/list"}, Settings(provider="local"))
    assert response is not None
    tools = response["result"]["tools"]
    assert tools[0]["name"] == "model_route"


def test_mcp_routes() -> None:
    response = _dispatch(
        {
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "model_route",
                "arguments": {
                    "task": "fix python api bug",
                    "scope": "demo",
                    "prefer": "best",
                    "models": _demo_models(),
                },
            },
        },
        Settings(provider="local"),
    )
    assert response is not None
    text = response["result"]["content"][0]["text"]
    body = json.loads(text)
    assert body["selected"]["id"] == "coding"


def test_mcp_rejects_keys() -> None:
    response = _dispatch(
        {
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "model_route",
                "arguments": {"task": "x", "models": [], "jev_api_key": "secret"},
            },
        },
        Settings(provider="local"),
    )
    assert response is not None
    assert response["result"]["isError"] is True
    assert "cle" in response["result"]["content"][0]["text"]


def test_cli_demo(capsys) -> None:
    assert main(["demo"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["decision"] == "select"
    assert out["selected"]["id"] in {
        "demo-cheap",
        "demo-quality",
        "demo-fast",
        "demo-balanced",
        "demo-vision",
    }
    assert "api_key" not in json.dumps(out).replace("api_key_env", "")


def test_cli_llms(capsys) -> None:
    assert main(["llms"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert "llms" in out
    for row in out["llms"]:
        assert "api_key" not in row


def test_cli_route(tmp_path, capsys) -> None:
    path = tmp_path / "job.json"
    path.write_text(
        json.dumps(
            {
                "task": "fix python api bug",
                "scope": "demo",
                "prefer": "best",
                "models": _demo_models(),
            }
        ),
        encoding="utf-8",
    )
    assert main(["route", "--file", str(path)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["selected"]["id"] == "coding"


def test_scores_parser() -> None:
    from jev_model_router.providers.scores import parse_score_list

    scores = parse_score_list({"scores": [{"id": "a", "confidence": 1.5}]})
    assert scores == {"a": 1.0}


def test_mcp_read_json_line() -> None:
    from jev_model_router.mcp_server import _read_message

    raw = json.dumps({"id": 1, "method": "initialize"}).encode("utf-8") + b"\n"
    message = _read_message(io.BytesIO(raw))
    assert message is not None
    assert message["method"] == "initialize"
