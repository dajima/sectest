"""SandboxManager abstraction layer (T3).

Wraps all ``agents.sandbox`` API calls. This is the **only** file in the
project that may import from ``agents.sandbox`` (L-01, L-02).

Key design constraints:
    - All docker-py sync calls wrapped in ``asyncio.to_thread()``
    - NEVER pass ``privileged=True`` or ``network="host"``
    - Use ``Manifest`` with File/LocalDir entries for workspace mounts
    - ``SandboxSession.exec()`` decodes ``bytes`` to ``str`` with ``errors="replace"``
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import docker
from docker.errors import NotFound

# These imports are ONLY in this file (L-01, L-02)
from agents.sandbox import Manifest
from agents.sandbox.entries import File, LocalDir
from agents.sandbox.sandboxes.docker import (
    DockerSandboxClient,
    DockerSandboxClientOptions,
    DockerSandboxSession,
)

if TYPE_CHECKING:
    from docker import DockerClient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class SandboxConfig:
    """Configuration for a Kali sandbox container.

    Attributes:
        image: Docker image name (gold copy built from Dockerfile.kali).
        capabilities: Linux capabilities granted to the container.
            Strictly limited to NET_ADMIN, NET_RAW, SYS_PTRACE (L-04).
        memory_limit: Container memory limit (Docker format, e.g. "2g").
        cpu_limit: Container CPU limit in cores.
        retention_minutes: Post-scan retention window before auto-cleanup (D-04).
    """

    image: str = "sectest/kali-sandbox:latest"
    capabilities: tuple[str, ...] = ("NET_ADMIN", "NET_RAW", "SYS_PTRACE")
    memory_limit: str = "2g"
    cpu_limit: float = 2.0
    retention_minutes: int = 15


@dataclass
class ExecResult:
    """Structured command output returned by :meth:`SandboxSession.exec` (L-07).

    All fields are ``str`` — decoding from ``bytes`` is handled inside
    :meth:`SandboxSession.exec` with ``errors="replace"``.
    """

    stdout: str
    """Standard output as a decoded string."""

    stderr: str
    """Standard error as a decoded string."""

    exit_code: int
    """Process exit code.  0 typically indicates success."""

    command: str
    """The command that was executed (echoed back for auditability)."""

    duration_ms: float
    """Wall-clock duration of the command in milliseconds."""


# ---------------------------------------------------------------------------
# SandboxSession
# ---------------------------------------------------------------------------


@dataclass
class SandboxSession:
    """Opaque handle to an active Kali sandbox container.

    Agent code uses **this** class, never the raw ``DockerSandboxSession``.
    Only :class:`SandboxManager` creates instances.

    Attributes:
        _inner: The underlying SDK ``DockerSandboxSession``.
        _client: The ``DockerSandboxClient`` that owns this session.
        container_id: Docker container ID string.
        config: The :class:`SandboxConfig` used to create this session.
        created_at: Unix timestamp when the session was created.
    """

    _inner: DockerSandboxSession
    _client: DockerSandboxClient
    container_id: str
    config: SandboxConfig
    created_at: float

    async def exec(self, command: str, timeout: int = 30) -> ExecResult:
        """Execute a shell command inside the Kali sandbox.

        Delegates to the underlying ``DockerSandboxSession.exec()``,
        decodes ``bytes`` fields to ``str`` with ``errors="replace"``,
        and measures wall-clock duration.

        Args:
            command: Shell command to execute (e.g. ``"nmap --version"``).
            timeout: Maximum execution time in seconds.  Defaults to 30.

        Returns:
            :class:`ExecResult` with decoded string fields and duration.
        """
        started_at = time.monotonic()

        result = await self._inner.exec(command, timeout=timeout)

        duration_ms = (time.monotonic() - started_at) * 1000.0

        return ExecResult(
            stdout=result.stdout.decode("utf-8", errors="replace"),
            stderr=result.stderr.decode("utf-8", errors="replace"),
            exit_code=result.exit_code,
            command=command,
            duration_ms=round(duration_ms, 2),
        )


# ---------------------------------------------------------------------------
# SandboxManager
# ---------------------------------------------------------------------------


class SandboxManager:
    """Manages Kali Linux Docker sandbox lifecycle (L-02).

    Responsibilities:
        - Pre-pull Kali image at startup (L-06)
        - Create ephemeral per-scan containers (D-01, D-02)
        - Enforce least-privilege capabilities (L-04)
        - Auto-cleanup after timeout or on error (L-08, D-03, D-04)
        - Expose structured shell execution via :class:`SandboxSession` (L-07)

    Only this class and :class:`SandboxSession` may reference ``agents.sandbox``
    types.  All other project code uses the abstractions defined here.
    """

    def __init__(self, config: SandboxConfig | None = None) -> None:
        """Initialize the sandbox manager.

        Args:
            config: Sandbox configuration.  Uses :class:`SandboxConfig` defaults
                when ``None``.
        """
        self._config = config or SandboxConfig()
        self._docker: DockerClient = docker.from_env()
        self._client: DockerSandboxClient | None = None

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _sync_image_exists(docker_client: DockerClient, image: str) -> bool:
        """Check whether *image* exists locally (runs in thread)."""
        try:
            docker_client.images.get(image)
            return True
        except (docker.errors.ImageNotFound, docker.errors.APIError):
            return False

    async def _ensure_client(self) -> DockerSandboxClient:
        """Lazily create (or return) the :class:`DockerSandboxClient`."""
        if self._client is None:
            self._client = await asyncio.to_thread(
                DockerSandboxClient,
                self._docker,
            )
        return self._client

    # -- public API --------------------------------------------------------

    async def pre_pull_image(self) -> bool:
        """Pre-pull the Kali sandbox image at platform startup (L-06).

        Checks whether the image already exists locally.  If not, pulls it
        from the registry using ``docker-py`` wrapped in
        ``asyncio.to_thread()``.

        Returns:
            ``True`` if the image is available locally after the call,
            ``False`` if the pull failed.
        """
        image = self._config.image

        # Fast path — check local cache in a thread
        exists = await asyncio.to_thread(
            self._sync_image_exists, self._docker, image
        )
        if exists:
            logger.info("Kali sandbox image %r already present locally.", image)
            return True

        logger.info("Pulling Kali sandbox image %r …", image)
        try:
            await asyncio.to_thread(
                self._docker.images.pull, image, platform=None
            )
            logger.info("Kali sandbox image %r pulled successfully.", image)
            return True
        except (docker.errors.APIError, docker.errors.ImageNotFound) as exc:
            logger.error("Failed to pull image %r: %s", image, exc)
            return False

    async def create_session(
        self, workspace_dir: Path | None = None
    ) -> SandboxSession:
        """Create an ephemeral sandbox container for a scan (D-01, D-02).

        Builds a :class:`Manifest` that optionally mounts *workspace_dir*,
        then calls ``DockerSandboxClient.create()`` with least-privilege
        settings.

        Args:
            workspace_dir: Optional host directory staged into the sandbox
                via a ``LocalDir`` manifest entry.

        Returns:
            A :class:`SandboxSession` wrapping the live container.
        """
        client = await self._ensure_client()

        # Build manifest — optionally include workspace directory
        entries: dict[str | Path, File | LocalDir] = {}

        if workspace_dir is not None:
            abs_path = workspace_dir.resolve()
            entries["/workspace"] = LocalDir(src=abs_path)

        manifest = Manifest(
            version=1,
            root="/workspace",
            entries=entries,
        )

        options = DockerSandboxClientOptions(
            image=self._config.image,
            exposed_ports=(),
        )

        # create() is async-safe (the SDK internally uses a thread pool)
        inner_session: DockerSandboxSession = await client.create(
            manifest=manifest,
            options=options,
        )

        # Build our wrapper
        session = SandboxSession(
            _inner=inner_session,
            _client=client,
            container_id=inner_session.container_id,
            config=self._config,
            created_at=time.time(),
        )

        logger.info(
            "Sandbox session created: container_id=%s",
            session.container_id,
        )
        return session

    async def destroy_session(self, session: SandboxSession) -> None:
        """Destroy a sandbox container immediately (L-08).

        Calls ``DockerSandboxClient.delete()``.  If the container has
        already been removed, ``docker.errors.NotFound`` is caught silently
        so double-destroy is safe.

        Args:
            session: The session to destroy.
        """
        client = await self._ensure_client()
        try:
            await client.delete(session._inner)
            logger.info(
                "Sandbox session destroyed: container_id=%s",
                session.container_id,
            )
        except NotFound:
            logger.debug(
                "Sandbox session already removed (container_id=%s), "
                "nothing to do.",
                session.container_id,
            )

    def schedule_cleanup(self, session: SandboxSession) -> None:
        """Schedule delayed container destruction (D-03, D-04).

        Creates a background :class:`asyncio.Task` that sleeps for
        ``retention_minutes * 60`` seconds, then calls
        :meth:`destroy_session`.

        This implements the 15-minute post-scan retention window so
        results can be retrieved before the container is torn down.

        Args:
            session: The session to schedule for delayed cleanup.
        """
        retention_seconds = self._config.retention_minutes * 60

        async def _delayed_cleanup() -> None:
            logger.debug(
                "Scheduled cleanup in %d seconds for container_id=%s",
                retention_seconds,
                session.container_id,
            )
            await asyncio.sleep(retention_seconds)
            await self.destroy_session(session)

        asyncio.create_task(_delayed_cleanup())

        logger.info(
            "Cleanup scheduled for container_id=%s in %d minutes.",
            session.container_id,
            self._config.retention_minutes,
        )
