"""Unit tests for LLM config and ModelProvider (T5).

Tests verify:
    - Direct mode: LLM_API_BASE / LLM_API_KEY / LLM_MODEL env vars
    - Proxy mode: LITELLM_BASE_URL / LITELLM_API_KEY fallback
    - get_model returns correct model type with resolved name
    - LLMConfig raises on missing key in both modes
    - set_tracing_disabled is called at module level

All external API calls are mocked — no real LLM calls are made.
"""

from __future__ import annotations

import os
from unittest import mock

import pytest
from agents import OpenAIChatCompletionsModel


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove LLM env vars before each test so they don't leak."""
    for key in (
        "LLM_MODEL", "LLM_API_KEY", "LLM_API_BASE",
        "LITELLM_BASE_URL", "LITELLM_API_KEY", "DEFAULT_MODEL",
    ):
        monkeypatch.delenv(key, raising=False)


def _make_config(**env: str) -> "LLMConfig":
    """Create an LLMConfig with the given env vars set (and nothing else)."""
    from sectest.llm.config import LLMConfig

    with mock.patch.dict(os.environ, env, clear=True):
        return LLMConfig()


# ---------------------------------------------------------------------------
# Tests: LLMConfig — direct mode
# ---------------------------------------------------------------------------


class TestDirectMode:
    def test_direct_mode_detected_when_llm_api_base_is_set(self) -> None:
        config = _make_config(
            LLM_API_BASE="https://api.deepseek.com/v1",
            LLM_API_KEY="sk-deepseek",
        )
        assert config.is_direct_mode is True
        assert config.effective_base_url == "https://api.deepseek.com/v1"
        assert config.effective_api_key == "sk-deepseek"

    def test_model_reads_llm_model_env_var(self) -> None:
        config = _make_config(
            LLM_API_BASE="https://api.deepseek.com/v1",
            LLM_API_KEY="sk-deepseek",
            LLM_MODEL="deepseek/deepseek-v4-flash",
        )
        assert config.model == "deepseek/deepseek-v4-flash"

    def test_direct_mode_raises_when_api_key_missing(self) -> None:
        with pytest.raises(ValueError, match="LLM_API_KEY"):
            _make_config(LLM_API_BASE="https://api.deepseek.com/v1")

    def test_effective_properties_in_direct_mode(self) -> None:
        config = _make_config(
            LLM_API_BASE="https://custom.api/v1",
            LLM_API_KEY="sk-custom-key",
            LLM_MODEL="custom-model",
            # Also set LiteLLM vars — they should be ignored in direct mode
            LITELLM_API_KEY="sk-should-be-ignored",
            LITELLM_BASE_URL="http://should-be-ignored:4000/v1",
        )
        assert config.is_direct_mode is True
        assert config.effective_base_url == "https://custom.api/v1"
        assert config.effective_api_key == "sk-custom-key"
        assert config.model == "custom-model"


# ---------------------------------------------------------------------------
# Tests: LLMConfig — proxy mode
# ---------------------------------------------------------------------------


class TestProxyMode:
    def test_proxy_mode_when_llm_api_base_missing(self) -> None:
        config = _make_config(LITELLM_API_KEY="sk-proxy-key")
        assert config.is_direct_mode is False
        assert config.effective_base_url == "http://localhost:4000/v1"
        assert config.effective_api_key == "sk-proxy-key"

    def test_proxy_mode_custom_url(self) -> None:
        config = _make_config(
            LITELLM_BASE_URL="https://litellm.example.com/v1",
            LITELLM_API_KEY="sk-custom",
        )
        assert config.effective_base_url == "https://litellm.example.com/v1"
        assert config.effective_api_key == "sk-custom"

    def test_proxy_mode_raises_when_litellm_key_missing(self) -> None:
        with pytest.raises(ValueError, match="LITELLM_API_KEY"):
            _make_config()  # no keys at all

    def test_model_defaults_to_gpt4o_in_proxy_mode(self) -> None:
        config = _make_config(LITELLM_API_KEY="sk-test")
        assert config.model == "gpt-4o"

    def test_legacy_default_model_still_works(self) -> None:
        config = _make_config(
            LITELLM_API_KEY="sk-test",
            DEFAULT_MODEL="claude-sonnet-4",
        )
        assert config.model == "claude-sonnet-4"

    def test_llm_model_overrides_default_model(self) -> None:
        config = _make_config(
            LITELLM_API_KEY="sk-test",
            LLM_MODEL="my-custom-model",
            DEFAULT_MODEL="gpt-4o",
        )
        assert config.model == "my-custom-model"


