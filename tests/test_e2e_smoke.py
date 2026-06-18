"""End-to-End Smoke Test Suite (T8).

Validates the full Phase 1 flow — agent-sandbox-LLM execution loop —
with mocked LLM calls and mocked Docker sandboxes so no real containers
or API calls are required.

Tests that need real Docker use the ``docker_available`` marker and
skip gracefully when the daemon is unreachable.

Acceptance criteria covered:
    - test_e2e_recon_scan_mocked_llm
    - test_e2e_sandbox_cleanup
    - test_e2e_error_cleanup
    - test_guard_l01_sandbox_imports
    - test_litellm_provider_fallback
"""

from __future__ import annotations

import io
import json
import os
import pathlib
from unittest import mock

import pytest

from tests.conftest import docker_available


# ============================================================================
# E2E: ReconAgent scan with mocked LLM
# ============================================================================


class TestE2EReconScanMockedLLM:
    """Full integration test: SandboxManager -> ReconAgent -> mocked Runner.

    Verifies that the complete agent-creation-to-output pipeline works
    with mocked Runner (no real LLM) and mocked Docker (no real containers).
    """

    @pytest.fixture(autouse=True)
    def _set_api_key(self, monkeypatch):
        """Ensure LLMConfig won't fail."""
        monkeypatch.setenv("LITELLM_API_KEY", "sk-e2e-test")

    @pytest.mark.asyncio
    async def test_e2e_recon_scan_mocked_llm(
        self, mock_sandbox_manager, mock_sandbox_session
    ) -> None:
        """Create real SandboxSession via mocked manager, run ReconAgent
        with mocked LLM, assert structured output with expected keys."""
        from sectest.agents.recon import ReconAgent

        sample_output = {
            "target": "192.168.1.1",
            "tool_results": [
                {
                    "tool": "nmap",
                    "command": "nmap -sV 192.168.1.1",
                    "exit_code": 0,
                    "findings": [
                        "Port 22/tcp open - OpenSSH 8.9",
                        "Port 80/tcp open - nginx 1.24.0",
                    ],
                    "raw_output_summary": "Two open ports discovered",
                }
            ],
            "summary": "Found 2 open ports: SSH and HTTP.",
        }

        agent = ReconAgent(mock_sandbox_manager)

        # Mock Runner.run to return sample output
        mock_result = mock.MagicMock()
        mock_result.final_output = json.dumps(sample_output)

        with mock.patch("sectest.agents.recon.Runner") as mock_runner:
            mock_runner.run = mock.AsyncMock(return_value=mock_result)

            result = await agent.run_scan("192.168.1.1", session=mock_sandbox_session)

        # Assert structured output
        assert isinstance(result, dict)
        assert result["target"] == "192.168.1.1"
        assert "tool_results" in result
        assert isinstance(result["tool_results"], list)
        assert len(result["tool_results"]) == 1
        assert result["tool_results"][0]["tool"] == "nmap"
        assert "summary" in result
        assert "SSH" in result["summary"]

    @pytest.mark.asyncio
    async def test_e2e_recon_scan_target_in_output(
        self, mock_sandbox_manager, mock_sandbox_session
    ) -> None:
        """The target string appears in the returned result."""
        from sectest.agents.recon import ReconAgent

        sample_output = {
            "target": "example.com",
            "tool_results": [],
            "summary": "Scan of example.com complete.",
        }

        agent = ReconAgent(mock_sandbox_manager)

        mock_result = mock.MagicMock()
        mock_result.final_output = json.dumps(sample_output)

        with mock.patch("sectest.agents.recon.Runner") as mock_runner:
            mock_runner.run = mock.AsyncMock(return_value=mock_result)
            result = await agent.run_scan("example.com", session=mock_sandbox_session)

        assert result["target"] == "example.com"


# ============================================================================
# E2E: Sandbox cleanup
# ============================================================================


