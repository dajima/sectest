"""LLM configuration from environment variables.

Provides :class:`LLMConfig` that reads LiteLLM Proxy connection
parameters from environment variables with sensible defaults.

Environment variables:
    ``LITELLM_BASE_URL`` — LiteLLM Proxy base URL (default ``http://localhost:4000/v1``)
    ``LITELLM_API_KEY`` — LiteLLM master key (required)
    ``DEFAULT_MODEL`` — default model name (default ``gpt-4o``)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class LLMConfig:
    """Configuration for connecting to the LiteLLM Proxy.

    Reads from environment variables at instantiation time so that
    callers can mutate the env (e.g. in tests) and get a fresh config.

    Raises:
        ValueError: If ``LITELLM_API_KEY`` is not set.
    """

    base_url: str = field(
        default_factory=lambda: os.getenv(
            "LITELLM_BASE_URL", "http://localhost:4000/v1"
        )
    )
    api_key: str = field(
        default_factory=lambda: os.getenv("LITELLM_API_KEY", "")
    )
    default_model: str = field(
        default_factory=lambda: os.getenv("DEFAULT_MODEL", "gpt-4o")
    )

    def __post_init__(self) -> None:
        if not self.api_key:
            raise ValueError(
                "LITELLM_API_KEY environment variable is required. "
                "Set it to your LiteLLM Proxy master key (default: sk-sectest-lite)."
            )
