"""Shared test fixtures for the Sectest platform.

Provides common fixtures used across all test modules:
    - Mock Docker client
    - Mock LLM runner / provider
    - Temporary configuration
    - Mock SandboxSession
    - Mock SandboxManager (real Docker optional)
    - Progress output capture
"""

from __future__ import annotations

import io
import json
import os
from unittest import mock

import pytest


# ---------------------------------------------------------------------------
# Sandbox configuration
# ---------------------------------------------------------------------------


@pytest.fixture
def sandbox_config():
    """Return a default SandboxConfig for testing."""
    from sectest.sandbox.manager import SandboxConfig

    return SandboxConfig()


# ---------------------------------------------------------------------------
# Docker / Sandbox fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_docker_client(mocker):
    """Return a mocked Docker SDK client."""
    return mocker.MagicMock(name="docker_client")


@pytest.fixture
def mock_sandbox_session():
    """Return a mocked SandboxSession with a working async exec().

    The mock returns a default ExecResult with ``stdout="nmap output\n"``
    and exit_code=0.  Tests can override ``session.exec.side_effect`` or
    ``return_value`` to customise behaviour.
    """
    from sectest.sandbox.manager import ExecResult

    session = mock.MagicMock(name="SandboxSession")
    session.container_id = "mock-container-abc123"

    async def _default_exec(command: str, timeout: int = 30) -> ExecResult:
        return ExecResult(
            stdout="nmap output\n",
            stderr="",
            exit_code=0,
            command=command,
            duration_ms=50.0,
        )

    session.exec = _default_exec
    return session


# ---------------------------------------------------------------------------
# LLM / Provider fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_llm_provider():
    """Return a mocked LiteLLMModelProvider.

    ``get_model()`` returns a MagicMock that quacks like an
    ``OpenAIChatCompletionsModel`` — it has ``model`` and ``openai_client``
    attributes set.
    """
    provider = mock.MagicMock(name="LiteLLMModelProvider")

    def _get_model(model_name: str | None = None) -> mock.MagicMock:
        model = mock.MagicMock(name=f"Model({model_name})")
        model.model = model_name or "gpt-4o"
        model.openai_client = mock.MagicMock(name="AsyncOpenAI")
        return model

    provider.get_model = mock.MagicMock(side_effect=_get_model)
    provider._get_model_ref = _get_model  # expose for direct call in tests
    return provider


@pytest.fixture(autouse=False)
def patch_llm_api_key(monkeypatch):
    """Ensure LITELLM_API_KEY is set so LLMConfig does not raise.

    This fixture is NOT autouse by default — individual test classes may
    opt-in by including it in their fixture list.
    """
    monkeypatch.setenv("LITELLM_API_KEY", "sk-test-fixture")
    monkeypatch.setenv("LITELLM_BASE_URL", "http://localhost:4000/v1")
    monkeypatch.setenv("DEFAULT_MODEL", "gpt-4o")


# ---------------------------------------------------------------------------
# SandboxManager fixtures (mock Docker)
# ---------------------------------------------------------------------------


def _make_mock_docker_session_for_conf(container_id: str = "abc123"):
    """Build a mock DockerSandboxSession with a working ``exec()``."""
    session = mock.MagicMock()
    session.container_id = container_id
    session.exec = mock.AsyncMock(
        return_value=mock.MagicMock(
            stdout=b"nmap output\n",
            stderr=b"",
            exit_code=0,
        )
    )
    return session


def _make_mock_docker_client_for_conf():
    """Build a mock DockerSandboxClient with a working ``create()``/``delete()``."""
    client = mock.MagicMock()
    client.create = mock.AsyncMock(
        return_value=_make_mock_docker_session_for_conf()
    )
    client.delete = mock.AsyncMock()
    return client


@pytest.fixture
def mock_sandbox_manager():
    """Return a SandboxManager with all Docker interactions mocked out.

    Session creation returns a real ``SandboxSession`` wrapping a mock
    ``DockerSandboxSession`` so that ``session.exec()`` works end-to-end.
    Cleanup methods are also mocked so tests can assert they were called.
    """
    from sectest.sandbox.manager import SandboxConfig, SandboxManager, SandboxSession

    with mock.patch(
        "sectest.sandbox.manager.DockerSandboxClient",
        autospec=True,
    ) as mock_client_cls:
        mock_client = _make_mock_docker_client_for_conf()
        mock_client_cls.side_effect = lambda docker_client: mock_client

        config = SandboxConfig()
        mgr = SandboxManager(config=config)
        mgr._docker = mock.MagicMock()       # avoid real docker.from_env()
        mgr._client = None                    # force lazy init to use our mock

        # Also mock pre_pull_image for speed
        mgr.pre_pull_image = mock.AsyncMock(return_value=True)

        # Keep destroy/schedule accessible for assertion
        mgr._mock_inner_client = mock_client

        yield mgr


# ---------------------------------------------------------------------------
# Progress output capture
# ---------------------------------------------------------------------------


@pytest.fixture
def progress_output():
    """Capture stdout as StringIO and return a helper for inspecting JSON lines.

    Usage::

        def test_something(progress_output):
            emitter = ProgressEmitter()
            emitter.emit("DONE", "done", "ok")
            lines = progress_output.get_json_lines()
            assert lines[0]["phase"] == "DONE"
    """

    class _Capture:
        def __init__(self) -> None:
            self.buf = io.StringIO()
            self._patcher = mock.patch("sys.stdout", self.buf)

        def start(self) -> None:
            self._patcher.start()

        def stop(self) -> None:
            self._patcher.stop()

        def get_json_lines(self) -> list[dict]:
            """Return all stdout lines as parsed JSON dicts (skip blanks)."""
            return [
                json.loads(line)
                for line in self.buf.getvalue().splitlines()
                if line.strip()
            ]

        def get_text(self) -> str:
            """Return raw captured text."""
            return self.buf.getvalue()

    cap = _Capture()
    cap.start()
    yield cap
    cap.stop()


# ---------------------------------------------------------------------------
# Docker availability check
# ---------------------------------------------------------------------------


def _docker_available() -> bool:
    """Return True if a Docker daemon is reachable on this machine."""
    try:
        import docker

        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


docker_available = pytest.mark.skipif(
    not _docker_available(),
    reason="Docker daemon is not available",
)
"""Marker to skip tests that require a real Docker daemon."""