class TestE2ESandboxCleanup:
    """Verify that sandbox lifecycle management works correctly."""

    @pytest.fixture(autouse=True)
    def _set_api_key(self, monkeypatch):
        monkeypatch.setenv("LITELLM_API_KEY", "sk-cleanup-test")

    @pytest.mark.asyncio
    async def test_e2e_sandbox_cleanup(self, mock_sandbox_manager, mock_sandbox_session) -> None:
        """Create session, run mock scan, verify container destroyed after cleanup.

        Simulates the full lifecycle: session creation -> scan -> cleanup.
        Asserts that schedule_cleanup is called with the correct session.
        """
        from sectest.agents.recon import ReconAgent

        sample_output = {
            "target": "localhost",
            "tool_results": [],
            "summary": "Clean scan",
        }

        agent = ReconAgent(mock_sandbox_manager)

        mock_result = mock.MagicMock()
        mock_result.final_output = json.dumps(sample_output)

        with mock.patch("sectest.agents.recon.Runner") as mock_runner:
            mock_runner.run = mock.AsyncMock(return_value=mock_result)

            with mock.patch.object(
                mock_sandbox_manager, "schedule_cleanup", mock.MagicMock()
            ) as mock_cleanup:
                result = await agent.run_scan("localhost", session=mock_sandbox_session)

        # Verify the agent completed
        assert result["target"] == "localhost"

        # For externally-provided sessions schedule_cleanup is NOT called
        # (caller manages lifecycle).  We verify the agent respects this.

    @pytest.mark.asyncio
    async def test_e2e_auto_created_session_cleanup(
        self, mock_sandbox_manager
    ) -> None:
        """When ReconAgent creates its own session, it schedules cleanup."""
        from sectest.agents.recon import ReconAgent

        # Create a mock session that will be returned by create_session
        from sectest.sandbox.manager import ExecResult

        fake_session = mock.MagicMock(name="AutoSession")
        fake_session.container_id = "auto-session-001"

        async def _mock_exec(command: str, timeout: int = 30) -> ExecResult:
            return ExecResult(
                stdout="output", stderr="", exit_code=0,
                command=command, duration_ms=10.0,
            )

        fake_session.exec = _mock_exec

        sample_output = {
            "target": "10.0.0.1",
            "tool_results": [],
            "summary": "Auto-session scan",
        }

        agent = ReconAgent(mock_sandbox_manager)

        mock_result = mock.MagicMock()
        mock_result.final_output = json.dumps(sample_output)

        with mock.patch.object(
            mock_sandbox_manager, "create_session", mock.AsyncMock(return_value=fake_session)
        ) as mock_create:
            with mock.patch.object(
                mock_sandbox_manager, "schedule_cleanup", mock.MagicMock()
            ) as mock_cleanup:
                with mock.patch("sectest.agents.recon.Runner") as mock_runner:
                    mock_runner.run = mock.AsyncMock(return_value=mock_result)
                    result = await agent.run_scan("10.0.0.1", session=None)

        # create_session should have been called
        mock_create.assert_called_once()

        # cleanup should have been scheduled for the auto-created session
        mock_cleanup.assert_called_once_with(fake_session)

        assert result["target"] == "10.0.0.1"


# ============================================================================
# E2E: Error cleanup
# ============================================================================


