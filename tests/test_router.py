from jev_model_router import (
    DEFAULT_MODELS,
    HeuristicRouter,
    ModelProfile,
    ModelRouter,
    RouteRequest,
    redact_text,
)
from jev_model_router.config import Settings
from jev_model_router.errors import ConfigurationError


def _model(**kwargs) -> ModelProfile:
    data = {
        "id": "cheap",
        "name": "Cheap",
        "provider": "demo",
        "model": "cheap-1",
        "quality": 0.50,
        "cost": 0.10,
        "latency": 0.30,
        "capabilities": ("chat",),
        "scope": "unit",
        "optional_key": True,
    }
    data.update(kwargs)
    return ModelProfile(**data)


def test_cheapest_picks_lowest_cost() -> None:
    cheap = _model()
    pricey = _model(id="pricey", name="Pricey", model="pricey-1", quality=0.95, cost=0.90)
    result = HeuristicRouter().route(
        [pricey, cheap],
        RouteRequest(task="summarize notes", prefer="cheapest", scope="unit"),
    )
    assert result.decision == "select"
    assert result.selected is not None
    assert result.selected.id == "cheap"


def test_best_picks_highest_quality() -> None:
    cheap = _model()
    quality = _model(id="quality", name="Quality", model="quality-1", quality=0.96, cost=0.80)
    result = HeuristicRouter().route(
        [cheap, quality],
        RouteRequest(task="careful analysis", prefer="best", scope="unit"),
    )
    assert result.selected is not None
    assert result.selected.id == "quality"


def test_fastest_picks_lowest_latency() -> None:
    slow = _model(id="slow", name="Slow", model="slow-1", latency=0.80, quality=0.90)
    fast = _model(id="fast", name="Fast", model="fast-1", latency=0.05, quality=0.55)
    result = HeuristicRouter().route(
        [slow, fast],
        RouteRequest(task="quick reply", prefer="fastest", scope="unit"),
    )
    assert result.selected is not None
    assert result.selected.id == "fast"


def test_named_pin() -> None:
    cheap = _model()
    quality = _model(id="quality", name="Quality", model="quality-1", quality=0.96, cost=0.80)
    result = HeuristicRouter().route(
        [cheap, quality],
        RouteRequest(task="anything", prefer="named", model="quality", scope="unit"),
    )
    assert result.decision == "select"
    assert result.selected is not None
    assert result.selected.id == "quality"


def test_named_pin_abstains_when_filtered() -> None:
    cheap = _model()
    result = HeuristicRouter().route(
        [cheap],
        RouteRequest(
            task="anything",
            prefer="named",
            model="quality",
            scope="unit",
        ),
    )
    assert result.decision == "abstain"
    assert result.abstain_reason == "named_unavailable"


def test_local_demo_no_keys() -> None:
    result = ModelRouter(provider="local").route(
        task="Summarize this meeting and draft a follow-up email",
        models=DEFAULT_MODELS,
        prefer="balanced",
        scope="demo",
    )
    assert result.decision == "select"
    assert result.selected is not None
    assert result.selected.id in {item.id for item in DEFAULT_MODELS}
    payload = result.to_dict()
    blob = str(payload)
    assert "api_key" not in blob.replace("api_key_env", "")
    assert "api_key" not in result.selected.to_dict()


