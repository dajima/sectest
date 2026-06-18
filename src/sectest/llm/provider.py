"""LiteLLM / Direct ModelProvider for openai-agents SDK.

Two modes — auto-selected based on :class:`LLMConfig`:

**Direct mode** (LLM_API_BASE is set):
    AsyncOpenAI client connects directly to the provider's API endpoint
    (DeepSeek, OpenAI, etc.).  No proxy process needed.

**LiteLLM Proxy mode** (LLM_API_BASE is NOT set):
    AsyncOpenAI client connects to the LiteLLM Proxy at
    ``http://localhost:4000/v1``, which handles multi-provider routing,
    automatic fallback chains, and cost tracking.

Example usage::

    from sectest.llm.provider import get_model

    model = get_model()                   # uses LLMConfig default
    model = get_model("deepseek/deepseek-v4-flash")

    result = await Runner.run(
        agent,
        "input",
        run_config=RunConfig(model_provider=llm_provider),
    )
"""

from __future__ import annotations

from openai import AsyncOpenAI
from agents import (
    Model,
    ModelProvider,
    OpenAIChatCompletionsModel,
    set_tracing_disabled,
)

from sectest.llm.config import LLMConfig

# ---------------------------------------------------------------------------
# Disable built-in OpenAI tracing for Phase 1.
#
# In Phase 2 this will be replaced by the Langfuse / OpenInference exporter.
# Remove this call at that time.
# ---------------------------------------------------------------------------
set_tracing_disabled(disabled=True)


def _build_client(config: LLMConfig) -> AsyncOpenAI:
    """Create an AsyncOpenAI client for the current connection mode."""
    return AsyncOpenAI(
        base_url=config.effective_base_url,
        api_key=config.effective_api_key,
    )


class LiteLLMModelProvider(ModelProvider):
    """Model provider that routes LLM calls through LiteLLM or directly.

    Implements the :class:`agents.ModelProvider` interface.  Connection
    mode (direct vs proxy) is determined by :class:`LLMConfig` based on
    which environment variables are set.

    Parameters:
        config: Optional :class:`LLMConfig`.  When *None*, a default
            config is created (reads env vars at construction time).
    """

    def __init__(self, config: LLMConfig | None = None) -> None:
        self._config = config or LLMConfig()
        self._client = _build_client(self._config)

    # -- ModelProvider interface ----------------------------------------------

    def get_model(self, model_name: str | None = None) -> Model:
        """Return an :class:`OpenAIChatCompletionsModel`.

        Parameters:
            model_name: The model identifier (e.g. ``"gpt-4o"``,
                ``"deepseek/deepseek-v4-flash"``).  When *None*, the
                default from ``LLMConfig.model`` is used.

        Returns:
            An :class:`OpenAIChatCompletionsModel` configured for the
            current connection mode.
        """
        resolved_name = model_name or self._config.model
        return OpenAIChatCompletionsModel(
            model=resolved_name,
            openai_client=self._client,
        )


# ---------------------------------------------------------------------------
# Singleton — one provider shared across the platform.
# Lazily constructed so that import works even when API keys are not yet
# set (e.g. during test collection).
# ---------------------------------------------------------------------------
_llm_provider: LiteLLMModelProvider | None = None


def _get_llm_provider() -> LiteLLMModelProvider:
    """Return the module-level singleton, creating it on first access."""
    global _llm_provider
    if _llm_provider is None:
        _llm_provider = LiteLLMModelProvider()
    return _llm_provider


def get_model(model_name: str | None = None) -> Model:
    """Convenience helper that delegates to the singleton provider.

    Parameters:
        model_name: Optional model name.  When *None*, the default
            from the environment is used.

    Returns:
        An :class:`OpenAIChatCompletionsModel`.
    """
    return _get_llm_provider().get_model(model_name)


def __getattr__(name: str) -> object:
    if name == "llm_provider":
        return _get_llm_provider()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
