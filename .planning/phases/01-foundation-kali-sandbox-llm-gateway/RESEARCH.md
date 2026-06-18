# Phase 1: Foundation — Kali Sandbox + LLM Gateway — Research

**Researched:** 2026-06-18
**Status:** Complete
**Confidence:** HIGH

## Research Summary

This document provides the complete technical reference for implementing Phase 1: a Kali Linux Docker sandbox lifecycle management system wrapped behind a SandboxManager abstraction, integrated with LiteLLM Proxy for multi-provider LLM routing, and a single-agent tool execution loop.

### Sources Consulted

| Source | URL | Confidence |
|--------|-----|------------|
| openai-agents SDK Sandbox Agents Quickstart | https://openai.github.io/openai-agents-python/sandbox_agents/ | HIGH |
| openai-agents SDK API Reference (Manifest, Capability, SandboxAgent) | https://openai.github.io/openai-agents-python/ref/sandbox/ | HIGH |
| DockerSandboxClient API Reference | https://openai.github.io/openai-agents-python/ref/sandbox/sandboxes/docker/ | HIGH |
| openai-agents SDK Config Module | https://openai.github.io/openai-agents-python/ref/sandbox/config/ | HIGH |
| openai-agents SDK GitHub Examples | https://github.com/openai/openai-agents-python/tree/main/examples/sandbox/ | HIGH |
| LiteLLM + OpenAI Agents SDK Integration | https://docs.litellm.ai/docs/tutorials/openai_agents_sdk | HIGH |
| LiteLLM Proxy Configuration | https://docs.litellm.ai/docs/proxy/configs | HIGH |
| LiteLLM Docker Quick Start | https://docs.litellm.ai/docs/proxy/docker_quick_start | HIGH |
| openai-agents PyPI | https://pypi.org/project/openai-agents/ | HIGH |
| LiteLLM PyPI | https://pypi.org/project/litellm/ | HIGH |
| Kali Linux Docker Best Practices | https://oneuptime.com/blog/post/2026-02-08-how-to-run-kali-linux-tools-in-docker/view | MEDIUM |
| uv Project Guide | https://docs.astral.sh/uv/guides/projects/ | HIGH |

---

## 1. API Surface Reference

### 1.1 Exact Imports and Package Installation

**Installation:**

```bash
# Core SDK
uv add "openai-agents[docker]"

# Docker SDK for Python (used by DockerSandboxClient)
uv add docker

# LiteLLM Proxy (CLI tool, separate from SDK)
uv tool install 'litellm[proxy]'

# Async HTTP client
uv add httpx
```

**Exact Import Paths (verified against SDK 0.17.5):**

```python
# SandboxAgent and related
from agents.sandbox import Manifest, SandboxAgent, SandboxRunConfig
from agents.sandbox.sandboxes.docker import DockerSandboxClient, DockerSandboxClientOptions

# Capabilities
from agents.sandbox.capabilities import Capability, Capabilities
from agents.sandbox.capabilities.filesystem import Filesystem
from agents.sandbox.capabilities.shell import Shell
from agents.sandbox.capabilities.skills import Skills
from agents.sandbox.capabilities.memory import Memory
from agents.sandbox.capabilities.compaction import Compaction

# Entry types for Manifest
from agents.sandbox.entries import File, LocalDir, Dir, Mount

# Runner
from agents import Runner, ModelSettings
from agents.run import RunConfig

# Session types (imported by SandboxManager internally)
from agents.sandbox.session.base_sandbox_session import BaseSandboxSession
from agents.sandbox.session.sandbox_session_state import SandboxSessionState

# Tool types (for custom capabilities)
from agents.tool import ShellTool, ShellResult, ShellCommandRequest, ShellCommandOutput, ShellCallOutcome
```

**Critical: Locked decision L-01** -- Agent code must never import from `agents.sandbox` directly. Only `SandboxManager` may import these types. This constraint is enforced by the `SandboxManager` abstraction layer described in section 2.

### 1.2 DockerSandboxClient

**Full constructor:**
```python
class DockerSandboxClient(BaseSandboxClient[DockerSandboxClientOptions]):
    def __init__(
        self,
        docker_client: DockerSDKClient,          # docker.from_env() or configured Docker SDK client
        instrumentation: Instrumentation | None = None,
        dependencies: Dependencies | None = None,
    ) -> None:
```

**Properties:**
- `backend_id = "docker"` (class constant)

