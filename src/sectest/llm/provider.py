"""LiteLLM ModelProvider for openai-agents SDK.

Connects the openai-agents SDK to LiteLLM Proxy for multi-provider
LLM routing with automatic fallback (L-05).

Example usage::

    from sectest.llm.provider import get_model

    model = get_model("gpt-4o")          # specific model
    model = get_model()                   # uses LLMConfig.default_model

    # Or via Runner:
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
# The openai-agents SDK ships with a built-in trace exporter that sends
# spans directly to OpenAI.  In Phase 2 this will be replaced by the
# Langfuse / OpenInference exporter, and this call MUST be removed.
# ---------------------------------------------------------------------------
set_tracing_disabled(disabled=True)


def _build_client(config: LLMConfig) -> AsyncOpenAI:
    """Create an AsyncOpenAI client pointed at the LiteLLM Proxy."""
    return AsyncOpenAI(base_url=config.base_url, api_key=config.api_key)


class LiteLLMModelProvider(ModelProvider):
    """Model provider that routes LLM calls through LiteLLM Proxy.

    Implements the :class:`agents.ModelProvider` interface so the
    openai-agents SDK can use our LiteLLM-backed :class:`AsyncOpenAI`
    client instead of hitting the OpenAI API directly.

    Parameters:
        config: Optional :class:`LLMConfig`.  When *None*, a default
            config is created (reads env vars at construction time).
    """

    # ------------------------------------------------------------------
    # The ``__init__`` accepts an optional config to allow tests to
    # inject their own LLMConfig with a controlled api_key.
    # ------------------------------------------------------------------

    def __init__(self, config: LLMConfig | None = None) -> None:
        self._config = config or LLMConfig()
        self._client = _build_client(self._config)

    def get_model(self, model_name: str | None = None) -> Model:
        """Return an :class:`OpenAIChatCompletionsModel` bound to LiteLLM.

        Parameters:
            model_name: The model identifier (e.g. ``"gpt-4o"``,
                ``"claude-sonnet-4"``).  When *None*, the default from
                ``LLMConfig.default_model`` is used.

        Returns:
            An :class:`OpenAIChatCompletionsModel` configured to use
            the LiteLLM Proxy endpoint.
        """
        resolved_name = model_name or self._config.default_model
        return OpenAIChatCompletionsModel(
            model=resolved_name,
            openai_client=self._client,
        )


# ---------------------------------------------------------------------------
# Singleton — one provider shared across the platform.
# Lazily constructed so that import works even when LITELLM_API_KEY is
# not yet set in the environment (e.g. during test collection).
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
        An :class:`OpenAIChatCompletionsModel` routed through LiteLLM.
    """
    return _get_llm_provider().get_model(model_name)


# Backwards-compatible alias.  Property so that ``llm_provider`` resolves
# to the singleton.  Use :func:`get_model` for new code.
def __getattr__(name: str) -> object:
    if name == "llm_provider":
        return _get_llm_provider()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
