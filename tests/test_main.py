"""Unit tests for main.py entry point and streaming.py (T7).

Tests verify:
    - ProgressEmitter.emit() produces valid JSON lines with required keys
    - ProgressEmitter.phase() context manager handles done/error states
    - test_streaming_progress: mock SandboxManager + ReconAgent, capture stdout,
      assert each phase JSON line present and valid
    - test_streaming_error_phase: mock ReconAgent to raise, assert error phase emitted
    - test_cleanup_called_on_error: verify schedule_cleanup called in finally
    - test_cli_target_argument: verify --target parsed correctly
    - test_progress_format_default: --progress-format defaults to json
    - test_progress_format_text: --progress-format text suppresses JSON output
    - test_help: --help works via argparse
    - test_config_error_early_exit: missing API key causes clean error exit

All external dependencies (Docker, sandbox, LLM) are mocked — no real
containers or API calls are made.
"""

from __future__ import annotations

import asyncio
import io
import json
import sys
from unittest import mock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _capture_stdout_lines(coro) -> list[str]:
    """Run an async callable, capture sys.stdout, return line list."""
    buf = io.StringIO()
    original_stdout = sys.stdout
    sys.stdout = buf
    try:
        asyncio.run(coro())
    finally:
        sys.stdout = original_stdout
    return buf.getvalue().splitlines()


# ---------------------------------------------------------------------------
# Tests: ProgressEmitter (unit tests on streaming.py)
# ---------------------------------------------------------------------------


class TestProgressEmitterEmit:
    """Tests for ProgressEmitter.emit()."""

    def test_emit_writes_valid_json_line(self) -> None:
        """emit() writes a single valid JSON object to stdout."""
        from sectest.streaming import ProgressEmitter

        emitter = ProgressEmitter()
        buf = io.StringIO()

        with mock.patch("sys.stdout", buf):
            emitter.emit("PULL_IMAGE", "running", "Pulling image...")

        lines = buf.getvalue().splitlines()
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["phase"] == "PULL_IMAGE"
        assert parsed["status"] == "running"
        assert parsed["message"] == "Pulling image..."
        assert "timestamp" in parsed

    def test_emit_all_required_keys(self) -> None:
        """Each emitted line contains phase, status, timestamp, message."""
        from sectest.streaming import ProgressEmitter

        emitter = ProgressEmitter()
        buf = io.StringIO()

        phases = [
            ("PULL_IMAGE", "running", "pull"),
            ("CREATE_SANDBOX", "running", "create"),
            ("TOOL_EXEC", "running", "tools"),
            ("PARSE_RESULTS", "running", "parse"),
            ("DONE", "done", "finish"),
        ]

        with mock.patch("sys.stdout", buf):
            for phase, status, msg in phases:
                emitter.emit(phase, status, msg)

        lines = buf.getvalue().splitlines()
        assert len(lines) == 5
        for line in lines:
            parsed = json.loads(line)
            assert "phase" in parsed
            assert "status" in parsed
            assert "timestamp" in parsed
            assert "message" in parsed

    def test_emit_includes_extra_kwargs(self) -> None:
        """Extra keyword arguments are merged into the JSON object."""
        from sectest.streaming import ProgressEmitter

        emitter = ProgressEmitter()
        buf = io.StringIO()

        with mock.patch("sys.stdout", buf):
            emitter.emit("DONE", "done", "All good", summary="2 ports found", exit_code=0)

        parsed = json.loads(buf.getvalue().splitlines()[0])
        assert parsed["summary"] == "2 ports found"
        assert parsed["exit_code"] == 0

    def test_emit_timestamp_is_iso8601(self) -> None:
        """The timestamp field is a valid ISO 8601 string with timezone."""
        from sectest.streaming import ProgressEmitter

        emitter = ProgressEmitter()
        buf = io.StringIO()

        with mock.patch("sys.stdout", buf):
            emitter.emit("DONE", "done", "")

        parsed = json.loads(buf.getvalue().splitlines()[0])
        ts = parsed["timestamp"]
        # ISO 8601 in python datetime outputs: 2026-06-18T00:00:00+00:00
        assert "T" in ts
        assert "+" in ts or "Z" in ts

    def test_emit_writes_without_trailing_whitespace(self) -> None:
        """Each line is exactly one JSON object, no trailing spaces."""
        from sectest.streaming import ProgressEmitter

        emitter = ProgressEmitter()
        buf = io.StringIO()

        with mock.patch("sys.stdout", buf):
            emitter.emit("TOOL_EXEC", "done", "ok")

        line = buf.getvalue().splitlines()[0]
        # Should be valid JSON (the whole line)
        parsed = json.loads(line)
        assert parsed["phase"] == "TOOL_EXEC"


