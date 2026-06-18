"""LLM routing through LiteLLM Proxy.

Provides the :class:`LiteLLMModelProvider` that connects the openai-agents
SDK to a LiteLLM Proxy instance for multi-provider routing with automatic
fallback (L-05).

Exports:
    - :class:`LiteLLMModelProvider` — OpenAI-compatible model provider
    - :class:`LLMConfig` — environment-variable-based configuration
    - :data:`llm_provider` — singleton provider instance (lazy)
    - :func:`get_model` — convenience helper returning a configured Model
"""

from sectest.llm.config import LLMConfig
from sectest.llm.provider import LiteLLMModelProvider, get_model

# ``llm_provider`` is a lazy module-level __getattr__ on provider.py.
# Re-export it here the same way.
import sectest.llm.provider as _provider


def __getattr__(name: str) -> object:
    if name == "llm_provider":
        return _provider._get_llm_provider()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "LLMConfig",
    "LiteLLMModelProvider",
    "get_model",
    "llm_provider",
]