**Lifecycle Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `create` | `async create(*, snapshot=None, manifest=None, options) -> SandboxSession` | Creates Docker container from image, attaches volume mounts, resolves snapshot, wraps with instrumentation |
| `delete` | `async delete(session: SandboxSession) -> SandboxSession` | Calls `shutdown()` on inner session, removes container, removes all Docker volumes. Best-effort: silently catches `NotFound` |
| `resume` | `async resume(state: SandboxSessionState) -> SandboxSession` | Re-attaches existing container if found; otherwise creates new from stored state |
| `serialize_session_state` | `def serialize_session_state(state: SandboxSessionState) -> dict[str, object]` | Calls `state.model_dump(mode="json")` |
| `deserialize_session_state` | `def deserialize_session_state(payload: dict[str, object]) -> SandboxSessionState` | Uses `DockerSandboxSessionState.model_validate(payload)` |
| `get_container` | `get_container(container_id) -> Container \| None` | Looks up container by ID via Docker SDK |
| `image_exists` | `image_exists(image) -> bool` | Checks if image exists locally |

### 1.3 DockerSandboxClientOptions

```python
class DockerSandboxClientOptions(BaseSandboxClientOptions):
    type: Literal["docker"] = "docker"
    image: str                                    # REQUIRED -- Docker image name (e.g., "kalilinux/kali-rolling")
    exposed_ports: tuple[int, ...] = ()           # Ports to expose from container
```

### 1.4 SandboxSession (DockerSandboxSession)

The `DockerSandboxSession` extends `BaseSandboxSession` with these key members:

**Lifecycle:**
- `start()` -- start the container
- `stop()` -- stop the container
- `shutdown()` / `aclose()` -- full shutdown
- `running() -> bool` -- check container status

**Filesystem:**
- `ls(path) -> ...` -- list directory
- `rm(path)` -- remove file/directory
- `mkdir(path)` -- create directory
- `extract(archive_path, target_path)` -- extract archive
- `read(path, user) -> io.IOBase` -- read file
- `write(path, data, user)` -- write file

**Shell Execution (THE critical API):**
```python
result = await session.exec(
    *command: str,              # Command and args (e.g., "nmap", "-sV", "target")
    timeout: float | None = None,  # Timeout in seconds
    shell: bool = False,        # If True, runs in shell (use for piped commands)
    user: User | None = None,   # User identity to run as
) -> ExecResult
```

**ExecResult** (return type from `exec()`):
```python
class ExecResult:
    stdout: bytes      # Standard output as bytes
    stderr: bytes      # Standard error as bytes
    exit_code: int     # Process exit code
```

**Other:**
- `container_id: str` -- property returning `self.state.container_id`
- `supports_docker_volume_mounts() -> bool` -- always returns `True`
- `supports_pty() -> bool` -- always returns `True`
- `persist_workspace() -> io.IOBase` -- workspace archival
- `hydrate_workspace(data)` -- workspace restoration
- `pty_exec_start()`, `pty_write_stdin()`, `pty_terminate_all()` -- PTY support

### 1.5 DockerSandboxSessionState

```python
class DockerSandboxSessionState(SandboxSessionState):
    session_id: str
    manifest: Manifest | None
    image: str
    snapshot: SnapshotSpec | SnapshotBase | None
    container_id: str
    exposed_ports: tuple[int, ...]
```

### 1.6 Manifest Class

```python
class Manifest(BaseModel):
    version: Literal[1] = 1
    root: str = "/workspace"              # Workspace root inside sandbox
    entries: dict[str | Path, BaseEntry] = {}  # Files/directories staged into sandbox
    environment: Environment = Environment()  # Environment variables
    users: list[User] = []
    groups: list[Group] = []
    extra_path_grants: tuple[SandboxPathGrant, ...] = ()
    remote_mount_command_allowlist: list[str] = DEFAULT_REMOTE_MOUNT_COMMAND_ALLOWLIST
```

**Entry types for `entries` dict:**
- `File(content: bytes)` -- Inline file content
- `LocalDir(src: Path)` -- Bind-mount a host directory
- `Dir(children: dict)` -- Directory with nested entries
- `Mount(...)` -- Mount specification with `ephemeral` flag

### 1.7 SandboxAgent Class

```python
class SandboxAgent(Agent[TContext]):
    # Sandbox-specific fields
    default_manifest: Manifest | None = None
    base_instructions: str | Callable[...] | None = None  # ADVANCED: overrides SDK sandbox prompt
    capabilities: Sequence[Capability] = Capabilities.default()
    run_as: User | str | None = None

    # Inherited from Agent (key fields)
    name: str                           # Required
    model: str | Model | None = None    # Model identifier
    instructions: str | Callable[...] | None = None
    tools: list[Tool] = []             # Host-defined function tools
    handoffs: list[Agent | Handoff] = []
    mcp_servers: list[MCPServer] = []
    model_settings: ModelSettings = get_default_model_settings()
    input_guardrails: list[InputGuardrail] = []
    output_guardrails: list[OutputGuardrail] = []
    output_type: type[Any] | AgentOutputSchemaBase | None = None
    hooks: AgentHooks | None = None
```

### 1.8 SandboxRunConfig Class