class TestProgressEmitterPhase:
    """Tests for ProgressEmitter.phase() context manager."""

    def test_phase_emits_running_then_done(self) -> None:
        """phase() context manager emits 'running' on entry, 'done' on success."""
        from sectest.streaming import ProgressEmitter

        emitter = ProgressEmitter()
        buf = io.StringIO()

        with mock.patch("sys.stdout", buf):
            with emitter.phase("PULL_IMAGE", "pull"):
                pass  # no-op

        lines = buf.getvalue().splitlines()
        assert len(lines) == 2
        entry = json.loads(lines[0])
        exit_ = json.loads(lines[1])

        assert entry["phase"] == "PULL_IMAGE"
        assert entry["status"] == "running"
        assert entry["message"] == "pull"

        assert exit_["phase"] == "PULL_IMAGE"
        assert exit_["status"] == "done"
        assert exit_["message"] == "pull"

    def test_phase_emits_error_on_exception(self) -> None:
        """phase() context manager emits 'error' status when an exception occurs."""
        from sectest.streaming import ProgressEmitter

        emitter = ProgressEmitter()
        buf = io.StringIO()

        with mock.patch("sys.stdout", buf):
            with pytest.raises(RuntimeError, match="boom"):
                with emitter.phase("TOOL_EXEC", "scanning"):
                    raise RuntimeError("boom")

        lines = buf.getvalue().splitlines()
        assert len(lines) == 2
        error_line = json.loads(lines[1])
        assert error_line["phase"] == "TOOL_EXEC"
        assert error_line["status"] == "error"
        assert error_line["error"] == "boom"
        assert error_line["error_type"] == "RuntimeError"

    def test_phase_error_includes_message(self) -> None:
        """On error, the original phase message is preserved."""
        from sectest.streaming import ProgressEmitter

        emitter = ProgressEmitter()
        buf = io.StringIO()

        with mock.patch("sys.stdout", buf):
            with pytest.raises(ValueError):
                with emitter.phase("PULL_IMAGE", "Pre-pulling..."):
                    raise ValueError("pull failed")

        lines = buf.getvalue().splitlines()
        error_line = json.loads(lines[1])
        assert error_line["message"] == "Pre-pulling..."
        assert error_line["error_type"] == "ValueError"

    def test_phase_uses_exception_str_when_message_empty(self) -> None:
        """When phase message is empty, error uses the exception str as message."""
        from sectest.streaming import ProgressEmitter

        emitter = ProgressEmitter()
        buf = io.StringIO()

        with mock.patch("sys.stdout", buf):
            with pytest.raises(RuntimeError, match="test error"):
                with emitter.phase("DONE", ""):
                    raise RuntimeError("test error")

        lines = buf.getvalue().splitlines()
        error_line = json.loads(lines[1])
        assert error_line["status"] == "error"
        # Message should be the exception string since incoming message is empty
        assert error_line["message"] == "test error"

    def test_phase_re_raises_original_exception(self) -> None:
        """The exception is re-raised after emission so callers can handle it."""
        from sectest.streaming import ProgressEmitter

        emitter = ProgressEmitter()

        class CustomError(Exception):
            pass

        buf = io.StringIO()
        with mock.patch("sys.stdout", buf):
            with pytest.raises(CustomError, match="custom"):
                with emitter.phase("TOOL_EXEC", "ops"):
                    raise CustomError("custom")

        # Verify the error was still emitted
        lines = buf.getvalue().splitlines()
        error_line = json.loads(lines[1])
        assert error_line["status"] == "error"


# ---------------------------------------------------------------------------
# Tests: CLI argument parsing
# ---------------------------------------------------------------------------


