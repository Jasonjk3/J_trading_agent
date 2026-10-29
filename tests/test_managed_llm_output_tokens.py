import asyncio
from types import SimpleNamespace

from app.v1.services import managed_llm_service


def _model(*, max_tokens=81920, max_output_tokens=None, use_max_completion_tokens=False):
    return SimpleNamespace(
        model_id="deepseek-v4.1-flash",
        name="DeepSeek V4.1 Flash",
        api_config_id=1,
        max_tokens=max_tokens,
        max_output_tokens=max_output_tokens,
        use_max_completion_tokens=use_max_completion_tokens,
        custom_params=None,
    )


def _api_config():
    return SimpleNamespace(
        api_key="test-key",
        api_type="openai",
        api_url="https://example.test/v1",
        extra_headers=None,
        extra_params=None,
    )


def test_managed_llm_uses_independent_output_token_limit(monkeypatch):
    captured = {}

    async def fake_get_model(_session, _model_id):
        return _model(max_output_tokens=16384, use_max_completion_tokens=True)

    async def fake_get_config(_session, _config_id):
        return _api_config()

    def fake_create_llm_direct(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(managed_llm_service, "get_model_by_id", fake_get_model)
    monkeypatch.setattr(managed_llm_service, "get_api_config_by_id", fake_get_config)
    monkeypatch.setattr(
        managed_llm_service.LLMFactory,
        "create_llm_direct",
        fake_create_llm_direct,
    )

    llm, error, _ = asyncio.run(
        managed_llm_service.build_llm_from_managed_model(
            object(), 1, temperature=0
        )
    )

    assert llm is not None
    assert error is None
    assert captured["max_tokens"] == 16384
    assert captured["use_max_completion_tokens"] is True


def test_managed_llm_legacy_limit_is_not_capped_at_8192(monkeypatch):
    captured = {}

    async def fake_get_model(_session, _model_id):
        return _model(max_tokens=81920, max_output_tokens=None)

    async def fake_get_config(_session, _config_id):
        return _api_config()

    def fake_create_llm_direct(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(managed_llm_service, "get_model_by_id", fake_get_model)
    monkeypatch.setattr(managed_llm_service, "get_api_config_by_id", fake_get_config)
    monkeypatch.setattr(
        managed_llm_service.LLMFactory,
        "create_llm_direct",
        fake_create_llm_direct,
    )

    llm, error, _ = asyncio.run(
        managed_llm_service.build_llm_from_managed_model(
            object(), 1, temperature=0
        )
    )

    assert llm is not None
    assert error is None
    assert captured["max_tokens"] == 81920
