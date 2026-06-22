"""LLM configuration from environment variables.

Two modes — auto-detected from the environment:

**Direct mode** (no external proxy needed)::

    $env:LLM_MODEL="deepseek/deepseek-v4-flash"
    $env:LLM_API_KEY="sk-..."
    $env:LLM_API_BASE="https://api.deepseek.com/v1"

**LiteLLM Proxy mode** (multi-provider fallback, cost tracking)::

    $env:LITELLM_BASE_URL="http://localhost:4000/v1"
    $env:LITELLM_API_KEY="sk-lite"

    # Also start the proxy first:
    #   docker compose up litellm -d

Detection rule: when ``LLM_API_BASE`` is set, direct mode is used and
``LITELLM_*`` variables are ignored.  Otherwise the provider falls back
to the LiteLLM Proxy configuration.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class LLMConfig:
    """LLM connection parameters.

    Priority: ``LLM_API_BASE`` > ``LITELLM_BASE_URL``.

    ==================== ========== ===========================================
    Variable             Required   Description
    ==================== ========== ===========================================
    ``LLM_MODEL``        No         Model id (direct mode). Default ``gpt-4o``
    ``LLM_API_KEY``      Yes*       API key for the LLM provider
    ``LLM_API_BASE``     No         Base URL for OpenAI-compatible API endpoint
    ``LITELLM_BASE_URL`` No         LiteLLM Proxy URL (proxy mode fallback)
    ``LITELLM_API_KEY``  Yes*       Master key for LiteLLM Proxy
    ``DEFAULT_MODEL``    No         Legacy alias for ``LLM_MODEL``
    ==================== ========== ===========================================

    * At least one key source must be provided; see :meth:`_require_key`.
    """

    model: str = field(
        default_factory=lambda: os.getenv(
            "LLM_MODEL",
            os.getenv("DEFAULT_MODEL", "gpt-4o"),
        )
    )
    api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))
    base_url: str = field(default_factory=lambda: os.getenv("LLM_API_BASE", ""))

    # LiteLLM Proxy fallback values (only used in proxy mode)
    litellm_api_key: str = field(
        default_factory=lambda: os.getenv("LITELLM_API_KEY", "")
    )
    litellm_base_url: str = field(
        default_factory=lambda: os.getenv(
            "LITELLM_BASE_URL", "http://localhost:4000/v1"
        )
    )

    # -- derived properties ---------------------------------------------------

    @property
    def is_direct_mode(self) -> bool:
        """True when LLM_API_BASE is set, indicating direct-to-provider mode."""
        return bool(self.base_url)

    @property
    def effective_base_url(self) -> str:
        """Return the URL the provider should connect to."""
        if self.base_url:
            return self.base_url
        return self.litellm_base_url

    @property
    def effective_api_key(self) -> str:
        """Return the API key the provider should use."""
        if self.is_direct_mode:
            return self.api_key
        return self.litellm_api_key

    # -- validation -----------------------------------------------------------

    def __post_init__(self) -> None:
        self._require_key()

    def _require_key(self) -> None:
        """Ensure at least one key source is configured."""
        if self.is_direct_mode:
            if not self.api_key:
                raise ValueError(
                    "LLM_API_KEY is required in direct mode "
                    "(LLM_API_BASE is set)."
                )
        else:
            if not self.litellm_api_key:
                raise ValueError(
                    "LITELLM_API_KEY environment variable is required. "
                    "Set it to your LiteLLM Proxy master key, "
                    "or switch to direct mode by setting "
                    "LLM_API_BASE and LLM_API_KEY."
                )