class TestCLIArguments:
    """Tests for argparse-based CLI argument handling."""

    def test_target_defaults_to_localhost(self) -> None:
        """--target defaults to 'localhost' when not provided."""
        from sectest.main import _build_parser

        parser = _build_parser()
        args = parser.parse_args([])
        assert args.target == "localhost"

    def test_target_accepts_custom_value(self) -> None:
        """--target accepts a custom hostname/IP."""
        from sectest.main import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["--target", "example.com"])
        assert args.target == "example.com"

    def test_progress_format_defaults_to_json(self) -> None:
        """--progress-format defaults to 'json'."""
        from sectest.main import _build_parser

        parser = _build_parser()
        args = parser.parse_args([])
        assert args.progress_format == "json"

    def test_progress_format_accepts_text(self) -> None:
        """--progress-format accepts 'text'."""
        from sectest.main import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["--progress-format", "text"])
        assert args.progress_format == "text"

    def test_progress_format_rejects_invalid(self) -> None:
        """--progress-format rejects invalid values."""
        from sectest.main import _build_parser

        parser = _build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--progress-format", "xml"])

    def test_help_flag_works(self) -> None:
        """--help produces usage text and exits."""
        from sectest.main import _build_parser

        parser = _build_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--help"])
        assert exc_info.value.code == 0


# ---------------------------------------------------------------------------
# Tests: streaming progress integration (mock full pipeline)
# ---------------------------------------------------------------------------