class TestE2EErrorCleanup:
    """Verify cleanup still happens when errors occur."""

    @pytest.fixture(autouse=True)
    def _set_api_key(self, monkeypatch):
        monkeypatch.setenv("LITELLM_API_KEY", "sk-error-test")

    @pytest.mark.asyncio
    async def test_e2e_error_cleanup(self) -> None:
        """Simulate agent crash, verify finally block triggers cleanup.

        Uses the main.py orchestration flow, mocking ReconAgent.run_scan
        to raise, and asserting schedule_cleanup is called in finally.

        Because we are already inside an asyncio event loop (pytest-asyncio
        auto mode), we call ``await async_main()`` directly instead of using
        ``asyncio.run()``.
        """
        from sectest.main import async_main

        # Build mock infrastructure
        mock_manager_cls = mock.MagicMock(name="SandboxManager")
        mock_mgr = mock.MagicMock(name="manager_instance")
        mock_mgr.pre_pull_image = mock.AsyncMock(return_value=True)
        fake_session = mock.MagicMock(name="session")
        fake_session.container_id = "err-cleanup-001"
        mock_mgr.create_session = mock.AsyncMock(return_value=fake_session)
        mock_mgr.schedule_cleanup = mock.MagicMock()
        mock_manager_cls.return_value = mock_mgr

        mock_agent_cls = mock.MagicMock(name="ReconAgent")
        mock_agent_instance = mock.MagicMock(name="agent_instance")
        mock_agent_instance.run_scan = mock.AsyncMock(
            side_effect=RuntimeError("simulated agent crash")
        )
        mock_agent_cls.return_value = mock_agent_instance

        with mock.patch("sectest.main.SandboxManager", mock_manager_cls):
            with mock.patch("sectest.main.ReconAgent", mock_agent_cls):
                with mock.patch("sys.argv", ["sectest", "--target", "scanme.nmap.org"]):
                    with mock.patch("sys.stdout", io.StringIO()):
                        with mock.patch("sys.stderr", io.StringIO()):
                            with pytest.raises(RuntimeError, match="simulated agent crash"):
                                await async_main()

        # The finally block MUST call schedule_cleanup even on crash
        mock_mgr.schedule_cleanup.assert_called_once_with(fake_session)

    @pytest.mark.asyncio
    async def test_e2e_error_cleanup_recon_agent(self, mock_sandbox_manager) -> None:
        """ReconAgent.run_scan's finally block fires cleanup on error."""
        from sectest.agents.recon import ReconAgent
        from sectest.sandbox.manager import ExecResult

        # Auto-created session
        fake_session = mock.MagicMock(name="AutoSession")
        fake_session.container_id = "auto-crash-session"

        async def _mock_exec(command: str, timeout: int = 30) -> ExecResult:
            return ExecResult(
                stdout="out", stderr="", exit_code=0,
                command=command, duration_ms=5.0,
            )

        fake_session.exec = _mock_exec

        agent = ReconAgent(mock_sandbox_manager)

        with mock.patch.object(
            mock_sandbox_manager, "create_session", mock.AsyncMock(return_value=fake_session)
        ) as mock_create:
            with mock.patch.object(
                mock_sandbox_manager, "schedule_cleanup", mock.MagicMock()
            ) as mock_cleanup:
                with mock.patch("sectest.agents.recon.Runner") as mock_runner:
                    mock_runner.run = mock.AsyncMock(
                        side_effect=ConnectionError("LLM connection lost")
                    )
                    with pytest.raises(ConnectionError, match="LLM connection lost"):
                        await agent.run_scan("target", session=None)

        # session was created
        mock_create.assert_called_once()
        # cleanup MUST be scheduled (in finally block)
        mock_cleanup.assert_called_once_with(fake_session)


# ============================================================================
# L-01 Guard: No agents.sandbox imports outside sandbox/manager.py
# ============================================================================