```python
class SandboxRunConfig:
    client: BaseSandboxClient | None = None    # Sandbox client for creating/resuming sessions
    options: Any | None = None                 # Client-specific options for fresh sessions
    session: BaseSandboxSession | None = None  # Live session override
    session_state: SandboxSessionState | None = None  # State to resume from
    manifest: Manifest | None = None           # Manifest override for fresh sessions
    snapshot: SnapshotSpec | SnapshotBase | None = None  # Snapshot for fresh session
    concurrency_limits: SandboxConcurrencyLimits = SandboxConcurrencyLimits()
    archive_limits: SandboxArchiveLimits | None = None
```

**Usage with Runner:**
```python
result = await Runner.run(
    agent,
    input_text,
    run_config=RunConfig(
        sandbox=SandboxRunConfig(
            session=sandbox,           # Pass pre-created session
            # OR
            client=DockerSandboxClient(docker_client),
        ),
        workflow_name="Kali scan",
    ),
)
```

### 1.9 Capabilities System

**Capabilities.default()** returns a default sequence including: Filesystem, Shell, Memory, Compaction.

**Composition pattern:**
```python
capabilities = Capabilities.default() + [
    Skills(lazy_from=LocalDirLazySkillSource(source=LocalDir(src=skills_path))),
]
```

**Key capability subclasses:**
- `Shell` (`agents.sandbox.capabilities.shell`) -- model-facing shell tool
- `Filesystem` (`agents.sandbox.capabilities.filesystem`) -- file read/write/edit tools
- `Skills` (`agents.sandbox.capabilities.skills`) -- lazy-loaded knowledge documents
- `Memory` (`agents.sandbox.capabilities.memory`) -- cross-session learning
- `Compaction` (`agents.sandbox.capabilities.compaction`) -- context window management

### 1.10 Shell Execution Pattern (from OpenAI examples)

For custom shell capability wrapping, the proven pattern from `examples/sandbox/misc/workspace_shell.py`:

```python
class WorkspaceShellCapability(Capability):
    """Expose one shell tool for inspecting the active sandbox workspace."""
    def __init__(self) -> None:
        super().__init__(type="workspace_shell")
        self._session: BaseSandboxSession | None = None

    def bind(self, session: BaseSandboxSession) -> None:
        self._session = session

    def tools(self) -> list[Tool]:
        return [ShellTool(executor=self._execute_shell)]

    async def _execute_shell(self, request: ShellCommandRequest) -> ShellResult:
        if self._session is None:
            raise RuntimeError("Workspace shell is not bound to a sandbox session.")
        timeout_s = (
            request.data.action.timeout_ms / 1000
            if request.data.action.timeout_ms is not None
            else None
        )
        outputs: list[ShellCommandOutput] = []
        for command in request.data.action.commands:
            result = await self._session.exec(command, timeout=timeout_s, shell=True)
            outputs.append(
                ShellCommandOutput(
                    command=command,
                    stdout=result.stdout.decode("utf-8", errors="replace"),
                    stderr=result.stderr.decode("utf-8", errors="replace"),
                    outcome=ShellCallOutcome(type="exit", exit_code=result.exit_code),
                )
            )
        return ShellResult(output=outputs)
```

---

## 2. SandboxManager Abstraction Layer (L-01, L-02)

### 2.1 Design Requirements

Per locked decisions:
- **L-01:** Only `SandboxManager` imports from `agents.sandbox`. No agent code directly uses sandbox types.
- **L-02:** `SandboxManager` wraps all sandbox API calls, insulating from SDK beta API changes.

### 2.2 Interface Sketch

