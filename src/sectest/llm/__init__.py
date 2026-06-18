"""LLM routing through LiteLLM Proxy.

Provides the :class:`LiteLLMModelProvider` that connects the openai-agents
SDK to a LiteLLM Proxy instance for multi-provider routing with automatic
fallback (L-05).

Exports:
    - :class:`LiteLLMModelProvider` — OpenAI-compatible model provider
    - :data:`llm_provider` — singleton provider instance
"""

from sectest.llm.provider import LiteLLMModelProvider, llm_provider

__all__ = [
    "LiteLLMModelProvider",
    "llm_provider",
]
