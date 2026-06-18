"""Kali Linux Docker sandbox management.

Provides the SandboxManager abstraction layer that wraps all
``agents.sandbox`` API calls behind a stable interface (L-01, L-02).

Only ``manager.py`` in this package may import from ``agents.sandbox``.
All other code uses the types exported here:

    - :class:`SandboxManager` — lifecycle management for sandbox containers
    - :class:`SandboxConfig` — configuration dataclass
    - :class:`SandboxSession` — opaque handle to an active container
    - :class:`ExecResult` — structured command output
"""

from sectest.sandbox.manager import (
    ExecResult,
    SandboxConfig,
    SandboxManager,
    SandboxSession,
)

__all__ = [
    "SandboxManager",
    "SandboxConfig",
    "SandboxSession",
    "ExecResult",
]
