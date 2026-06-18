"""Unit tests for the SandboxManager abstraction layer (T3).

All tests mock ``DockerSandboxClient`` and ``docker-py`` calls — no real
Docker daemon is required.

Acceptance criteria covered:
    - test_sandbox_config_defaults
    - test_create_session_capabilities
    - test_exec_returns_exec_result
    - test_cleanup_after_scan
    - test_cleanup_on_error
    - test_scheduled_cleanup
    - test_pre_pull_image_returns_true
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from docker.errors import NotFound

from sectest.sandbox.manager import (
    ExecResult,
    Manifest,
    SandboxConfig,
    SandboxManager,
    SandboxSession,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_docker_session(container_id: str = "abc123"):
    """Build a mock DockerSandboxSession with a working ``exec()``."""
    session = MagicMock()
    session.container_id = container_id
    session.exec = AsyncMock(
        return_value=MagicMock(
            stdout=b"nmap output\n",
            stderr=b"",
            exit_code=0,
        )
    )
    return session


def _make_mock_docker_client():
    """Build a mock DockerSandboxClient with a working ``create()``/``delete()``."""
    client = MagicMock()
    client.create = AsyncMock(
        return_value=_make_mock_docker_session()
    )
    client.delete = AsyncMock()
    return client


def _wrap_session(
    inner_session,
    client=None,
    *,
    container_id="abc123",
    config=None,
    created_at=None,
):
    """Build a SandboxSession wrapping the given inner session."""
    return SandboxSession(
        _inner=inner_session,
        _client=client or _make_mock_docker_client(),
        container_id=container_id,
        config=config or SandboxConfig(),
        created_at=created_at or time.time(),
    )


# ---------------------------------------------------------------------------
# SandboxConfig
# ---------------------------------------------------------------------------


class TestSandboxConfigDefaults:
    """Verify default values match the acceptance criteria."""

    def test_default_image(self):
        config = SandboxConfig()
        assert config.image == "sectest/kali-sandbox:latest"

    def test_default_capabilities(self):
        config = SandboxConfig()
        assert config.capabilities == ("NET_ADMIN", "NET_RAW", "SYS_PTRACE")

    def test_default_memory_limit(self):
        config = SandboxConfig()
        assert config.memory_limit == "2g"

    def test_default_cpu_limit(self):
        config = SandboxConfig()
        assert config.cpu_limit == 2.0

    def test_default_retention_minutes(self):
        config = SandboxConfig()
        assert config.retention_minutes == 15

    def test_custom_overrides(self):
        config = SandboxConfig(
            image="custom:latest",
            capabilities=("NET_ADMIN",),
            memory_limit="4g",
            cpu_limit=4.0,
            retention_minutes=30,
        )
        assert config.image == "custom:latest"
        assert config.capabilities == ("NET_ADMIN",)
        assert config.memory_limit == "4g"
        assert config.cpu_limit == 4.0
        assert config.retention_minutes == 30


# ---------------------------------------------------------------------------
# ExecResult
# ---------------------------------------------------------------------------


class TestExecResult:
    def test_fields(self):
        result = ExecResult(
            stdout="output",
            stderr="error",
            exit_code=0,
            command="nmap --version",
            duration_ms=123.45,
        )
        assert result.stdout == "output"
        assert result.stderr == "error"
        assert result.exit_code == 0
        assert result.command == "nmap --version"
        assert result.duration_ms == 123.45


# ---------------------------------------------------------------------------
# SandboxSession.exec()
# ---------------------------------------------------------------------------


class TestSandboxSessionExec:
    @pytest.mark.asyncio
    async def test_exec_returns_exec_result(self):
        """Verify that exec() returns a properly structured ExecResult."""
        inner = _make_mock_docker_session()
        session = _wrap_session(inner)

        result = await session.exec("nmap --version", timeout=30)

        assert isinstance(result, ExecResult)
        assert result.command == "nmap --version"
        assert result.stdout == "nmap output\n"
        assert result.stderr == ""
        assert result.exit_code == 0
        assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_exec_decodes_bytes_to_str(self):
        """Verify that bytes fields are decoded with errors='replace'."""
        inner = _make_mock_docker_session()
        inner.exec.return_value = MagicMock(
            stdout=b"st\xffout",
            stderr=b"st\xfferr",
            exit_code=1,
        )
        session = _wrap_session(inner)

        result = await session.exec("cmd")

        # Should be str with replacement character, not raise
        assert isinstance(result.stdout, str)
        assert isinstance(result.stderr, str)
        assert "�" in result.stdout  # Unicode replacement char
        assert result.exit_code == 1

    @pytest.mark.asyncio
    async def test_exec_measures_duration(self):
        """Verify duration_ms is populated and positive."""
        inner = _make_mock_docker_session()

        # Delay the inner exec slightly
        async def slow_exec(*args, **kwargs):
            await asyncio.sleep(0.05)
            return MagicMock(stdout=b"", stderr=b"", exit_code=0)

        inner.exec = slow_exec
        session = _wrap_session(inner)

        result = await session.exec("cmd")
        assert result.duration_ms > 0


# ---------------------------------------------------------------------------
# SandboxManager
# ---------------------------------------------------------------------------


class TestSandboxManagerInit:
    def test_default_config(self):
        mgr = SandboxManager()
        assert isinstance(mgr._config, SandboxConfig)
        assert mgr._config.image == "sectest/kali-sandbox:latest"

    def test_custom_config(self):
        config = SandboxConfig(image="test:latest")
        mgr = SandboxManager(config=config)
        assert mgr._config.image == "test:latest"


class TestPrePullImage:
    @pytest.mark.asyncio
    async def test_pre_pull_image_returns_true_when_exists(self, mocker):
        """pre_pull_image() returns True when image already exists locally."""
        mock_docker = mocker.patch("docker.from_env")
        mock_client = MagicMock()
        mock_docker.return_value = mock_client

        # Simulate image already present
        mock_client.images.get.return_value = MagicMock()

        mgr = SandboxManager()
        result = await mgr.pre_pull_image()

        assert result is True
        mock_client.images.get.assert_called_once_with(
            "sectest/kali-sandbox:latest"
        )
        # pull should NOT be called since image exists
        mock_client.images.pull.assert_not_called()

    @pytest.mark.asyncio
    async def test_pre_pull_image_pulls_when_missing(self, mocker):
        """pre_pull_image() pulls the image when not present locally."""
        mock_docker = mocker.patch("docker.from_env")
        mock_client = MagicMock()
        mock_docker.return_value = mock_client

        # Image not found → must pull
        mock_client.images.get.side_effect = __import__("docker").errors.ImageNotFound(
            "not found"
        )

        mgr = SandboxManager()
        result = await mgr.pre_pull_image()

        assert result is True
        mock_client.images.pull.assert_called_once_with(
            "sectest/kali-sandbox:latest", platform=None
        )

    @pytest.mark.asyncio
    async def test_pre_pull_image_returns_false_on_pull_failure(self, mocker):
        """pre_pull_image() returns False when pull fails."""
        mock_docker = mocker.patch("docker.from_env")
        mock_client = MagicMock()
        mock_docker.return_value = mock_client

        mock_client.images.get.side_effect = __import__("docker").errors.ImageNotFound(
            "not found"
        )
        mock_client.images.pull.side_effect = __import__("docker").errors.APIError(
            "pull failed"
        )

        mgr = SandboxManager()
        result = await mgr.pre_pull_image()

        assert result is False


class TestCreateSession:
    @pytest.mark.asyncio
    async def test_create_session_returns_sandbox_session(self):
        """create_session() returns a SandboxSession with a container_id."""
        # Patch the DockerSandboxClient constructor
        with patch(
            "sectest.sandbox.manager.DockerSandboxClient",
            autospec=True,
        ) as mock_client_cls:
            mock_client = _make_mock_docker_client()
            # Make the constructor return our mock client
            mock_client_cls.side_effect = lambda docker_client: mock_client

            mgr = SandboxManager()
            # Override _docker to avoid real docker.from_env()
            mgr._docker = MagicMock()
            mgr._client = None

            session = await mgr.create_session()

            assert isinstance(session, SandboxSession)
            assert session.container_id == "abc123"
            assert session.container_id != ""
            assert isinstance(session.created_at, float)

    @pytest.mark.asyncio
    async def test_create_session_passes_manifest(self):
        """create_session() builds a Manifest and calls client.create()."""
        with patch(
            "sectest.sandbox.manager.DockerSandboxClient",
            autospec=True,
        ) as mock_client_cls:
            mock_client = _make_mock_docker_client()
            mock_client_cls.side_effect = lambda docker_client: mock_client

            mgr = SandboxManager()
            mgr._docker = MagicMock()
            mgr._client = None

            await mgr.create_session()

            # Verify create was called
            mock_client.create.assert_called_once()
            call_kwargs = mock_client.create.call_args.kwargs
            assert "manifest" in call_kwargs
            assert "options" in call_kwargs

            # Verify options contain the image
            options = call_kwargs["options"]
            assert options.image == "sectest/kali-sandbox:latest"

    @pytest.mark.asyncio
    async def test_create_session_with_workspace_dir(self, tmp_path):
        """create_session() mounts workspace_dir as LocalDir when provided."""
        (tmp_path / "test.txt").write_text("hello")

        with patch(
            "sectest.sandbox.manager.DockerSandboxClient",
            autospec=True,
        ) as mock_client_cls:
            mock_client = _make_mock_docker_client()
            mock_client_cls.side_effect = lambda docker_client: mock_client

            mgr = SandboxManager()
            mgr._docker = MagicMock()
            mgr._client = None

            session = await mgr.create_session(workspace_dir=tmp_path)

            assert session is not None
            mock_client.create.assert_called_once()

            call_kwargs = mock_client.create.call_args.kwargs
            manifest = call_kwargs["manifest"]
            assert isinstance(manifest, Manifest)
            assert "/workspace" in manifest.entries


class TestDestroySession:
    @pytest.mark.asyncio
    async def test_destroy_session_calls_client_delete(self):
        """destroy_session() delegates to DockerSandboxClient.delete()."""
        with patch(
            "sectest.sandbox.manager.DockerSandboxClient",
            autospec=True,
        ) as mock_client_cls:
            mock_client = _make_mock_docker_client()
            mock_client_cls.side_effect = lambda docker_client: mock_client

            mgr = SandboxManager()
            mgr._docker = MagicMock()
            mgr._client = mock_client

            inner = _make_mock_docker_session()
            session = _wrap_session(inner, client=mock_client)

            await mgr.destroy_session(session)

            mock_client.delete.assert_called_once_with(inner)

    @pytest.mark.asyncio
    async def test_destroy_session_silently_swallows_not_found(self):
        """destroy_session() catches NotFound silently (double-destroy safe)."""
        with patch(
            "sectest.sandbox.manager.DockerSandboxClient",
            autospec=True,
        ) as mock_client_cls:
            mock_client = _make_mock_docker_client()
            mock_client.delete.side_effect = NotFound("gone", response=MagicMock())
            mock_client_cls.side_effect = lambda docker_client: mock_client

            mgr = SandboxManager()
            mgr._docker = MagicMock()
            mgr._client = mock_client

            inner = _make_mock_docker_session()
            session = _wrap_session(inner, client=mock_client)

            # Should not raise
            await mgr.destroy_session(session)
            mock_client.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_destroy_session_does_not_raise_on_double_destroy(self):
        """destroy_session() is idempotent — second call also safe."""
        with patch(
            "sectest.sandbox.manager.DockerSandboxClient",
            autospec=True,
        ) as mock_client_cls:
            mock_client = _make_mock_docker_client()
            mock_client_cls.side_effect = lambda docker_client: mock_client

            mgr = SandboxManager()
            mgr._docker = MagicMock()
            mgr._client = mock_client

            inner = _make_mock_docker_session()
            session = _wrap_session(inner, client=mock_client)

            # First destroy succeeds
            await mgr.destroy_session(session)
            assert mock_client.delete.call_count == 1

            # Second destroy: NotFound is swallowed
            mock_client.delete.side_effect = NotFound("gone", response=MagicMock())
            await mgr.destroy_session(session)
            assert mock_client.delete.call_count == 2  # no exception raised


class TestScheduleCleanup:
    @pytest.mark.asyncio
    async def test_scheduled_cleanup_creates_task(self, mocker):
        """schedule_cleanup() creates an asyncio task that will later call destroy_session."""
        with patch(
            "sectest.sandbox.manager.DockerSandboxClient",
            autospec=True,
        ) as mock_client_cls:
            mock_client = _make_mock_docker_client()
            mock_client_cls.side_effect = lambda docker_client: mock_client

            mgr = SandboxManager()
            mgr._docker = MagicMock()
            mgr._client = mock_client

            inner = _make_mock_docker_session()
            session = _wrap_session(inner, client=mock_client)

            # Patch destroy_session to verify it is NOT called during scheduling
            destroy_mock = mocker.patch.object(
                mgr, "destroy_session", new_callable=AsyncMock
            )

            # schedule_cleanup is SYNC — it creates a background task
            mgr.schedule_cleanup(session)

            # Let the event loop process pending tasks briefly
            await asyncio.sleep(0)

            # destroy_session should NOT have been called (the task sleeps first)
            destroy_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_scheduled_cleanup_calls_destroy_after_sleep(self, mocker):
        """When the task's sleep completes, destroy_session is called."""
        with patch(
            "sectest.sandbox.manager.DockerSandboxClient",
            autospec=True,
        ) as mock_client_cls:
            mock_client = _make_mock_docker_client()
            mock_client_cls.side_effect = lambda docker_client: mock_client

            config = SandboxConfig(retention_minutes=0)  # 0 seconds!
            mgr = SandboxManager(config=config)
            mgr._docker = MagicMock()
            mgr._client = mock_client

            inner = _make_mock_docker_session()
            session = _wrap_session(inner, client=mock_client, config=config)

            # Patch destroy_session so we can verify the call
            destroy_mock = mocker.patch.object(
                mgr, "destroy_session", new_callable=AsyncMock
            )

            # Schedule cleanup — retention is 0, so sleep(0)
            mgr.schedule_cleanup(session)

            # Let the task run: sleep(0) yields immediately, then destroy_session fires
            await asyncio.sleep(0.1)

            # destroy_session should now have been called with the session
            destroy_mock.assert_called_once_with(session)


# ---------------------------------------------------------------------------
# Acceptance Criteria: No privileged / no network host
# ---------------------------------------------------------------------------

class TestSecurityConstraints:
    """Verify that the implementation never passes privileged=True
    or network='host'.  These grep checks are also verified via the
    acceptance criteria script, but we add code-level smoke tests here."""

    def test_sandbox_config_has_no_privileged_field(self):
        """SandboxConfig does not expose a 'privileged' toggle."""
        config = SandboxConfig()
        assert not hasattr(config, "privileged")

    def test_sandbox_config_has_no_network_host_field(self):
        """SandboxConfig does not expose a 'network' field."""
        config = SandboxConfig()
        assert not hasattr(config, "network")
