"""Tests for LiteLLM Proxy configuration.

Validates litellm_config.yaml against the acceptance criteria:
- At least 2 models: gpt-4o (OpenAI) and claude-sonnet-4-20250514 (Anthropic)
- Fallbacks defined with correct primary->secondary mappings
- Retry settings: num_retries=3, request_timeout=120
- API keys use os.environ/ syntax (not hardcoded)
"""

from pathlib import Path

import yaml


CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "litellm_config.yaml"


def load_config() -> dict:
    """Load and parse the LiteLLM config YAML file."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class TestModelList:
    """Validate model_list section."""

    def test_config_has_two_models(self):
        """Config must define at least gpt-4o and claude-sonnet-4-20250514."""
        config = load_config()
        model_list = config.get("model_list", [])
        model_names = [m["model_name"] for m in model_list]

        assert "gpt-4o" in model_names, (
            f"gpt-4o not found in model_list. Models: {model_names}"
        )
        assert "claude-sonnet-4-20250514" in model_names, (
            f"claude-sonnet-4-20250514 not found in model_list. Models: {model_names}"
        )

    def test_config_has_gpt4o_mini(self):
        """Config should also include gpt-4o-mini for fallback chain completion."""
        config = load_config()
        model_list = config.get("model_list", [])
        model_names = [m["model_name"] for m in model_list]

        assert "gpt-4o-mini" in model_names, (
            f"gpt-4o-mini not found in model_list. Models: {model_names}"
        )

    def test_models_use_environ_syntax(self):
        """All model API keys must use os.environ/ syntax — never hardcoded."""
        config = load_config()
        model_list = config.get("model_list", [])

        for model in model_list:
            api_key = model.get("litellm_params", {}).get("api_key", "")
            assert api_key.startswith("os.environ/"), (
                f"Model '{model['model_name']}' has hardcoded api_key: {api_key!r}. "
                f"Must use os.environ/VAR_NAME syntax."
            )


class TestFallbacks:
    """Validate litellm_settings fallbacks."""

    def test_config_has_fallbacks(self):
        """Config must define fallbacks with correct primary->secondary mapping."""
        config = load_config()
        settings = config.get("litellm_settings", {})
        fallbacks = settings.get("fallbacks", [])

        assert len(fallbacks) > 0, "No fallbacks defined in litellm_settings"

        # Build lookup dict from fallback list
        fb_dict: dict[str, list[str]] = {}
        for entry in fallbacks:
            fb_dict.update(entry)

        assert "gpt-4o" in fb_dict, (
            f"gpt-4o fallback not found. Fallbacks: {fb_dict}"
        )
        assert "claude-sonnet-4-20250514" in fb_dict["gpt-4o"], (
            f"Expected claude-sonnet-4-20250514 as fallback for gpt-4o, "
            f"got: {fb_dict.get('gpt-4o')}"
        )

    def test_claude_falls_back_to_gpt4o_mini(self):
        """Claude Sonnet 4 should fall back to gpt-4o-mini."""
        config = load_config()
        settings = config.get("litellm_settings", {})
        fallbacks = settings.get("fallbacks", [])

        fb_dict: dict[str, list[str]] = {}
        for entry in fallbacks:
            fb_dict.update(entry)

        assert "claude-sonnet-4-20250514" in fb_dict, (
            f"claude-sonnet-4-20250514 fallback not found. Fallbacks: {fb_dict}"
        )
        assert "gpt-4o-mini" in fb_dict["claude-sonnet-4-20250514"], (
            f"Expected gpt-4o-mini as fallback for claude-sonnet-4-20250514, "
            f"got: {fb_dict.get('claude-sonnet-4-20250514')}"
        )


class TestRetrySettings:
    """Validate retry/timeout configuration."""

    def test_config_has_retry_settings(self):
        """Config must set num_retries=3 and request_timeout=120."""
        config = load_config()
        settings = config.get("litellm_settings", {})

        assert settings.get("num_retries") == 3, (
            f"Expected num_retries=3, got: {settings.get('num_retries')}"
        )
        assert settings.get("request_timeout") == 120, (
            f"Expected request_timeout=120, got: {settings.get('request_timeout')}"
        )

    def test_config_has_allowed_fails(self):
        """Config must set allowed_fails=5 for model cooldown."""
        config = load_config()
        settings = config.get("litellm_settings", {})

        assert settings.get("allowed_fails") == 5, (
            f"Expected allowed_fails=5, got: {settings.get('allowed_fails')}"
        )


class TestRouterSettings:
    """Validate router_settings — Phase 1 uses basic in-memory mode."""

    def test_router_type_is_basic(self):
        """Phase 1 must use basic router type (in-memory, no DB)."""
        config = load_config()
        router = config.get("router_settings", {})

        assert router.get("type") == "basic", (
            f"Expected router_settings.type='basic' for Phase 1, "
            f"got: {router.get('type')}"
        )


class TestGeneralSettings:
    """Validate general_settings."""

    def test_master_key_uses_environ_syntax(self):
        """Master key must use os.environ/ syntax — never hardcoded."""
        config = load_config()
        general = config.get("general_settings", {})

        master_key = general.get("master_key", "")
        assert master_key.startswith("os.environ/"), (
            f"master_key must use os.environ/ syntax, got: {master_key!r}"
        )