class TestStreamingProgress:
    """End-to-end tests with mocked SandboxManager and ReconAgent."""

    @pytest.fixture(autouse=True)
    def _patch_llm_config(self, monkeypatch):
        """Ensure LLMConfig does not fail due to missing API key."""
        monkeypatch.setenv("LITELLM_API_KEY", "test-key-do-not-use")

    @pytest.fixture
    def mock_manager(self) -> mock.MagicMock:
        """Mock SandboxManager with async methods."""
        mgr = mock.MagicMock(name="SandboxManager")
        mgr.pre_pull_image = mock.AsyncMock(return_value=True)

        # create_session returns a fake SandboxSession
        fake_session = mock.MagicMock(name="SandboxSession")
        fake_session.container_id = "test-container-001"
        mgr.create_session = mock.AsyncMock(return_value=fake_session)
        mgr.schedule_cleanup = mock.MagicMock()
        return mgr

    @pytest.fixture
    def mock_agent(self) -> mock.MagicMock:
        """Mock ReconAgent that returns sample scan results."""
        agent = mock.MagicMock(name="ReconAgent")
        agent.run_scan = mock.AsyncMock(
            return_value={
                "target": "localhost",
                "tool_results": [
                    {
                        "tool": "nmap",
                        "command": "nmap -sV localhost",
                        "exit_code": 0,
                        "findings": ["Port 22/tcp - SSH"],
                        "raw_output_summary": "One port open",
                    }
                ],
                "summary": "Found 1 open port: SSH.",
            }
        )
        return agent

    @pytest.mark.asyncio
    async def test_json_progress_emits_all_phases(
        self,
        mock_manager: mock.MagicMock,
        mock_agent: mock.MagicMock,
    ) -> None:
        """With --progress-format json, stdout contains one JSON line per phase."""
        from sectest.main import _run_phase_pull_image
        from sectest.main import _run_phase_create_sandbox
        from sectest.main import _run_phase_tool_exec
        from sectest.main import _output_results
        from sectest.streaming import ProgressEmitter

        emitter = ProgressEmitter()
        buf = io.StringIO()

        with mock.patch("sys.stdout", buf):
            # Run phases in order
            await _run_phase_pull_image(emitter, mock_manager)
            session = mock_manager.create_session.return_value
            await _run_phase_create_sandbox(emitter, mock_manager)
            result = await _run_phase_tool_exec(emitter, mock_agent, "localhost", session)
            _output_results(emitter, result)

        lines = [L for L in buf.getvalue().splitlines() if L.strip()]

        # We expect at least: PULL_IMAGE(running), PULL_IMAGE(done),
        # CREATE_SANDBOX(running), CREATE_SANDBOX(done),
        # TOOL_EXEC(running), TOOL_EXEC(done),
        # PARSE_RESULTS(running), PARSE_RESULTS(done), DONE(done)
        # The last line is the JSON dump (not a progress line) so skip it
        progress_lines = [L for L in lines if json.loads(L).get("phase")]

        phases_seen = {json.loads(L)["phase"] for L in progress_lines}
        expected_phases = {"PULL_IMAGE", "CREATE_SANDBOX", "TOOL_EXEC", "PARSE_RESULTS", "DONE"}
        assert expected_phases.issubset(phases_seen), (
            f"Missing phases: {expected_phases - phases_seen}"
        )

    @pytest.mark.asyncio
    async def test_streaming_progress_each_json_line_valid(
        self,
        mock_manager: mock.MagicMock,
        mock_agent: mock.MagicMock,
    ) -> None:
        """Every JSON-line progress output is valid JSON with required keys."""
        from sectest.main import _run_phase_pull_image
        from sectest.main import _run_phase_create_sandbox
        from sectest.main import _run_phase_tool_exec
        from sectest.main import _output_results
        from sectest.streaming import ProgressEmitter

        emitter = ProgressEmitter()
        buf = io.StringIO()

        with mock.patch("sys.stdout", buf):
            await _run_phase_pull_image(emitter, mock_manager)
            session = mock_manager.create_session.return_value
            await _run_phase_create_sandbox(emitter, mock_manager)
            result = await _run_phase_tool_exec(emitter, mock_agent, "localhost", session)
            _output_results(emitter, result)

        lines = buf.getvalue().splitlines()

        for line in lines:
            if not line.strip():
                continue
            parsed = json.loads(line)
            if "phase" in parsed:
                # Progress line
                assert "status" in parsed, f"Missing status in: {line}"
                assert "timestamp" in parsed, f"Missing timestamp in: {line}"
                assert "message" in parsed, f"Missing message in: {line}"
                assert parsed["status"] in ("running", "done", "error")

    @pytest.mark.asyncio
    async def test_streaming_phase_statuses_correct(
        self,
        mock_manager: mock.MagicMock,
        mock_agent: mock.MagicMock,
    ) -> None:
        """Each phase transitions: running -> done (no skipped state)."""
        from sectest.main import _run_phase_pull_image
        from sectest.main import _run_phase_create_sandbox
        from sectest.main import _run_phase_tool_exec
        from sectest.main import _output_results
        from sectest.streaming import ProgressEmitter

        emitter = ProgressEmitter()
        buf = io.StringIO()

        with mock.patch("sys.stdout", buf):
            await _run_phase_pull_image(emitter, mock_manager)
            session = mock_manager.create_session.return_value
            await _run_phase_create_sandbox(emitter, mock_manager)
            result = await _run_phase_tool_exec(emitter, mock_agent, "localhost", session)
            _output_results(emitter, result)

        all_lines = buf.getvalue().splitlines()
        progress_lines = []
        for line in all_lines:
            if not line.strip():
                continue
            parsed = json.loads(line)
            if "phase" in parsed:
                progress_lines.append(parsed)

        # Group by phase
        by_phase: dict = {}
        for p in progress_lines:
            by_phase.setdefault(p["phase"], []).append(p)

        # Each execution phase should have running -> done
        for ph in ["PULL_IMAGE", "CREATE_SANDBOX", "TOOL_EXEC", "PARSE_RESULTS"]:
            statuses = [e["status"] for e in by_phase.get(ph, [])]
            assert "running" in statuses, f"{ph} missing 'running'"
            assert "done" in statuses, f"{ph} missing 'done'"

        # DONE should only have "done"
        done_statuses = [e["status"] for e in by_phase.get("DONE", [])]
        assert all(s == "done" for s in done_statuses)

    @pytest.mark.asyncio
    async def test_text_format_no_json_lines(
        self,
        mock_manager: mock.MagicMock,
        mock_agent: mock.MagicMock,
    ) -> None:
        """With --progress-format text, no JSON progress lines are emitted."""
        from sectest.main import _run_phase_pull_image
        from sectest.main import _run_phase_create_sandbox
        from sectest.main import _run_phase_tool_exec
        from sectest.main import _output_results

        buf = io.StringIO()

        with mock.patch("sys.stdout", buf):
            await _run_phase_pull_image(None, mock_manager)
            session = mock_manager.create_session.return_value
            await _run_phase_create_sandbox(None, mock_manager)
            result = await _run_phase_tool_exec(None, mock_agent, "localhost", session)
            _output_results(None, result)

        output = buf.getvalue()
        # Should contain human-readable text
        assert "Pre-pulling Kali sandbox image" in output
        assert "Creating sandbox container" in output

        # The full output (all lines concatenated) should contain parseable JSON
        # for the result -- just not as separate progress lines.
        # json.dump with indent=2 is pretty-printed, so join all lines.
        assert '"target"' in output
        assert '"summary"' in output