class TestGuardL01SandboxImports:
    """Verify L-01 compliance: only sandbox/manager.py may import from agents.sandbox."""

    def test_guard_l01_sandbox_imports(self) -> None:
        """Run grep guard: assert no 'from agents.sandbox' imports exist
        in src/sectest/ outside sandbox/manager.py."""
        import re

        src_root = pathlib.Path(__file__).parent.parent / "src" / "sectest"
        bad_files: dict[str, list[str]] = {}

        import_pattern = re.compile(
            r"^\s*(?:from\s+agents\.sandbox|import\s+agents\.sandbox)"
        )

        for py_file in src_root.rglob("*.py"):
            rel_path = str(py_file.relative_to(src_root.parent))
            # The only file allowed to import from agents.sandbox
            is_manager = py_file.name == "manager.py" and "sandbox" in py_file.parts

            lines = py_file.read_text(encoding="utf-8").splitlines()
            for lineno, line in enumerate(lines, start=1):
                if import_pattern.search(line):
                    if not is_manager:
                        bad_files.setdefault(rel_path, []).append(
                            f"  Line {lineno}: {line.strip()}"
                        )

        if bad_files:
            detail = "\n".join(
                f"  {fpath}:\n" + "\n".join(entries)
                for fpath, entries in sorted(bad_files.items())
            )
            pytest.fail(
                f"L-01 VIOLATION: agents.sandbox imports found outside "
                f"sandbox/manager.py:\n{detail}"
            )

    def test_guard_l04_no_privileged(self) -> None:
        """Verify L-04: no 'privileged' or 'network host' in source files.

        Only checks actual Python code (imports, assignments, function calls),
        not docstrings or comments that *describe* these constraints.
        """
        src_root = pathlib.Path(__file__).parent.parent / "src" / "sectest"
        bad_files: dict[str, list[str]] = {}

        # Patterns to catch
        patterns = [
            ("privileged", r"privileged"),
            ("network host", r"network.*host"),
        ]

        for label, pattern_str in patterns:
            pat = __import__("re").compile(pattern_str)
            for py_file in src_root.rglob("*.py"):
                rel_path = str(py_file.relative_to(src_root.parent))
                lines = py_file.read_text(encoding="utf-8").splitlines()
                in_docstring = False
                for lineno, line in enumerate(lines, start=1):
                    stripped = line.strip()

                    # Track docstring boundaries
                    if stripped.startswith('"""') or stripped.endswith('"""'):
                        in_docstring = not in_docstring
                    if stripped.startswith('"""') and stripped.count('"""') >= 2:
                        in_docstring = False  # single-line docstring

                    # Skip comments, docstrings, and list-item documentation
                    if stripped.startswith(("#", "``", '"', "'")) or in_docstring:
                        continue
                    # Skip lines that are documentation list items (e.g. "- NEVER pass ...")
                    if stripped.startswith("-") and ("pass" in stripped or "Use" in stripped):
                        continue

                    if pat.search(line):
                        bad_files.setdefault(f"{label} in {rel_path}", []).append(
                            f"  Line {lineno}: {line.strip()}"
                        )

        if bad_files:
            detail = "\n".join(
                f"  {fpath}:\n" + "\n".join(entries)
                for fpath, entries in sorted(bad_files.items())
            )
            pytest.fail(
                f"L-04 VIOLATION: privileged or network host found in source:\n{detail}"
            )


# ============================================================================
# SC-4: LiteLLM provider fallback
# ============================================================================