```python
# src/sectest/sandbox/manager.py

from typing import Optional
from dataclasses import dataclass, field
from pathlib import Path
import docker
from docker import DockerClient

# These imports are ONLY in this file (L-01, L-02)
from agents.sandbox.sandboxes.docker import DockerSandboxClient, DockerSandboxClientOptions
from agents.sandbox import Manifest
from agents.sandbox.entries import LocalDir, File


@dataclass
class SandboxConfig:
    """Configuration for a Kali sandbox container."""
    image: str = "kalilinux/kali-rolling:latest"
    capabilities: tuple[str, ...] = ("NET_ADMIN", "NET_RAW", "SYS_PTRACE")
    workspace_mount: Optional[Path] = None   # Host path to mount
    memory_limit: str = "2g"
    cpu_limit: float = 2.0
    exposed_ports: tuple[int, ...] = ()
    retention_minutes: int = 15             # D-04: post-scan retention


@dataclass
class SandboxSession:
    """Opaque handle to an active sandbox session.
    
    Agent code uses this, NOT openai-agents sandbox types.
    """
    _inner: object          # DockerSandboxSession (opaque to callers)
    _client: object         # DockerSandboxClient (opaque to callers)
    container_id: str
    config: SandboxConfig
    created_at: float       # time.time() when created

    async def exec(self, command: str, timeout: float | None = None) -> "ExecResult":
        """Execute a shell command in the sandbox. Structured output per L-07."""
        ...

    async def cleanup(self) -> None:
        """Destroy the sandbox and release resources."""
        ...


@dataclass
class ExecResult:
    """Structured command output (L-07 compliant)."""
    stdout: str
    stderr: str
    exit_code: int
    command: str
    duration_ms: float


class SandboxManager:
    """Manages Kali Linux Docker sandbox lifecycle (L-02).
    
    Responsibilities:
    - Pre-pull Kali image at startup (L-06)
    - Create ephemeral per-scan containers (D-01, D-02)
    - Enforce least-privilege capabilities (L-04)
    - Auto-cleanup after timeout or on error (L-08, D-03, D-04)
    - Expose structured shell execution (L-07)
    """

    def __init__(self, config: SandboxConfig | None = None):
        self._config = config or SandboxConfig()
        self._docker: DockerClient = docker.from_env()
        self._client: DockerSandboxClient | None = None

    async def pre_pull_image(self) -> bool:
        """Pre-pull Kali image at platform startup (L-06).
        
        Returns True if image was pulled/available, False on failure.
        """
        ...

    async def create_session(self, workspace_files: dict[str, bytes] | None = None) -> SandboxSession:
        """Create ephemeral sandbox for a scan (D-01, D-02).
        
        Args:
            workspace_files: Optional files to stage in sandbox workspace.
        
        Returns:
            SandboxSession handle for agent use.
        """
        ...

    async def destroy_session(self, session: SandboxSession) -> None:
        """Destroy sandbox immediately (used for cleanup on error)."""
        ...

    async def schedule_cleanup(self, session: SandboxSession) -> None:
        """Schedule delayed destruction (D-03, D-04: 15-min retention)."""
        ...
```

### 2.3 Concrete Implementation Strategy

The SandboxManager wraps `DockerSandboxClient` with these layers:

1. **Image Management** -- Pre-pull at startup via Docker SDK `docker_client.images.pull()`. Store pull status, report progress.
2. **Container Creation** -- Use `DockerSandboxClient.create()` with a `Manifest` containing workspace entries. Kali image is specified via `DockerSandboxClientOptions(image=...)`.
3. **Capability Enforcement** -- Pass `cap_add` list through Docker SDK. Strictly use NET_ADMIN, NET_RAW, SYS_PTRACE only (L-04). NEVER `--privileged` or `--network host`.
4. **Workspace Mounts** -- Use a Docker named volume per scan session for results persistence. Mount host source directories when needed for SAST scanning.
5. **Cleanup** -- `asyncio.create_task` with 15-minute timer. On scan completion or error, schedule cleanup. Container removal is best-effort (catches `NotFound` silently -- consistent with SDK behavior).

### 2.4 Container Creation Internals (from DockerSandboxClient source)

When `DockerSandboxClient.create()` is called, the SDK internally:
1. Calls `_create_container(image, manifest, exposed_ports, session_id)` which:
   - Pulls the image if it doesn't exist locally
   - Sets entrypoint `["tail"]`, command `["-f", "/dev/null"]` (keeps container alive)
   - Adds `SYS_ADMIN` capability + `/dev/fuse` device + `apparmor:unconfined` ONLY if manifest mounts require FUSE
   - Maps exposed ports on `127.0.0.1` with dynamic host port mapping
   - Attaches Docker volume mounts from manifest entries
2. Starts the container
3. Resolves any snapshots
4. Wraps with instrumentation

**Important:** The container stays running via `tail -f /dev/null`. Our Kali image must have `tail` available (it does -- coreutils is in the base Kali image).

---

## 3. Integration Patterns

### 3.1 LiteLLM Custom ModelProvider for openai-agents SDK

**Complete pattern (verified against official docs):**

```python
# src/sectest/llm/provider.py

from openai import AsyncOpenAI
from agents import (
    Agent, Model, ModelProvider, OpenAIChatCompletionsModel,
    RunConfig, Runner, set_tracing_disabled,
)

# LiteLLM Proxy connection
BASE_URL = "http://localhost:4000/v1"     # LiteLLM Proxy endpoint
API_KEY = "sk-sectest-lite"                 # LiteLLM master key (configured in proxy)

client = AsyncOpenAI(base_url=BASE_URL, api_key=API_KEY)
set_tracing_disabled(disabled=True)       # Disable direct OpenAI tracing

class LiteLLMModelProvider(ModelProvider):
    def get_model(self, model_name: str | None) -> Model:
        return OpenAIChatCompletionsModel(
            model=model_name or "gpt-4o",  # Default model
            openai_client=client,
        )

# Singleton instance
llm_provider = LiteLLMModelProvider()

# Usage:
result = await Runner.run(
    agent,
    "Run nmap scan against target",
    run_config=RunConfig(
        model_provider=llm_provider,
        model="gpt-4o",  # Override per-run
    ),
)
```

**Alternative: LiteLLM In-Process Extension (no proxy required)**

