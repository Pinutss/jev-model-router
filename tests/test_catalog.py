import json

from jev_model_router.catalog import public_catalog, resolve_gateway
from jev_model_router.models import ModelProfile


def _clear_gateway(monkeypatch) -> None:
    for key in (
        "GATEWAY_BASE_URL",
        "GATEWAY_API_KEY",
        "GATEWAY_MODEL",
        "GATEWAY_MODELS",
        "JEV_MODELS_FILE",
        "JEV_LLM_STRATEGY",
        "JEV_LLM_DEFAULT",
        "OPENROUTER_API_KEY",
        "OPENAI_API_KEY",
        "GROQ_API_KEY",
        "TOGETHER_API_KEY",
        "FIREWORKS_API_KEY",
        "MISTRAL_API_KEY",
        "OLLAMA_BASE_URL",
    ):
        monkeypatch.delenv(key, raising=False)


def test_resolve_openrouter_with_key(monkeypatch) -> None:
    _clear_gateway(monkeypatch)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-key-1234567890abcd")
    monkeypatch.setenv("JEV_LLM_DEFAULT", "openrouter:anthropic/claude-sonnet-4")
    endpoint = resolve_gateway(provider="openrouter")
    assert endpoint.base_url == "https://openrouter.ai/api/v1"
    assert endpoint.model == "anthropic/claude-sonnet-4"
    assert endpoint.api_key == "sk-or-test-key-1234567890abcd"
    assert endpoint.api_key_env == "OPENROUTER_API_KEY"
    assert "api_key" not in endpoint.to_dict()


def test_public_catalog_never_returns_raw_key(monkeypatch) -> None:
    _clear_gateway(monkeypatch)
    secret = "sk-or-test-key-1234567890abcd"
    monkeypatch.setenv("OPENROUTER_API_KEY", secret)
    catalog = public_catalog()
    blob = json.dumps(catalog)
    assert secret not in blob
    assert "sk-or-test" not in blob
    assert catalog
    for row in catalog:
        assert "api_key" not in row
        assert "has_key" in row
        assert "api_key_env" in row
        if row["provider"] == "openrouter":
            assert row["has_key"] is True
            assert row["api_key_env"] == "OPENROUTER_API_KEY"


def test_catalog_entry_to_profile_has_no_key(monkeypatch) -> None:
    _clear_gateway(monkeypatch)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-hidden-key-1234567890abcd")
    from jev_model_router.catalog import load_catalog

    entry = next(item for item in load_catalog() if item.provider == "openrouter")
    profile = entry.to_profile()
    blob = json.dumps(profile.to_dict() if hasattr(profile, "to_dict") else profile.__dict__)
    assert "sk-or-hidden" not in blob
    assert not hasattr(profile, "api_key") or getattr(profile, "api_key", None) in (None, "")


def test_strategy_cheapest_resolve(monkeypatch) -> None:
    _clear_gateway(monkeypatch)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-key-1234567890abcd")
    endpoint = resolve_gateway(provider="openrouter", prefer="cheapest")
    assert endpoint.provider == "openrouter"
    assert endpoint.model == "openai/gpt-4o-mini"


def test_models_file_strips_api_key(monkeypatch, tmp_path) -> None:
    _clear_gateway(monkeypatch)
    path = tmp_path / "models.json"
    path.write_text(
        json.dumps(
            {
                "providers": {
                    "openrouter": {
                        "base_url": "https://openrouter.ai/api/v1",
                        "api_key_env": "OPENROUTER_API_KEY",
                        "api_key": "should-be-ignored",
                        "models": [
                            {
                                "id": "custom/model",
                                "quality": 0.4,
                                "cost": 0.1,
                                "latency": 0.1,
                            }
                        ],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("JEV_MODELS_FILE", str(path))
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-file-key-1234567890abcd")
    endpoint = resolve_gateway(provider="openrouter", model="custom/model")
    assert endpoint.model == "custom/model"
    blob = json.dumps(public_catalog())
    assert "should-be-ignored" not in blob
    assert "sk-or-file-key" not in blob


def test_classic_gateway_complete(monkeypatch) -> None:
    _clear_gateway(monkeypatch)
    monkeypatch.setenv("GATEWAY_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("GATEWAY_API_KEY", "sk-classic-key-1234567890abcd")
    monkeypatch.setenv("GATEWAY_MODEL", "gpt-4o-mini")
    endpoint = resolve_gateway()
    assert endpoint.provider == "gateway"
    assert endpoint.model == "gpt-4o-mini"
    assert endpoint.api_key == "sk-classic-key-1234567890abcd"
    assert "sk-classic" not in json.dumps(endpoint.to_dict())


def test_model_profile_from_mapping_rejects_key() -> None:
    try:
        ModelProfile.from_mapping(
            {
                "id": "x",
                "name": "X",
                "provider": "demo",
                "model": "x",
                "api_key": "secret",
            }
        )
    except Exception as exc:
        assert "cle" in str(exc)
    else:
        raise AssertionError("attendu un refus")
