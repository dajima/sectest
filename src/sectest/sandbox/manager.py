"""SandboxManager abstraction layer (T3 — to be fully implemented).

Wraps all ``agents.sandbox`` API calls. This is the ONLY file in the
project that may import from ``agents.sandbox`` (L-01, L-02).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SandboxConfig:
    """Configuration for a Kali sandbox container."""

    image: str = "sectest/kali-sandbox:latest"
    capabilities: tuple[str, ...] = ("NET_ADMIN", "NET_RAW", "SYS_PTRACE")
    memory_limit: str = "2g"
    cpu_limit: float = 2.0
    retention_minutes: int = 15


@dataclass
class ExecResult:
    """Structured command output (L-07)."""

    stdout: str
    stderr: str
    exit_code: int
    command: str
    duration_ms: float


@dataclass
class SandboxSession:
    """Opaque handle to an active sandbox session."""

    _inner: object  # DockerSandboxSession (opaque)
    _client: object  # DockerSandboxClient (opaque)
    container_id: str
    config: SandboxConfig
    created_at: float

    async def exec(self, command: str, timeout: float | None = None) -> ExecResult:
        """Execute a shell command in the sandbox."""
        raise NotImplementedError("SandboxSession.exec() — implement in T3")


class SandboxManager:
    """Manages Kali Linux Docker sandbox lifecycle (L-02)."""

    def __init__(self, config: SandboxConfig | None = None) -> None:
        self._config = config or SandboxConfig()

    async def pre_pull_image(self) -> bool:
        """Pre-pull Kali image at platform startup (L-06)."""
        raise NotImplementedError("SandboxManager.pre_pull_image() — implement in T3")

    async def create_session(self) -> SandboxSession:
        """Create ephemeral sandbox for a scan (D-01, D-02)."""
        raise NotImplementedError("SandboxManager.create_session() — implement in T3")

    async def destroy_session(self, session: SandboxSession) -> None:
        """Destroy sandbox immediately (L-08)."""
        raise NotImplementedError("SandboxManager.destroy_session() — implement in T3")

    async def schedule_cleanup(self, session: SandboxSession) -> None:
        """Schedule delayed destruction (D-03, D-04)."""
        raise NotImplementedError("SandboxManager.schedule_cleanup() — implement in T3")