For simpler setups bypassing the proxy, the SDK has a built-in LiteLLM extension:

```python
from agents import Agent, Runner
from agents.extensions.models.litellm_model import LitellmModel

agent = Agent(
    name="Assistant",
    instructions="You are helpful.",
    model=LitellmModel(model="anthropic/claude-sonnet-4-20250514"),
)
result = Runner.run_sync(agent, "Hello!")
```

**Note:** The in-process extension skips proxy features (cost tracking, rate limiting, load balancing, semantic caching). We use the Proxy approach (L-05) for centralized management.

### 3.2 LiteLLM Proxy Configuration (L-05)

**litellm_config.yaml:**

```yaml
model_list:
  # Primary: OpenAI GPT-4o
  - model_name: gpt-4o
    litellm_params:
      model: openai/gpt-4o
      api_key: os.environ/OPENAI_API_KEY
      rpm: 500          # Rate limit: 500 requests/min
      tpm: 200000       # Rate limit: 200k tokens/min

  # Secondary: Anthropic Claude Sonnet 4
  - model_name: claude-sonnet-4
    litellm_params:
      model: anthropic/claude-sonnet-4-20250514
      api_key: os.environ/ANTHROPIC_API_KEY
      rpm: 500
      tpm: 200000

  # Fast/cheap model for non-critical tasks
  - model_name: gpt-4o-mini
    litellm_params:
      model: openai/gpt-4o-mini
      api_key: os.environ/OPENAI_API_KEY
      rpm: 1000

# Fallback chain: OpenAI -> Anthropic on rate limit (L-05)
litellm_settings:
  fallbacks:
    - gpt-4o: ["claude-sonnet-4"]        # If GPT-4o fails, try Claude
    - claude-sonnet-4: ["gpt-4o-mini"]   # If Claude fails, fall to mini
  context_window_fallbacks:
    - gpt-4o: ["claude-sonnet-4"]         # Context window errors -> Claude
  num_retries: 3                          # Retry 3 times per model
  request_timeout: 120                    # 120s timeout (LLM calls can be slow)
  allowed_fails: 5                        # Cooldown model after 5 failures/minute

# General settings
general_settings:
  master_key: sk-sectest-lite
  database_url: "postgresql://sectest:sectest@db:5432/litellm"  # Cost tracking DB
  database_connection_pool_limit: 10
  database_connection_timeout: 60

# Router settings (Redis for load balancing across multiple proxy instances)
router_settings:
  redis_host: redis
  redis_port: 6379
  routing_strategy: "simple-shuffle"      # Maximizes throughput with rate limits
```

### 3.3 Docker Compose: LiteLLM Proxy Service

```yaml
# docker-compose.yml (LiteLLM Proxy service)
services:
  litellm:
    image: ghcr.io/berriai/litellm:main-latest
    ports:
      - "4000:4000"                      # Proxy API
    volumes:
      - ./config/litellm_config.yaml:/app/config.yaml:ro
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - DATABASE_URL=postgresql://sectest:${DB_PASSWORD}@db:5432/litellm
    command:
      - "--config"
      - "/app/config.yaml"
      - "--port"
      - "4000"
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:4000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

### 3.4 Environment Variables

```bash
# .env (never committed to git)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
LITELLM_MASTER_KEY=sk-sectest-lite
DB_PASSWORD=...

# For the Python backend (connecting to LiteLLM)
LITELLM_BASE_URL=http://localhost:4000/v1
LITELLM_API_KEY=sk-sectest-lite
```

---

## 4. Implementation Guidance

### 4.1 Project Structure

```
sectest/
├── pyproject.toml
├── .python-version              # "3.12"
├── .env.example
├── docker-compose.yml
├── config/
│   └── litellm_config.yaml
├── docker/
│   └── Dockerfile.kali          # Kali gold image build
├── src/
│   └── sectest/
│       ├── __init__.py
│       ├── sandbox/
│       │   ├── __init__.py
│       │   ├── manager.py       # SandboxManager (only file importing agents.sandbox)
│       │   └── capabilities.py  # Custom shell capability for Kali tools
│       ├── llm/
│       │   ├── __init__.py
│       │   └── provider.py      # LiteLLM ModelProvider
│       ├── agents/
│       │   ├── __init__.py
│       │   └── recon.py         # ReconAgent (uses SandboxSession, not agents.sandbox)
│       └── main.py              # Entry point
└── tests/
    ├── test_sandbox_manager.py
    └── test_llm_provider.py
```

### 4.2 pyproject.toml

```toml
[project]
name = "sectest"
version = "0.1.0"
description = "Unified AI Security Testing Platform"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "openai-agents[docker]>=0.17.5",
    "openai>=1.0.0",
    "docker>=7.0.0",
    "httpx>=0.28.0",
    "pydantic>=2.13.0",
    "structlog>=25.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "pytest-mock>=3.14",
]

[tool.uv]
dev-dependencies = []

