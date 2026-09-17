"""Demonstration locale sur le catalogue d'exemple, sans reseau."""
from jev_model_router import DEFAULT_MODELS, ModelRouter

result = ModelRouter(provider="local").route(
    task="Summarize this meeting and draft a follow-up email",
    models=DEFAULT_MODELS,
    prefer="balanced",
    scope="demo",
)
print(result.decision, result.selected.id if result.selected else result.abstain_reason)
if result.selected:
    print(result.selected.reasons)
    print("has_key", result.selected.has_key)
    print("api_key_env", result.selected.api_key_env)
    assert "api_key" not in result.selected.to_dict()
if result.fallback:
    print("repli", result.fallback.id)
for item in result.rejected:
    print("rejet", item.id, item.reason)
assert result.decision == "select"
assert result.selected is not None
assert result.selected.id in {model.id for model in DEFAULT_MODELS}