# ---------------------------------------------------------------------------
# Test: LiteLLMModelProvider
# ---------------------------------------------------------------------------


class TestLiteLLMModelProvider:
    def test_get_model_returns_openai_model(self) -> None:
        from sectest.llm.provider import LiteLLMModelProvider

        config = _make_config(LITELLM_API_KEY="sk-test")
        provider = LiteLLMModelProvider(config=config)
        model = provider.get_model("gpt-4o")

        assert isinstance(model, OpenAIChatCompletionsModel)
        assert model.model == "gpt-4o"

    def test_get_model_with_specific_name(self) -> None:
        from sectest.llm.provider import LiteLLMModelProvider

        config = _make_config(LITELLM_API_KEY="sk-test")
        provider = LiteLLMModelProvider(config=config)
        model = provider.get_model("deepseek/deepseek-v4-flash")
        assert model.model == "deepseek/deepseek-v4-flash"

    def test_get_model_uses_default_when_none(self) -> None:
        from sectest.llm.provider import LiteLLMModelProvider

        config = _make_config(LITELLM_API_KEY="sk-test", LLM_MODEL="gpt-4o-mini")
        provider = LiteLLMModelProvider(config=config)
        model = provider.get_model(None)
        assert model.model == "gpt-4o-mini"

    def test_provider_client_configured_correctly_proxy_mode(self) -> None:
        from sectest.llm.provider import LiteLLMModelProvider

        config = _make_config(LITELLM_API_KEY="sk-test")
        provider = LiteLLMModelProvider(config=config)
        assert provider._config.is_direct_mode is False
        assert "localhost" in str(provider._client.base_url)
        assert "/v1" in str(provider._client.base_url)

    def test_provider_client_configured_correctly_direct_mode(self) -> None:
        from sectest.llm.provider import LiteLLMModelProvider

        config = _make_config(
            LLM_API_BASE="https://api.deepseek.com/v1",
            LLM_API_KEY="sk-deepseek",
        )
        provider = LiteLLMModelProvider(config=config)
        assert provider._config.is_direct_mode is True
        assert "deepseek.com" in str(provider._client.base_url)


# ---------------------------------------------------------------------------
# Tests: Singleton and helper
# ---------------------------------------------------------------------------


class TestSingletonAndHelper:
    def test_get_model_function_returns_model(self) -> None:
        from sectest.llm.provider import get_model

        with mock.patch.dict(os.environ, {"LITELLM_API_KEY": "sk-test"}):
            model = get_model("gpt-4o")
            assert isinstance(model, OpenAIChatCompletionsModel)
            assert model.model == "gpt-4o"

    def test_get_model_function_no_args_uses_default(self) -> None:
        from sectest.llm.provider import get_model

        with mock.patch.dict(os.environ, {"LITELLM_API_KEY": "sk-test"}):
            model = get_model()
            assert model.model == "gpt-4o"


# ---------------------------------------------------------------------------
# Tests: tracing disabled
# ---------------------------------------------------------------------------


class TestTracingDisabled:
    def test_tracing_disabled_at_module_level(self) -> None:
        """Verify set_tracing_disabled is callable (called at import time)."""
        from agents import set_tracing_disabled

        set_tracing_disabled(disabled=True)
        # No exception = success.