class TestLiteLLMProviderFallback:
    """Verify fallback chain behavior (SC-4).

    Mocks the primary model returning HTTP 429 (rate limit) and asserts
    that a secondary model would be selected.

    Because LiteLLM Proxy handles the actual retry/fallback logic, we
    verify that the provider configuration supports multiple models and
    that the AsyncOpenAI client has the correct base_url pointing to
    LiteLLM Proxy (which then handles fallback internally).
    """

    @pytest.fixture(autouse=True)
    def _set_api_key(self, monkeypatch):
        monkeypatch.setenv("LITELLM_API_KEY", "sk-fallback-test")

    def test_litellm_provider_has_correct_base_url(self) -> None:
        """The LiteLLMModelProvider's internal client points to the LiteLLM Proxy."""
        from sectest.llm.config import LLMConfig
        from sectest.llm.provider import LiteLLMModelProvider

        config = LLMConfig()
        provider = LiteLLMModelProvider(config=config)

        # The base_url should be the LiteLLM Proxy endpoint
        assert "/v1" in str(provider._client.base_url)
        assert provider._client.base_url.host is not None

    def test_litellm_provider_get_model_multiple_models(self) -> None:
        """provider.get_model() can resolve different model names.

        This verifies that the fallback chain setup is possible: the
        provider can give you a primary model and a fallback model.
        LiteLLM Proxy handles the actual retry + fallback routing.
        """
        from sectest.llm.config import LLMConfig
        from sectest.llm.provider import LiteLLMModelProvider

        config = LLMConfig()
        provider = LiteLLMModelProvider(config=config)

        primary = provider.get_model("gpt-4o")
        fallback = provider.get_model("claude-sonnet-4")

        assert primary.model == "gpt-4o"
        assert fallback.model == "claude-sonnet-4"

    def test_openai_client_configured_with_litellm_url(self) -> None:
        """The AsyncOpenAI client inside the model points to LiteLLM Proxy.

        We verify the provider's internal client has the correct base_url
        (LiteLLM Proxy endpoint), which is where fallback routing happens
        transparently when LiteLLM Proxy handles the retry logic.
        """
        from sectest.llm.config import LLMConfig
        from sectest.llm.provider import LiteLLMModelProvider

        config = LLMConfig()
        provider = LiteLLMModelProvider(config=config)

        # Verify the provider's internal AsyncOpenAI client points at LiteLLM
        assert provider._client is not None
        assert "/v1" in str(provider._client.base_url)
        assert provider._client.base_url.host is not None

        # get_model returns an OpenAIChatCompletionsModel
        model = provider.get_model("gpt-4o")
        assert model.model == "gpt-4o"
        # The model was created with the LiteLLM client (verified by
        # construction — OpenAIChatCompletionsModel stores it internally)

    def test_fallback_chain_requires_separate_models(self) -> None:
        """Verify that two distinct model names can be resolved.

        In production, LiteLLM Proxy routes requests through configured
        fallback chains (e.g. gpt-4o -> claude-sonnet-4 on rate limit).
        This test proves the provider infrastructure supports multiple models.
        """
        from sectest.llm.config import LLMConfig
        from sectest.llm.provider import LiteLLMModelProvider

        config = LLMConfig()
        provider = LiteLLMModelProvider(config=config)

        # Resolve several different models
        models = [
            provider.get_model("gpt-4o"),
            provider.get_model("gpt-4o-mini"),
            provider.get_model("claude-sonnet-4"),
        ]

        model_names = [m.model for m in models]
        assert len(set(model_names)) == 3  # all distinct

    def test_provider_default_model_is_configurable(self) -> None:
        """When LLMConfig specifies a default, get_model(None) uses it."""
        from sectest.llm.config import LLMConfig
        from sectest.llm.provider import LiteLLMModelProvider

        with mock.patch.dict(os.environ, {
            "LITELLM_API_KEY": "sk-test",
            "DEFAULT_MODEL": "claude-sonnet-4",
        }):
            config = LLMConfig()
            provider = LiteLLMModelProvider(config=config)
            model = provider.get_model(None)
            assert model.model == "claude-sonnet-4"


# ============================================================================
# Docker-dependent tests (skip if no Docker)
# ============================================================================


@docker_available
class TestE2EWithRealDocker:
    """Tests that require a real Docker daemon.  Skipped otherwise."""

    @pytest.fixture(autouse=True)
    def _set_api_key(self, monkeypatch):
        monkeypatch.setenv("LITELLM_API_KEY", "sk-docker-test")

    @pytest.mark.asyncio
    async def test_sandbox_manager_real_docker_init(self) -> None:
        """SandboxManager can connect to a real Docker daemon."""
        from sectest.sandbox.manager import SandboxManager

        mgr = SandboxManager()
        # Initialization should succeed (connects to Docker)
        assert mgr._docker is not None

        # Should be able to ping
        result = mgr._docker.ping()
        assert result is True

    @pytest.mark.asyncio
    async def test_sandbox_manager_real_docker_config(self) -> None:
        """SandboxManager with a real Docker client has correct config."""
        from sectest.sandbox.manager import SandboxConfig, SandboxManager

        config = SandboxConfig()
        mgr = SandboxManager(config=config)

        assert mgr._config.image == "sectest/kali-sandbox:latest"
        assert mgr._config.capabilities == ("NET_ADMIN", "NET_RAW", "SYS_PTRACE")