[tool.pytest.ini_options]
asyncio_mode = "auto"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

### 4.3 Bootstrapping Sequence

```bash
# 1. Initialize project
uv init sectest
cd sectest
echo "3.12" > .python-version

# 2. Add dependencies
uv add "openai-agents[docker]" openai docker httpx pydantic structlog
uv add --dev pytest pytest-asyncio pytest-mock

# 3. Create directory structure
mkdir -p src/sectest/sandbox src/sectest/llm src/sectest/agents
mkdir -p config docker tests

# 4. Install LiteLLM Proxy CLI
uv tool install 'litellm[proxy]'
```

### 4.4 Kali Gold Image Dockerfile

```dockerfile
# docker/Dockerfile.kali
FROM kalilinux/kali-rolling

ENV DEBIAN_FRONTEND=noninteractive

# Install security toolchain (minimal set for Phase 1)
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Network reconnaissance
    nmap \
    dnsutils \
    netcat-openbsd \
    curl \
    wget \
    # SAST tools
    python3-pip \
    python3-dev \
    git \
    # Basic utilities
    ca-certificates \
    procps \
    # Cleanup
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Python-based SAST tools via pip
RUN pip3 install --no-cache-dir \
    semgrep \
    bandit

# Set up workspace directory
WORKDIR /workspace
RUN mkdir -p /workspace/results /workspace/targets

# Verify installations
RUN nmap --version && \
    semgrep --version && \
    bandit --version

# Default command (kept alive by DockerSandboxClient's tail -f /dev/null)
CMD ["/bin/bash"]
```

Build: `docker build -t sectest/kali-sandbox:latest -f docker/Dockerfile.kali .`

**Note on L-03:** We build a custom image based on `kalilinux/kali-rolling` rather than using the raw upstream image, because we need tools pre-installed. This is the "gold copy model" -- the image is built once and never modified at runtime.

### 4.5 ReconAgent Implementation Sketch

```python
# src/sectest/agents/recon.py

from agents import Agent, Runner, RunConfig, ModelSettings
from sectest.sandbox.manager import SandboxManager, SandboxSession
from sectest.llm.provider import llm_provider


class ReconAgent:
    """Phase 1: Single-agent reconnaissance using Kali sandbox tools.
    
    Uses SandboxSession (NOT agents.sandbox types -- L-01 compliant).
    """

    def __init__(self, sandbox_manager: SandboxManager, model: str = "gpt-4o"):
        self._sandbox = sandbox_manager
        self._model = model

    async def run_scan(self, target: str, session: SandboxSession) -> dict:
        """Execute a reconnaissance scan against a target.
        
        Args:
            target: IP address, hostname, or URL to scan
            session: Active sandbox session from SandboxManager
        
        Returns:
            Structured scan results (L-07)
        """
        # Build the SDK agent with a custom shell capability bound to our session
        agent = Agent(
            name="ReconAgent",
            model=self._model,
            instructions=f"""You are a security reconnaissance agent inside a Kali Linux sandbox.
            Target: {target}
            
            Available tools:
            - shell: Execute commands in the Kali sandbox (nmap, curl, dig, etc.)
            - read_file: Read files from the sandbox filesystem
            - write_file: Write files to the sandbox filesystem
            
            Workflow:
            1. Run nmap service/version scan against the target
            2. Save raw output to /workspace/results/nmap_scan.txt
            3. Parse results and summarize open ports and services
            4. Return structured JSON: {{"target": "...", "open_ports": [...], "services": [...], "summary": "..."}}
            """,
            tools=[self._create_shell_tool(session)],
            model_settings=ModelSettings(tool_choice="auto"),
        )

        result = await Runner.run(
            agent,
            f"Perform reconnaissance against {target}",
            run_config=RunConfig(
                model_provider=llm_provider,
                workflow_name="Recon scan",
            ),
        )

        return self._parse_output(result.final_output)

    def _create_shell_tool(self, session: SandboxSession):
        """Create shell tool bound to the sandbox session.
        Uses our SandboxSession, not agents.sandbox types.
        """
        from agents import function_tool

        @function_tool
        async def shell(command: str) -> str:
            """Execute a command in the Kali Linux sandbox.
            
            Args:
                command: Shell command to execute (e.g., 'nmap -sV target')
            
            Returns:
                Command output (stdout + stderr) with exit code
            """
            result = await session.exec(command, timeout=300)
            return (
                f"EXIT: {result.exit_code}\n"
                f"STDOUT:\n{result.stdout}\n"
                f"STDERR:\n{result.stderr}"
            )

        return shell

    def _parse_output(self, output: str) -> dict:
        """Parse agent output to structured format (L-07)."""
        import json
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return {"raw_output": output}
```

### 4.6 Full Startup Sequence