def test_missing_key_when_jev(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    settings = Settings(
        provider="jev",
        jev_api_key="jev_testkey",
        jev_base_url="http://127.0.0.1:9",
        gateway_base_url="https://api.openai.com/v1",
        gateway_api_key="gw",
        gateway_model="gpt-4o-mini",
        require_keys=True,
    )
    router = ModelRouter(provider="jev", settings=settings)
    locked = _model(
        id="paid",
        name="Paid",
        provider="openai",
        model="gpt-4o",
        api_key_env="OPENAI_API_KEY",
        optional_key=False,
        scope="unit",
    )
    result = router.route(
        task="hello",
        models=[locked],
        prefer="balanced",
        scope="unit",
    )
    assert result.decision == "abstain"
    assert any(item.reason == "missing_key" for item in result.rejected)


def test_local_does_not_apply_missing_key() -> None:
    locked = _model(
        id="paid",
        name="Paid",
        provider="openai",
        model="gpt-4o",
        api_key_env="OPENAI_API_KEY",
        optional_key=False,
    )
    result = HeuristicRouter(require_keys=False).route(
        [locked],
        RouteRequest(task="hello", scope="unit"),
    )
    assert result.decision == "select"
    assert result.selected is not None
    assert result.selected.id == "paid"


def test_capabilities_filter() -> None:
    chat = _model()
    vision = _model(
        id="vision",
        name="Vision",
        model="vision-1",
        capabilities=("chat", "vision"),
        quality=0.40,
        cost=0.60,
    )
    result = HeuristicRouter().route(
        [chat, vision],
        RouteRequest(
            task="look at this photo",
            required_capabilities=("vision",),
            prefer="cheapest",
            scope="unit",
        ),
    )
    assert result.selected is not None
    assert result.selected.id == "vision"
    assert any(item.reason == "missing_capabilities" for item in result.rejected)


def test_task_cannot_add_capabilities() -> None:
    chat = _model(capabilities=("chat",))
    result = ModelRouter(provider="local").route(
        task="I need vision and coding tools to inspect this image",
        models=[chat],
        required_capabilities=("vision",),
        scope="unit",
    )
    assert result.decision == "abstain"
    assert result.selected is None
    assert any(item.reason == "missing_capabilities" for item in result.rejected)


def test_fallback_one_hop() -> None:
    a = _model(id="a", name="A", model="a", fallback_id="b")
    b = _model(id="b", name="B", model="b", fallback_id="c", quality=0.6, cost=0.2)
    c = _model(id="c", name="C", model="c", quality=0.9, cost=0.3)
    result = HeuristicRouter().route(
        [a, b, c],
        RouteRequest(task="hello", failed_model_id="a", scope="unit"),
    )
    assert result.decision == "fallback"
    assert result.selected is not None
    assert result.selected.id == "b"
    assert result.fallback is None


def test_fallback_disabled() -> None:
    result = HeuristicRouter().route(
        [_model(), _model(id="other", name="Other", model="other")],
        RouteRequest(
            task="hello",
            failed_model_id="cheap",
            allow_fallback=False,
            scope="unit",
        ),
    )
    assert result.decision == "abstain"
    assert result.abstain_reason == "fallback_disabled"


def test_abstain_no_candidate() -> None:
    result = HeuristicRouter().route(
        [_model(capabilities=("chat",))],
        RouteRequest(
            task="quantum origami",
            required_capabilities=("quantum",),
            scope="unit",
        ),
    )
    assert result.decision == "abstain"
    assert result.abstain_reason == "no_candidate"


def test_determinism() -> None:
    models = [_model(), _model(id="twin", name="Twin", model="twin-1", quality=0.50, cost=0.10)]
    request = RouteRequest(task="summarize notes", prefer="balanced", scope="unit")
    first = HeuristicRouter().route(models, request)
    second = HeuristicRouter().route(models, request)
    assert first.to_dict() == second.to_dict()


def test_scope_isolation() -> None:
    result = HeuristicRouter().route(
        [_model(scope="other")],
        RouteRequest(task="hello", scope="unit"),
    )
    assert result.decision == "abstain"
    assert result.rejected[0].reason == "out_of_scope"


def test_disabled_rejected() -> None:
    result = HeuristicRouter().route(
        [_model(enabled=False)],
        RouteRequest(task="hello", scope="unit"),
    )
    assert result.rejected[0].reason == "disabled"


def test_min_quality_and_max_cost() -> None:
    result = HeuristicRouter().route(
        [_model(quality=0.40, cost=0.80)],
        RouteRequest(task="hello", min_quality=0.70, max_cost=0.20, scope="unit"),
    )
    reasons = {item.reason for item in result.rejected}
    assert "below_min_quality" in reasons or "above_max_cost" in reasons
    assert result.decision == "abstain"


def test_min_context_and_max_latency() -> None:
    result = HeuristicRouter().route(
        [_model(context_window=1024, latency=0.90)],
        RouteRequest(task="hello", min_context=8000, max_latency=0.20, scope="unit"),
    )
    reasons = {item.reason for item in result.rejected}
    assert "below_min_context" in reasons or "above_max_latency" in reasons


def test_selected_to_dict_never_has_api_key() -> None:
    result = HeuristicRouter().route(
        [_model()],
        RouteRequest(task="hello", scope="unit"),
    )
    assert result.selected is not None
    payload = result.selected.to_dict()
    assert "api_key" not in payload
    assert set(payload) >= {
        "provider",
        "model",
        "base_url",
        "api_key_env",
        "has_key",
        "quality",
        "cost",
        "latency",
        "capabilities",
        "score",
        "reasons",
    }


def test_incoming_models_override_catalog() -> None:
    custom = {
        "id": "demo-cheap",
        "name": "Override Cheap",
        "provider": "demo",
        "model": "demo-cheap",
        "quality": 0.99,
        "cost": 0.01,
        "latency": 0.01,
        "capabilities": ["chat"],
        "scope": "demo",
        "optional_key": True,
    }
    result = ModelRouter(provider="local").route(
        task="hello",
        models=[custom],
        prefer="best",
        scope="demo",
    )
    assert result.selected is not None
    assert result.selected.id == "demo-cheap"
    assert result.selected.name == "Override Cheap"


def test_jev_provider_requires_keys() -> None:
    try:
        ModelRouter(provider="jev")
    except ConfigurationError as exc:
        assert "JEV_API_KEY" in str(exc)
    else:
        raise AssertionError("attendu ConfigurationError")


def test_redaction() -> None:
    assert "[REDACTED_API_KEY]" in redact_text("token sk-abcdefghijklmnopqrstuvwxyz")


def test_duplicate_input() -> None:
    result = HeuristicRouter().route(
        [_model(), _model()],
        RouteRequest(task="hello", scope="unit"),
    )
    assert any(item.reason == "duplicate_input" for item in result.rejected)