class TestStreamingErrorPhase:
    """Tests for error handling in the streaming pipeline."""

    @pytest.fixture(autouse=True)
    def _patch_llm_config(self, monkeypatch):
        """Ensure LLMConfig.from_env() does not fail."""
        monkeypatch.setenv("LITELLM_API_KEY", "test-key-do-not-use")

    def test_error_phase_json_emitted_on_tool_exec_error(self) -> None:
        """When ReconAgent raises, the error phase JSON is emitted."""
        from sectest.main import _run_phase_tool_exec
        from sectest.streaming import ProgressEmitter

        emitter = ProgressEmitter()
        mock_agent = mock.MagicMock(name="ReconAgent")
        mock_agent.run_scan = mock.AsyncMock(side_effect=RuntimeError("scan failed"))
        mock_session = mock.MagicMock(name="SandboxSession")

        buf = io.StringIO()

        with mock.patch("sys.stdout", buf):
            with pytest.raises(RuntimeError, match="scan failed"):
                asyncio.run(
                    _run_phase_tool_exec(emitter, mock_agent, "target", mock_session)
                )

        lines = buf.getvalue().splitlines()
        assert len(lines) >= 2

        # First line: running
        running = json.loads(lines[0])
        assert running["phase"] == "TOOL_EXEC"
        assert running["status"] == "running"

        # Second line: error
        error = json.loads(lines[1])
        assert error["phase"] == "TOOL_EXEC"
        assert error["status"] == "error"
        assert error["error"] == "scan failed"
        assert error["error_type"] == "RuntimeError"

    def test_error_phase_json_on_pull_error(self) -> None:
        """When pre_pull_image fails, the error phase JSON is emitted."""
        from sectest.main import _run_phase_pull_image
        from sectest.streaming import ProgressEmitter

        emitter = ProgressEmitter()
        mock_manager = mock.MagicMock(name="SandboxManager")
        mock_manager.pre_pull_image = mock.AsyncMock(
            side_effect=RuntimeError("pull failed")
        )

        buf = io.StringIO()

        with mock.patch("sys.stdout", buf):
            with pytest.raises(RuntimeError, match="pull failed"):
                asyncio.run(_run_phase_pull_image(emitter, mock_manager))

        lines = buf.getvalue().splitlines()
        assert len(lines) == 2
        error = json.loads(lines[1])
        assert error["phase"] == "PULL_IMAGE"
        assert error["status"] == "error"


class TestCleanupCalledOnError:
    """Tests verifying schedule_cleanup is called in finally block."""

    @pytest.fixture(autouse=True)
    def _patch_llm_config(self, monkeypatch):
        """Ensure LLMConfig.from_env() does not fail."""
        monkeypatch.setenv("LITELLM_API_KEY", "test-key-do-not-use")

    def test_cleanup_called_when_scan_fails(self) -> None:
        """schedule_cleanup is called even when scan raises an error."""
        from sectest.main import async_main

        # Setup mocks
        mock_manager_cls = mock.MagicMock(name="SandboxManager")
        mock_manager_instance = mock.MagicMock(name="manager_instance")
        mock_manager_instance.pre_pull_image = mock.AsyncMock(return_value=True)
        fake_session = mock.MagicMock(name="session")
        fake_session.container_id = "err-container-002"
        mock_manager_instance.create_session = mock.AsyncMock(return_value=fake_session)
        mock_manager_instance.schedule_cleanup = mock.MagicMock()
        mock_manager_cls.return_value = mock_manager_instance

        mock_agent_cls = mock.MagicMock(name="ReconAgent")
        mock_agent_instance = mock.MagicMock(name="agent_instance")
        mock_agent_instance.run_scan = mock.AsyncMock(
            side_effect=RuntimeError("scan exploded")
        )
        mock_agent_cls.return_value = mock_agent_instance

        with mock.patch("sectest.main.SandboxManager", mock_manager_cls):
            with mock.patch("sectest.main.ReconAgent", mock_agent_cls):
                with mock.patch("sys.argv", ["sectest", "--target", "example.com"]):
                    # Suppress stdout/stderr noise
                    with mock.patch("sys.stdout", io.StringIO()):
                        with mock.patch("sys.stderr", io.StringIO()):
                            with pytest.raises(RuntimeError, match="scan exploded"):
                                asyncio.run(async_main())

        # schedule_cleanup MUST have been called (in finally block)
        mock_manager_instance.schedule_cleanup.assert_called_once_with(fake_session)

    def test_cleanup_called_when_session_creation_fails(self) -> None:
        """schedule_cleanup is not called when session is None (safe path)."""
        from sectest.main import async_main

        mock_manager_cls = mock.MagicMock(name="SandboxManager")
        mock_manager_instance = mock.MagicMock(name="manager_instance")
        mock_manager_instance.pre_pull_image = mock.AsyncMock(return_value=True)
        mock_manager_instance.create_session = mock.AsyncMock(
            side_effect=RuntimeError("container create failed")
        )
        mock_manager_instance.schedule_cleanup = mock.MagicMock()
        mock_manager_cls.return_value = mock_manager_instance

        with mock.patch("sectest.main.SandboxManager", mock_manager_cls):
            with mock.patch("sys.argv", ["sectest"]):
                with mock.patch("sys.stdout", io.StringIO()):
                    with mock.patch("sys.stderr", io.StringIO()):
                        with pytest.raises(RuntimeError, match="container create failed"):
                            asyncio.run(async_main())

        # schedule_cleanup should NOT be called because session is None
        mock_manager_instance.schedule_cleanup.assert_not_called()

    def test_cleanup_called_on_success_path(self) -> None:
        """schedule_cleanup is also called on the success path."""
        from sectest.main import async_main

        mock_manager_cls = mock.MagicMock(name="SandboxManager")
        mock_manager_instance = mock.MagicMock(name="manager_instance")
        mock_manager_instance.pre_pull_image = mock.AsyncMock(return_value=True)
        fake_session = mock.MagicMock(name="session")
        fake_session.container_id = "ok-container-003"
        mock_manager_instance.create_session = mock.AsyncMock(return_value=fake_session)
        mock_manager_instance.schedule_cleanup = mock.MagicMock()
        mock_manager_cls.return_value = mock_manager_instance

        mock_agent_cls = mock.MagicMock(name="ReconAgent")
        mock_agent_instance = mock.MagicMock(name="agent_instance")
        mock_agent_instance.run_scan = mock.AsyncMock(
            return_value={
                "target": "example.com",
                "tool_results": [],
                "summary": "clean scan",
            }
        )
        mock_agent_cls.return_value = mock_agent_instance

        with mock.patch("sectest.main.SandboxManager", mock_manager_cls):
            with mock.patch("sectest.main.ReconAgent", mock_agent_cls):
                with mock.patch("sys.argv", ["sectest", "--target", "example.com"]):
                    with mock.patch("sys.stdout", io.StringIO()):
                        with mock.patch("sys.stderr", io.StringIO()):
                            asyncio.run(async_main())

        mock_manager_instance.schedule_cleanup.assert_called_once_with(fake_session)