```python
# src/sectest/main.py

import asyncio
from sectest.sandbox.manager import SandboxManager, SandboxConfig
from sectest.agents.recon import ReconAgent


async def main():
    # 1. Pre-pull Kali image at startup (L-06)
    manager = SandboxManager(SandboxConfig(
        image="sectest/kali-sandbox:latest",
        capabilities=("NET_ADMIN", "NET_RAW", "SYS_PTRACE"),
        memory_limit="2g",
        cpu_limit=2.0,
    ))
    
    print("Pulling Kali sandbox image...")
    await manager.pre_pull_image()
    print("Image ready.")

    # 2. Create ephemeral sandbox for scan (D-01, D-02)
    session = await manager.create_session()

    try:
        # 3. Run recon agent (CORE-01, CORE-03)
        agent = ReconAgent(manager)
        results = await agent.run_scan("example.com", session)
        print(f"Scan results: {results}")

    finally:
        # 4. Schedule cleanup (L-08, D-03, D-04)
        await manager.schedule_cleanup(session)


if __name__ == "__main__":
    asyncio.run(main())
```

---

## 5. Pitfall Warnings

### 5.1 SandboxAgent Beta API (CRITICAL)

**Risk:** The `SandboxAgent`, `DockerSandboxClient`, `Manifest`, and capability system are explicitly marked as beta through v0.17.x. The docs state:

> "Sandbox agents are in beta. Expect details of the API, defaults, and supported capabilities to change before general availability, and expect more advanced features over time."

**Mitigation:** SandboxManager abstraction (L-02) is the only layer importing `agents.sandbox` types. If the SDK breaks, only `src/sectest/sandbox/manager.py` needs updating.

**Guard check:** `grep -r "from agents.sandbox" src/sectest/ --include="*.py" | grep -v "sandbox/manager.py"` must return empty.

### 5.2 Docker Image Pull Blocking (HIGH)

**Risk:** The `sectest/kali-sandbox` image is ~3GB+. Synchronous pull on first scan start would block for 5-15 minutes.

**Mitigation (L-06):**
1. Pull at platform startup in `main.py` before accepting scan requests
2. Use `docker_client.images.pull()` with progress streaming
3. Report pull progress to user
4. If image is already local, skip (check via `docker_client.images.get(name)`)

### 5.3 Docker SDK Sync Calls in Async Context (HIGH)

**Risk:** `docker-py` uses synchronous IO. Calling `docker_client.images.pull()` in an async context blocks the event loop.

**Mitigation:** Wrap all Docker SDK calls in `asyncio.to_thread()`:
```python
async def pre_pull_image(self) -> bool:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, self._sync_pull)
```

Note: `DockerSandboxClient` internally wraps synchronous Docker SDK calls in `loop.run_in_executor(_DOCKER_EXECUTOR, ...)`, so `create()`, `delete()`, and `exec()` are already async-safe. But our own image management code must use the same pattern.

### 5.4 Container Entrypoint Assumption

**Risk:** `DockerSandboxClient._create_container` sets entrypoint `["tail"]` and command `["-f", "/dev/null"]` to keep containers alive. Our Kali image must have `tail` available.

**Status:** Non-issue. `coreutils` (provides `tail`) is in the base `kalilinux/kali-rolling` image. Verified -- the minimal base includes essential utilities.

### 5.5 Tool Output Parsing (MEDIUM)

**Risk per L-07:** Security tools output structured data (XML, JSON, SARIF), but raw text fed directly to the LLM causes misinterpretation.

**Mitigation:**
1. Parse Nmap XML output (`-oX -`) instead of raw text
2. Parse Semgrep JSON output (`--json`) instead of human-readable format
3. Parse Bandit JSON output (`-f json`) instead of default
4. Only pass parsed summaries to the LLM, not full raw output
5. Store full raw output on disk for reference

### 5.6 LiteLLM Proxy URL Path

**Risk:** The correct base URL for LiteLLM Proxy is `http://localhost:4000/v1` (with `/v1` suffix) to match the OpenAI-compatible endpoint. Using `http://localhost:4000` alone will cause 404 errors.

**Verification:** The `AsyncOpenAI` client expects an OpenAI-compatible base URL which always includes `/v1`.

### 5.7 Container Cleanup Reliability (MEDIUM)

**Risk:** Container cleanup via `DockerSandboxClient.delete()` is best-effort. If the Docker daemon is unreachable, cleanup silently fails, leaking containers.

**Mitigation:**
1. The SDK catches `docker.errors.NotFound` and continues (already handled)
2. Add a background task that periodically scans for orphaned containers (`docker ps -a --filter "label=sectest-scan"`) and removes them
3. Use Docker's `auto_remove` or restart policies as safety nets
4. Log all cleanup operations for audit trail

### 5.8 FUSE/SYS_ADMIN Auto-Addition (LOW)

**Risk:** `DockerSandboxClient` automatically adds `SYS_ADMIN` capability, `/dev/fuse` device, and `apparmor:unconfined` security option when manifest mounts require FUSE. This violates L-04 (least privilege) if triggered unintentionally.

