"""LiteLLM ModelProvider for openai-agents SDK (T5 — to be fully implemented).

Connects the openai-agents SDK to LiteLLM Proxy for multi-provider routing
with automatic fallback (L-05).
"""

from __future__ import annotations

from agents import ModelProvider


class LiteLLMModelProvider(ModelProvider):
    """Model provider that routes LLM calls through LiteLLM Proxy."""

    def get_model(self, model_name: str | None) -> object:
        """Return an OpenAIChatCompletionsModel pointed at the LiteLLM Proxy."""
        raise NotImplementedError("LiteLLMModelProvider.get_model() — implement in T5")


# Singleton instance for use across the platform
llm_provider = LiteLLMModelProvider()