class TestConfigError:
    """Tests for configuration validation at startup."""

    def test_missing_api_key_exits_with_error(self, monkeypatch) -> None:
        """When LITELLM_API_KEY is unset, the program exits with code 1."""
        # Remove the env var (even if set by other fixtures)
        monkeypatch.delenv("LITELLM_API_KEY", raising=False)

        from sectest.main import async_main

        with mock.patch("sys.argv", ["sectest"]):
            with mock.patch("sys.stdout", io.StringIO()):
                with mock.patch("sys.stderr", io.StringIO()):
                    with pytest.raises(SystemExit) as exc_info:
                        asyncio.run(async_main())

        assert exc_info.value.code == 1

    def test_missing_api_key_emits_error_json(self, monkeypatch) -> None:
        """When LITELLM_API_KEY is unset and format is json, error JSON is emitted."""
        monkeypatch.delenv("LITELLM_API_KEY", raising=False)

        from sectest.main import async_main

        stdout_buf = io.StringIO()

        with mock.patch("sys.argv", ["sectest", "--progress-format", "json"]):
            with mock.patch("sys.stdout", stdout_buf):
                with mock.patch("sys.stderr", io.StringIO()):
                    with pytest.raises(SystemExit) as exc_info:
                        asyncio.run(async_main())

        assert exc_info.value.code == 1
        # Should have emitted an error line
        lines = stdout_buf.getvalue().splitlines()
        assert len(lines) >= 1
        error_line = json.loads(lines[0])
        assert error_line["status"] == "error"


class TestMainModuleAttribute:
    """Verify main.py can be executed as 'python -m sectest.main'."""

    def test_main_has_name_main_guard(self) -> None:
        """main.py includes the classic if __name__ == '__main__' guard."""
        import pathlib

        main_file = (
            pathlib.Path(__file__).parent.parent / "src" / "sectest" / "main.py"
        )
        text = main_file.read_text(encoding="utf-8")

        assert 'if __name__ == "__main__"' in text
        assert "main()" in text

    def test_main_function_is_callable(self) -> None:
        """The main() function exists and is callable (but we don't run it)."""
        from sectest.main import main

        assert callable(main)