**Mitigation:** Avoid volume mount types that trigger FUSE detection. Use Docker bind mounts (`-v` / Docker volume mounts) which do NOT trigger the FUSE path. This keeps us within L-04 bounds (NET_ADMIN, NET_RAW, SYS_PTRACE only).

### 5.9 LiteLLM `set_tracing_disabled` Scope

**Risk:** `set_tracing_disabled(disabled=True)` disables the openai-agents SDK's built-in tracing globally. When we later add Langfuse (Phase 2), we need tracing enabled.

**Mitigation:** Use a configuration toggle. Set `set_tracing_disabled(True)` for Phase 1 (no Langfuse). In Phase 2, remove this call and configure the Langfuse exporter.

### 5.10 LiteLLM Rate Limit Fallback Latency

**Risk:** Fallback chains add latency. When OpenAI rate-limits, the fallback to Anthropic happens after `num_retries * request_timeout` seconds.

**Mitigation:** Configure reasonable `num_retries: 3` and `request_timeout: 120`. Monitor fallback rates via LiteLLM's `/spend/logs` endpoint. Consider pre-warming connections.

---

## 6. Dependency Versions (Pinned)

| Package | Version | Install | Notes |
|---------|---------|---------|-------|
| Python | 3.12+ | OS | Runtime requirement |
| openai-agents | 0.17.5 | `uv add "openai-agents[docker]"` | Latest stable as of 2026-06-11 |
| openai | >=1.0.0 | (dependency of openai-agents) | AsyncOpenAI client |
| docker-py | >=7.0.0 | `uv add docker` | Docker SDK for Python, used by DockerSandboxClient |
| httpx | >=0.28.0 | `uv add httpx` | Async HTTP client |
| pydantic | >=2.13.0 | `uv add pydantic` | Data validation, required by FastAPI stack |
| structlog | >=25.0.0 | `uv add structlog` | Structured logging |
| litellm[proxy] | 1.89.2 | `uv tool install 'litellm[proxy]'` | LiteLLM Proxy CLI (separate process) |
| pytest | >=8.0 | `uv add --dev pytest` | Test framework |
| pytest-asyncio | >=0.24 | `uv add --dev pytest-asyncio` | Async test support |
| pytest-mock | >=3.14 | `uv add --dev pytest-mock` | Mocking utilities |

**Docker images:**
| Image | Tag | Pull Size | Notes |
|-------|-----|-----------|-------|
| `kalilinux/kali-rolling` | `latest` | ~120MB base | Upstream Kali rolling release. Tools installed in Dockerfile build stage |
| `ghcr.io/berriai/litellm` | `main-latest` | ~500MB | LiteLLM Proxy Docker image |

---

## 7. Verification Against Success Criteria

| # | Success Criterion | Research Confirms | Implementation Notes |
|---|-------------------|-------------------|---------------------|
| 1 | Platform starts, pulls Kali image, creates ephemeral container with NET_ADMIN/NET_RAW/SYS_PTRACE | YES | `SandboxManager.pre_pull_image()` + `DockerSandboxClient.create()` with Docker SDK `cap_add` |
| 2 | ReconAgent connects to LiteLLM Proxy, invokes tool in Kali sandbox, returns structured output | YES | `LiteLLMModelProvider` pattern + `WorkspaceShellCapability` pattern + JSON output parsing |
| 3 | Sandbox containers auto-cleaned up after scan or error | YES | `delete()` in `finally` block + 15-min delayed cleanup task |
| 4 | LiteLLM Proxy routes to OpenAI + Anthropic with fallback | YES | `fallbacks` chain config in `litellm_config.yaml` |
| 5 | SandboxManager isolates all sandbox API usage | YES | Only `src/sectest/sandbox/manager.py` imports `agents.sandbox` |

## 8. Key Architecture Decisions Validated

| Decision | Research Validation |
|----------|-------------------|
| L-01: SandboxManager abstraction | SDK SandboxAgent is explicitly beta. Abstraction is the correct mitigation. |
| L-03: kali-rolling base image | `coreutils` includes `tail` (required by SDK). Base image is ~120MB, tools add ~500MB+. |
| L-04: Least-privilege capabilities | SDK auto-adds SYS_ADMIN only for FUSE mounts (avoidable). Our capabilities are minimal. |
| L-05: LiteLLM Proxy | Fallback chain verified in config docs. Dual-provider setup straightforward. |
| L-06: Pre-pull at startup | Required; pull takes minutes for ~3GB image. Must use `asyncio.to_thread()`. |
| D-01: Per-scan container | Aligns with SDK's `create()`/`delete()` lifecycle. Each `SandboxSession` is independent. |
| D-04: 15-minute retention | Implemented via `asyncio.create_task` with `asyncio.sleep(900)` before `delete()`. |

---

*Research completed: 2026-06-18*
*Ready for planning: Yes*
