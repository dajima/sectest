"""Unit tests for ReconAgent (T6).

Tests verify:
    - ReconAgent.__init__ accepts SandboxManager and optional model
    - run_scan creates an Agent, runs via Runner, returns structured dict
    - shell tool delegates to session.exec()
    - _parse_output handles valid JSON and raw text fallback
    - No imports from agents.sandbox in agent code
    - Session auto-creation when session=None
    - Session lifecycle management (cleanup scheduling)

All external calls (LLM Runner, sandbox exec) are mocked — no real
containers or API calls are made.
"""

from __future__ import annotations

import json
import re
from unittest import mock

import pytest


# ---------------------------------------------------------------------------
# Helper: minimal mock ExecResult
# ---------------------------------------------------------------------------


def _make_exec_result(
    stdout: str = "nmap output",
    stderr: str = "",
    exit_code: int = 0,
    command: str = "",
    duration_ms: float = 100.0,
) -> "ExecResult":
    """Create a mock ExecResult compatible with SandboxSession.exec() return."""
    from sectest.sandbox.manager import ExecResult

    return ExecResult(
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        command=command,
        duration_ms=duration_ms,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sandbox_manager() -> "SandboxManager":
    """Return a SandboxManager with a mocked Docker client."""
    with mock.patch("docker.from_env") as mock_from_env:
        mock_from_env.return_value = mock.MagicMock()
        from sectest.sandbox.manager import SandboxManager

        return SandboxManager()


@pytest.fixture
def mock_session() -> mock.MagicMock:
    """Return a mocked SandboxSession with async exec()."""
    session = mock.MagicMock()

    # exec() is async — return a coroutine
    async def _mock_exec(command: str, timeout: int = 30) -> "ExecResult":
        return _make_exec_result(command=command)

    session.exec = _mock_exec
    session.container_id = "mock-container-123"
    return session


@pytest.fixture
def sample_agent_output() -> dict:
    """Return a sample valid agent JSON output."""
    return {
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


# ---------------------------------------------------------------------------
# Tests: ReconAgent.__init__
# ---------------------------------------------------------------------------


class TestReconAgentInit:
    def test_init_accepts_sandbox_manager(self, sandbox_manager: "SandboxManager") -> None:
        """ReconAgent.__init__ stores sandbox_manager and model."""
        from sectest.agents.recon import ReconAgent

        agent = ReconAgent(sandbox_manager)
        assert agent._sandbox is sandbox_manager
        assert agent._model is None  # default — uses LiteLLM default

    def test_init_accepts_custom_model(self, sandbox_manager: "SandboxManager") -> None:
        """ReconAgent.__init__ accepts an optional model string."""
        from sectest.agents.recon import ReconAgent

        agent = ReconAgent(sandbox_manager, model="claude-sonnet-4")
        assert agent._model == "claude-sonnet-4"

    def test_init_model_defaults_to_none(self, sandbox_manager: "SandboxManager") -> None:
        """When model is not provided, it defaults to None (use LiteLLM default)."""
        from sectest.agents.recon import ReconAgent

        agent = ReconAgent(sandbox_manager)
        assert agent._model is None


# ---------------------------------------------------------------------------
# Tests: ReconAgent.run_scan
# ---------------------------------------------------------------------------


class TestRunScan:
    @pytest.mark.asyncio
    async def test_run_scan_creates_agent_and_runs(
        self,
        sandbox_manager: "SandboxManager",
        mock_session: mock.MagicMock,
        sample_agent_output: dict,
    ) -> None:
        """run_scan creates an Agent, runs via Runner, and returns a dict."""
        from sectest.agents.recon import ReconAgent

        agent = ReconAgent(sandbox_manager)

        # Mock Runner.run to return a mock result with our sample output
        mock_result = mock.MagicMock()
        mock_result.final_output = json.dumps(sample_agent_output)

        with mock.patch("sectest.agents.recon.Runner") as mock_runner:
            mock_runner.run = mock.AsyncMock(return_value=mock_result)

            result = await agent.run_scan("192.168.1.1", session=mock_session)

        assert isinstance(result, dict)
        assert mock_runner.run.called

    @pytest.mark.asyncio
    async def test_run_scan_returns_structured_dict(
        self,
        sandbox_manager: "SandboxManager",
        mock_session: mock.MagicMock,
        sample_agent_output: dict,
    ) -> None:
        """run_scan returns a dict with target, tool_results, summary keys."""
        from sectest.agents.recon import ReconAgent

        agent = ReconAgent(sandbox_manager)

        mock_result = mock.MagicMock()
        mock_result.final_output = json.dumps(sample_agent_output)

        with mock.patch("sectest.agents.recon.Runner") as mock_runner:
            mock_runner.run = mock.AsyncMock(return_value=mock_result)

            result = await agent.run_scan("192.168.1.1", session=mock_session)

        assert result["target"] == "192.168.1.1"
        assert isinstance(result["tool_results"], list)
        assert isinstance(result["summary"], str)
        assert len(result["tool_results"]) == 1
        assert result["tool_results"][0]["tool"] == "nmap"

    @pytest.mark.asyncio
    async def test_run_scan_passes_target_to_agent_instructions(
        self,
        sandbox_manager: "SandboxManager",
        mock_session: mock.MagicMock,
    ) -> None:
        """run_scan includes the target in the Agent instructions."""
        from sectest.agents.recon import ReconAgent

        agent = ReconAgent(sandbox_manager)

        mock_result = mock.MagicMock()
        mock_result.final_output = json.dumps({"target": "10.0.0.1", "tool_results": [], "summary": "ok"})

        with mock.patch("sectest.agents.recon.Runner") as mock_runner:
            mock_runner.run = mock.AsyncMock(return_value=mock_result)

            # We need to capture the Agent that was created to inspect its instructions
            with mock.patch("sectest.agents.recon.Agent") as mock_agent_cls:
                mock_agent_instance = mock.MagicMock()
                mock_agent_cls.return_value = mock_agent_instance

                await agent.run_scan("10.0.0.1", session=mock_session)

            # Check that Agent was constructed with the target in instructions
            call_kwargs = mock_agent_cls.call_args.kwargs
            assert "10.0.0.1" in call_kwargs["instructions"]

    @pytest.mark.asyncio
    async def test_run_scan_agent_has_shell_tool(
        self,
        sandbox_manager: "SandboxManager",
        mock_session: mock.MagicMock,
    ) -> None:
        """The Agent is created with a shell function_tool in its tools list."""
        from sectest.agents.recon import ReconAgent

        agent = ReconAgent(sandbox_manager)

        mock_result = mock.MagicMock()
        mock_result.final_output = json.dumps({"target": "t", "tool_results": [], "summary": "s"})

        with mock.patch("sectest.agents.recon.Runner") as mock_runner:
            mock_runner.run = mock.AsyncMock(return_value=mock_result)

            with mock.patch("sectest.agents.recon.Agent") as mock_agent_cls:
                mock_agent_instance = mock.MagicMock()
                mock_agent_cls.return_value = mock_agent_instance

                await agent.run_scan("example.com", session=mock_session)

            call_kwargs = mock_agent_cls.call_args.kwargs
            assert "tools" in call_kwargs
            assert len(call_kwargs["tools"]) == 1
            assert call_kwargs["name"] == "ReconAgent"


# ---------------------------------------------------------------------------
# Tests: shell tool uses session.exec
# ---------------------------------------------------------------------------


class TestShellTool:
    def test_create_shell_tool_returns_function_tool(
        self,
        sandbox_manager: "SandboxManager",
        mock_session: mock.MagicMock,
    ) -> None:
        """_create_shell_tool returns a function_tool-decorated function."""
        from sectest.agents.recon import ReconAgent

        agent = ReconAgent(sandbox_manager)
        tool = agent._create_shell_tool(mock_session)

        # A function_tool-decorated function has a name attribute
        assert hasattr(tool, "name")
        assert tool.name == "shell"

    @pytest.mark.asyncio
    async def test_shell_tool_calls_session_exec(
        self,
        sandbox_manager: "SandboxManager",
        mock_session: mock.MagicMock,
    ) -> None:
        """The shell tool calls session.exec(command, timeout=300)."""
        from sectest.agents.recon import ReconAgent

        agent = ReconAgent(sandbox_manager)
        tool = agent._create_shell_tool(mock_session)

        # Invoke the actual function wrapped by the tool
        # function_tool wraps it; the underlying function is tool.on_invoke_tool
        from agents import FunctionTool

        if isinstance(tool, FunctionTool):
            result_str = await tool.on_invoke_tool(
                mock.MagicMock(),  # RunContext
                '{"command": "nmap --version"}',
            )
        else:
            # Fallback: call the underlying coroutine directly
            result_str = await tool.on_invoke_tool(
                mock.MagicMock(),
                '{"command": "nmap --version"}',
            )

        assert "EXIT_CODE" in result_str
        assert "STDOUT" in result_str
        assert "nmap output" in result_str

    @pytest.mark.asyncio
    async def test_shell_tool_formats_output_correctly(
        self,
        sandbox_manager: "SandboxManager",
        mock_session: mock.MagicMock,
    ) -> None:
        """Shell tool returns formatted output with exit code, stdout, stderr."""
        from sectest.agents.recon import ReconAgent

        agent = ReconAgent(sandbox_manager)
        tool = agent._create_shell_tool(mock_session)

        from agents import FunctionTool

        if isinstance(tool, FunctionTool):
            result_str = await tool.on_invoke_tool(
                mock.MagicMock(),
                '{"command": "nmap -sV 10.0.0.1"}',
            )
        else:
            result_str = await tool.on_invoke_tool(
                mock.MagicMock(),
                '{"command": "nmap -sV 10.0.0.1"}',
            )

        # Verify format
        assert "EXIT_CODE: 0" in result_str
        assert "STDOUT:" in result_str
        assert "STDERR:" in result_str
        assert "DURATION_MS:" in result_str


# ---------------------------------------------------------------------------
# Tests: _parse_output
# ---------------------------------------------------------------------------


class TestParseOutput:
    def test_parse_output_valid_json(
        self,
        sandbox_manager: "SandboxManager",
        sample_agent_output: dict,
    ) -> None:
        """_parse_output parses valid JSON correctly."""
        from sectest.agents.recon import ReconAgent

        agent = ReconAgent(sandbox_manager)
        raw = json.dumps(sample_agent_output)
        result = agent._parse_output(raw)

        assert result == sample_agent_output
        assert result["target"] == "192.168.1.1"

    def test_parse_output_raw_text(
        self,
        sandbox_manager: "SandboxManager",
    ) -> None:
        """_parse_output returns raw_output dict for non-JSON text."""
        from sectest.agents.recon import ReconAgent

        agent = ReconAgent(sandbox_manager)
        raw = "This is not JSON at all. Just some text output."
        result = agent._parse_output(raw)

        assert "raw_output" in result
        assert result["raw_output"] == raw

    def test_parse_output_empty_string(
        self,
        sandbox_manager: "SandboxManager",
    ) -> None:
        """_parse_output handles empty string gracefully."""
        from sectest.agents.recon import ReconAgent

        agent = ReconAgent(sandbox_manager)
        result = agent._parse_output("")

        assert "raw_output" in result
        assert result["raw_output"] == ""

    def test_parse_output_json_in_markdown_fences(
        self,
        sandbox_manager: "SandboxManager",
        sample_agent_output: dict,
    ) -> None:
        """_parse_output extracts JSON from markdown code fences."""
        from sectest.agents.recon import ReconAgent

        agent = ReconAgent(sandbox_manager)

        raw = "```json\n" + json.dumps(sample_agent_output) + "\n```"
        result = agent._parse_output(raw)

        assert result["target"] == "192.168.1.1"
        assert isinstance(result["tool_results"], list)

    def test_parse_output_json_without_language_tag(
        self,
        sandbox_manager: "SandboxManager",
        sample_agent_output: dict,
    ) -> None:
        """_parse_output extracts JSON from fences without a language tag."""
        from sectest.agents.recon import ReconAgent

        agent = ReconAgent(sandbox_manager)

        raw = "```\n" + json.dumps(sample_agent_output) + "\n```"
        result = agent._parse_output(raw)

        assert result["target"] == "192.168.1.1"

    def test_parse_output_partial_json(
        self,
        sandbox_manager: "SandboxManager",
    ) -> None:
        """_parse_output falls back to raw_output for invalid JSON."""
        from sectest.agents.recon import ReconAgent

        agent = ReconAgent(sandbox_manager)
        raw = '{"target": "x", "tool_results": [}'
        result = agent._parse_output(raw)

        assert "raw_output" in result

    def test_parse_output_json_with_surrounding_text(
        self,
        sandbox_manager: "SandboxManager",
    ) -> None:
        """_parse_output falls back when JSON is mixed with other text."""
        from sectest.agents.recon import ReconAgent

        agent = ReconAgent(sandbox_manager)
        raw = "Here are the results:\n" + json.dumps({"target": "x", "tool_results": [], "summary": "ok"})
        result = agent._parse_output(raw)

        # This should fallback because the entire string is not valid JSON
        assert "raw_output" in result


# ---------------------------------------------------------------------------
# Tests: session lifecycle (auto-create / cleanup)
# ---------------------------------------------------------------------------


class TestSessionLifecycle:
    @pytest.mark.asyncio
    async def test_run_scan_uses_provided_session(
        self,
        sandbox_manager: "SandboxManager",
        mock_session: mock.MagicMock,
    ) -> None:
        """When a session is provided, run_scan uses it (no create_session call)."""
        from sectest.agents.recon import ReconAgent

        agent = ReconAgent(sandbox_manager)

        mock_result = mock.MagicMock()
        mock_result.final_output = json.dumps({"target": "t", "tool_results": [], "summary": "s"})

        with mock.patch("sectest.agents.recon.Runner") as mock_runner:
            mock_runner.run = mock.AsyncMock(return_value=mock_result)

            # Spy on create_session
            with mock.patch.object(
                sandbox_manager, "create_session", wraps=sandbox_manager.create_session
            ) as spy_create:
                await agent.run_scan("example.com", session=mock_session)

            # create_session should NOT have been called
            spy_create.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_scan_creates_session_if_none(
        self,
        sandbox_manager: "SandboxManager",
    ) -> None:
        """When session is None, run_scan calls create_session."""
        from sectest.agents.recon import ReconAgent

        agent = ReconAgent(sandbox_manager)

        # We need a more complete mock of create_session that returns something usable
        fake_session = mock.MagicMock()
        fake_session.container_id = "auto-created-container"

        async def _mock_exec(command: str, timeout: int = 30) -> "ExecResult":
            return _make_exec_result(command=command)

        fake_session.exec = _mock_exec

        mock_result = mock.MagicMock()
        mock_result.final_output = json.dumps({"target": "t", "tool_results": [], "summary": "s"})

        with mock.patch("sectest.agents.recon.Runner") as mock_runner:
            mock_runner.run = mock.AsyncMock(return_value=mock_result)

            with mock.patch.object(
                sandbox_manager,
                "create_session",
                mock.AsyncMock(return_value=fake_session),
            ) as mock_create:
                with mock.patch.object(
                    sandbox_manager, "schedule_cleanup"
                ) as mock_cleanup:
                    result = await agent.run_scan("example.com", session=None)

            mock_create.assert_called_once()
            mock_cleanup.assert_called_once_with(fake_session)

        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_run_scan_does_not_cleanup_provided_session(
        self,
        sandbox_manager: "SandboxManager",
        mock_session: mock.MagicMock,
    ) -> None:
        """When a session is provided, run_scan does NOT schedule cleanup."""
        from sectest.agents.recon import ReconAgent

        agent = ReconAgent(sandbox_manager)

        mock_result = mock.MagicMock()
        mock_result.final_output = json.dumps({"target": "t", "tool_results": [], "summary": "s"})

        with mock.patch("sectest.agents.recon.Runner") as mock_runner:
            mock_runner.run = mock.AsyncMock(return_value=mock_result)

            with mock.patch.object(
                sandbox_manager, "schedule_cleanup"
            ) as mock_cleanup:
                await agent.run_scan("example.com", session=mock_session)

            # schedule_cleanup should NOT be called (caller manages lifecycle)
            mock_cleanup.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: L-01 compliance — no agents.sandbox imports
# ---------------------------------------------------------------------------


class TestL01SandboxImportGuard:
    def test_no_agents_sandbox_imports(self) -> None:
        """GREP GUARD: recon.py must not contain 'from agents.sandbox' as an import."""
        import pathlib

        recon_file = pathlib.Path(__file__).parent.parent / "src" / "sectest" / "agents" / "recon.py"
        lines = recon_file.read_text(encoding="utf-8").splitlines()

        # Check only actual import lines, not docstring mentions
        pattern = re.compile(r"from\s+agents\.sandbox")
        for line in lines:
            if pattern.search(line):
                # Allow mentions in docstrings/comments
                stripped = line.strip()
                if stripped.startswith(('"""', '#', '``', '`')):
                    continue
                if stripped.startswith('"') and not stripped.startswith('from'):
                    continue
                raise AssertionError(
                    f"L-01 VIOLATION: recon.py imports from agents.sandbox at line:\n"
                    f"  {stripped}\n"
                    f"Only SandboxManager may import from agents.sandbox."
                )

    def test_no_shelltool_import(self) -> None:
        """GREP GUARD: recon.py must not import ShellTool from agents.sandbox."""
        import pathlib

        recon_file = pathlib.Path(__file__).parent.parent / "src" / "sectest" / "agents" / "recon.py"
        lines = recon_file.read_text(encoding="utf-8").splitlines()

        banned = ["ShellTool", "ShellCommandRequest", "ShellResult", "ShellCommandOutput", "ShellCallOutcome"]
        for line in lines:
            # Only check actual import lines, skip docstrings and comments
            stripped = line.strip()
            if not stripped:
                continue
            # Skip docstring lines (start with triple quotes or are inside docstrings)
            if stripped.startswith(('"""', '#', '``', '`', '"', 'All')):
                continue
            # Only check import lines
            if not stripped.startswith(("from ", "import ")):
                continue
            for token in banned:
                assert token not in stripped, (
                    f"L-01 VIOLATION: recon.py imports {token}. "
                    f"Use function_tool decorator from agents instead."
                )


# ---------------------------------------------------------------------------
# Tests: Instructions template
# ---------------------------------------------------------------------------


class TestInstructions:
    def test_instructions_include_target(self, sandbox_manager: "SandboxManager") -> None:
        """The instructions template includes the target string."""
        from sectest.agents.recon import ReconAgent

        agent = ReconAgent(sandbox_manager)
        instructions = agent._INSTRUCTIONS_TEMPLATE.format(target="10.10.10.10")

        assert "10.10.10.10" in instructions
        assert "Kali Linux sandbox" in instructions
        assert "nmap" in instructions
        assert "shell" in instructions

    def test_instructions_mention_output_format(self, sandbox_manager: "SandboxManager") -> None:
        """The instructions template specifies the JSON output format."""
        from sectest.agents.recon import ReconAgent

        agent = ReconAgent(sandbox_manager)
        instructions = agent._INSTRUCTIONS_TEMPLATE.format(target="test")

        assert "target" in instructions
        assert "tool_results" in instructions
        assert "summary" in instructions
        assert "json.loads" in instructions
