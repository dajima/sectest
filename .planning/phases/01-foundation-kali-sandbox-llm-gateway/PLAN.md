# Phase 1: Foundation — Kali Sandbox + LLM Gateway — PLAN

**Planned:** 2026-06-18
**Status:** Ready for execution
**Confidence:** HIGH
**Mode:** MVP (each task delivers usable end-to-end capability)
**Phase:** 1 of 7

---

## 1. Goal

Phase 1 delivers the core agent-sandbox-tool execution loop: the platform provisions least-privilege Kali Linux Docker containers, routes LLM calls through LiteLLM Proxy with dual-provider fallback (OpenAI + Anthropic), runs a single ReconAgent that executes security tools (Nmap/Semgrep) inside the sandbox, returns structured output, and streams real-time progress as structured JSON lines to stdout. Every sandbox API interaction is mediated through a `SandboxManager` abstraction layer that insulates all agent code from the beta `agents.sandbox` API surface.

---

## 2. Requirements Mapping

| Requirement | Phase Coverage | Task Mapping |
|-------------|---------------|--------------|
| **CORE-01** — Docker Kali Linux sandbox lifecycle (image pull, container create/destroy, resource limits, auto-cleanup) | Full | T1 (project scaffold + dependencies), T2 (Kali gold image Dockerfile), T3 (SandboxManager), T7 (image pre-pull + startup sequence) |
| **CORE-03** — LiteLLM Proxy LLM gateway (multi-provider routing, automatic fallback) | Full (cost tracking infrastructure laid; verification deferred to Phase 2) | T4 (LiteLLM config + Docker Compose), T5 (LiteLLM ModelProvider) |

### Requirement Verification Trace

- **CORE-01 verified by:** Success Criteria 1, 3, and 5 (see Section 3)
- **CORE-03 verified by:** Success Criteria 2, 4. Cost tracking infrastructure (provider-level `/spend/logs` in `litellm_config.yaml`) is configured but not validated by an automated test in Phase 1 — full CORE-03 verification completes in Phase 2 when Langfuse trace-based cost attribution per scan is integrated.
- **End-to-end integration verified by:** Success Criterion 2 (ReconAgent connects to LiteLLM, invokes tool in sandbox, returns structured output)

---

## 3. Success Criteria Verification

| # | Success Criterion | Verification Method | Owner Task | Pass Condition |
|---|-------------------|---------------------|------------|----------------|
| 1 | Platform starts, pulls Kali image, creates ephemeral container with NET_ADMIN/NET_RAW/SYS_PTRACE | **Automated test** + manual smoke test | T3, T7 | `test_sandbox_manager.py::test_create_session_capabilities` asserts container capabilities match exactly `["NET_ADMIN", "NET_RAW", "SYS_PTRACE"]`. Manual: run `main.py`, observe image pull progress, container creation log, `docker inspect` on created container shows correct `CapAdd`. |
| 2 | ReconAgent connects to LiteLLM Proxy, invokes tool (Nmap or Semgrep) in Kali sandbox, returns structured output | **Automated integration test** | T6, T8 | `test_recon_agent.py::test_run_scan_with_nmap` creates session via SandboxManager, runs ReconAgent against `localhost`, asserts response contains `{"target": ..., "open_ports": [...], "summary": "..."}`. Test uses mock LLM to avoid API cost; separate manual smoke test with real LLM validates end-to-end. |
| 3 | Scan progress is streamed to stdout as structured JSON lines — each line reports current scan phase (PULL_IMAGE → CREATE_SANDBOX → TOOL_EXEC → PARSE_RESULTS → DONE) with timestamps and status | **Automated test** | T7 | `test_main.py::test_streaming_progress` captures stdout lines during scan, asserts each line is valid JSON with `{"phase": str, "timestamp": str, "status": "running"|"done"|"error"}`. At least one line per phase emitted. End-of-scan line logs `"phase": "DONE", "summary": {...}`. |
| 4 | Sandbox containers auto-cleaned up after scan completion or on error | **Automated test** | T3, T7 | `test_sandbox_manager.py::test_cleanup_after_scan` creates session, calls `destroy_session()`, asserts container not in `docker ps -a`. `test_cleanup_on_error` simulates exception in agent, asserts `finally` block triggers cleanup. `test_scheduled_cleanup` uses `asyncio.sleep(900)` mock to verify 15-min retention timer. |
| 5 | LiteLLM Proxy routes LLM requests to two providers (OpenAI + Anthropic) with automatic fallback on rate limits | **Automated test** + manual verification | T4, T8 | `test_e2e_smoke.py::test_litellm_provider_fallback` uses a mock HTTP server (via `pytest-httpx` or `responses`) that returns 429 for the primary model, then asserts the secondary model is called next. Manual: start LiteLLM Proxy, call `/v1/models`, confirm both `gpt-4o` and `claude-sonnet-4` appear. Optionally trigger real rate limit and verify fallback in LiteLLM logs. |
| 6 | SandboxManager abstraction isolates all sandbox API usage — no agent code imports `agents.sandbox` | **Automated guard check** | T3, T6 | `grep -r "from agents.sandbox" src/sectest/ --include="*.py" \| grep -v "sandbox/manager.py"` returns empty. Enforced as CI/commit hook check. |

---

## 4. Task Breakdown

### T1: Project Scaffold and Dependency Installation

**Title:** Initialize project structure, pyproject.toml, and directory tree

**Description:**
Create the `sectest` Python package skeleton with `uv` as the package manager. Set up the directory structure (`src/sectest/sandbox/`, `src/sectest/llm/`, `src/sectest/agents/`), configure `pyproject.toml` with all Phase 1 dependencies, and create placeholder `__init__.py` files and an `.env.example`.

**Files to create/modify:**
- `d:\AI\pentest_strix\pyproject.toml` — project config with `uv` dependencies (exact versions from RESEARCH.md section 6)
- `d:\AI\pentest_strix\.python-version` — contains `3.12`
- `d:\AI\pentest_strix\.env.example` — template env vars (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `LITELLM_MASTER_KEY`, `LITELLM_BASE_URL`, `LITELLM_API_KEY`)
- `d:\AI\pentest_strix\.gitignore` — Python + Docker + .env patterns
- `d:\AI\pentest_strix\src\sectest\__init__.py` — package init, version `0.1.0`
- `d:\AI\pentest_strix\src\sectest\sandbox\__init__.py` — exports `SandboxManager`, `SandboxConfig`, `SandboxSession`, `ExecResult`
- `d:\AI\pentest_strix\src\sectest\llm\__init__.py` — exports `LiteLLMModelProvider`, `llm_provider`
- `d:\AI\pentest_strix\src\sectest\agents\__init__.py` — exports `ReconAgent`
- `d:\AI\pentest_strix\tests\__init__.py` — test package
- `d:\AI\pentest_strix\tests\conftest.py` — shared fixtures (mock docker, mock LLM, temp config)

**Dependencies:** None (first task)

**Acceptance Criteria:**
- `uv sync` installs all dependencies without error
- `uv run python -c "from sectest import __version__; print(__version__)"` outputs `0.1.0`
- `uv run pytest` runs successfully (0 tests collected, no errors)
- `.env.example` documents all required env vars with placeholder descriptions
- `.gitignore` covers `__pycache__/`, `.env`, `*.pyc`, `venv/`, `.uv/`, `.venv/`

**Estimated effort:** S

---

### T2: Kali Gold Image Dockerfile

**Title:** Build custom Kali Linux Docker image with pre-installed security tools

**Description:**
Create a Dockerfile based on `kalilinux/kali-rolling` that pre-installs the Phase 1 security toolchain (Nmap, Semgrep, Bandit, DNS utilities, curl, wget, netcat, python3-pip, git, ca-certificates, procps). Set up `/workspace` directory with `results/` and `targets/` subdirectories. Include a build script and verify tool installations.

**Files to create/modify:**
- `d:\AI\pentest_strix\docker\Dockerfile.kali` — gold image with Nmap, Semgrep, Bandit, basic Kali tools
- `d:\AI\pentest_strix\docker\build.sh` — one-command build script: `docker build -t sectest/kali-sandbox:latest -f docker/Dockerfile.kali .`
- `d:\AI\pentest_strix\docker\.dockerignore` — exclude unnecessary files from build context

**Dependencies:** T1 (need project root)

**Acceptance Criteria:**
- `bash docker/build.sh` completes successfully and produces `sectest/kali-sandbox:latest` image
- `docker run --rm sectest/kali-sandbox:latest nmap --version` prints version info
- `docker run --rm sectest/kali-sandbox:latest semgrep --version` prints version info
- `docker run --rm sectest/kali-sandbox:latest bandit --version` prints version info
- `docker run --rm sectest/kali-sandbox:latest which tail` outputs `/usr/bin/tail` (required by DockerSandboxClient internals)
- `docker run --rm sectest/kali-sandbox:latest ls /workspace/results /workspace/targets` confirms workspace exists

**Estimated effort:** M (image build takes time)

---

### T3: SandboxManager Abstraction Layer

**Title:** Implement the SandboxManager that wraps all `agents.sandbox` API calls

**Description:**
Implement `SandboxManager`, `SandboxConfig`, `SandboxSession`, and `ExecResult` in `src/sectest/sandbox/manager.py`. This is the **only** file in the entire project that imports from `agents.sandbox`. The `SandboxManager` handles: (1) image pre-pulling via `docker-py` wrapped in `asyncio.to_thread()`, (2) container creation via `DockerSandboxClient.create()` with least-privilege capabilities, (3) shell execution via `session.exec()` mapped through the `SandboxSession` wrapper, (4) container destruction via `DockerSandboxClient.delete()`, (5) scheduled delayed cleanup with 15-minute retention timer.

**Critical:** Must implement `SandboxSession.exec()` as an async method that delegates to `DockerSandboxSession.exec()` and returns `ExecResult` with decoded `str` fields (not `bytes`). Must wrap all `docker-py` sync calls in `asyncio.to_thread()` to avoid blocking the event loop.

**Files to create/modify:**
- `d:\AI\pentest_strix\src\sectest\sandbox\manager.py` — `SandboxConfig`, `SandboxSession`, `ExecResult`, `SandboxManager`
- `d:\AI\pentest_strix\tests\test_sandbox_manager.py` — unit tests with mocked Docker client and DockerSandboxClient

**Dependencies:** T1 (dependencies installed), T2 (image available for integration tests)

**Acceptance Criteria:**
- `SandboxConfig` defaults to `sectest/kali-sandbox:latest`, capabilities `("NET_ADMIN", "NET_RAW", "SYS_PTRACE")`, `memory_limit="2g"`, `cpu_limit=2.0`, `retention_minutes=15`
- `SandboxManager.pre_pull_image()` returns `True` if image exists, wraps pull in `asyncio.to_thread()`
- `SandboxManager.create_session()` returns a `SandboxSession` with non-empty `container_id`, calls `DockerSandboxClient.create()` internally
- `SandboxSession.exec("nmap --version", timeout=30)` returns `ExecResult` with `stdout: str`, `stderr: str`, `exit_code: int`, `command: str`, `duration_ms: float`
- `SandboxSession.exec()` calls `self._inner.exec(command, timeout=timeout)` internally, decodes `bytes` to `str` with `errors="replace"`
- `SandboxManager.destroy_session(session)` calls `DockerSandboxClient.delete()`, catches `docker.errors.NotFound` silently, does not raise on double-destroy
- `SandboxManager.schedule_cleanup(session)` creates `asyncio.create_task` that waits `retention_minutes * 60` seconds then calls `destroy_session()`
- `grep -r "from agents.sandbox" src/sectest/ --include="*.py" | grep -v "sandbox/manager.py"` returns empty
- All unit tests pass with mocked Docker: `uv run pytest tests/test_sandbox_manager.py -v`

**Estimated effort:** L (core abstraction, many boundary conditions)

---

### T4: LiteLLM Proxy Configuration and Docker Compose

**Title:** Configure LiteLLM Proxy with dual-provider fallback and Docker Compose service

**Description:**
Create the LiteLLM Proxy configuration (`litellm_config.yaml`) with OpenAI GPT-4o as primary and Anthropic Claude Sonnet 4 as secondary, including fallback chains, rate limits, retry logic, and request timeouts. Create a `docker-compose.yml` that defines the LiteLLM Proxy service with the config mounted, environment variables injected, and healthcheck enabled. Phase 1 runs LiteLLM Proxy in standalone mode (no PostgreSQL/Redis backend — `router_settings.type: basic` in-memory mode). No stub database services in docker-compose.yml; PostgreSQL and Redis are added in Phase 2 when multi-agent state and session persistence require them.

**Files to create/modify:**
- `d:\AI\pentest_strix\config\litellm_config.yaml` — full proxy config with model_list, fallbacks, rate limits, general_settings
- `d:\AI\pentest_strix\docker-compose.yml` — LiteLLM Proxy service (standalone, no DB stubs)
- `d:\AI\pentest_strix\config\docker-compose.override.yml` — local development overrides (debug logging, hot-reload disabled for proxy)
- `d:\AI\pentest_strix\tests\test_litellm_config.py` — config validation tests (schema check, required fields present)

**Dependencies:** T1 (project structure)

**Acceptance Criteria:**
- `litellm_config.yaml` validates against LiteLLM's config schema (run `litellm --config config/litellm_config.yaml --validate` or equivalent)
- Config defines at least 2 models: `gpt-4o` (OpenAI) and `claude-sonnet-4` (Anthropic)
- Config has `fallbacks: gpt-4o: ["claude-sonnet-4"]` and `fallbacks: claude-sonnet-4: ["gpt-4o-mini"]`
- Config sets `num_retries: 3`, `request_timeout: 120`, `allowed_fails: 5`
- `docker compose up litellm` starts without error
- `curl http://localhost:4000/health` returns 200
- `curl http://localhost:4000/v1/models -H "Authorization: Bearer sk-sectest-lite"` returns model list including `gpt-4o` and `claude-sonnet-4`

**Estimated effort:** M (config is straightforward, Docker Compose integration requires iterative testing)

---

### T5: LiteLLM ModelProvider

**Title:** Implement LiteLLM ModelProvider for openai-agents SDK

**Description:**
Implement `LiteLLMModelProvider` in `src/sectest/llm/provider.py` that connects the openai-agents SDK to the LiteLLM Proxy via OpenAI-compatible API. Create a singleton `llm_provider` instance. The provider uses `AsyncOpenAI` client pointed at `http://localhost:4000/v1` with the LiteLLM master key. Disable direct OpenAI tracing (will be replaced by Langfuse in Phase 2).

**Files to create/modify:**
- `d:\AI\pentest_strix\src\sectest\llm\provider.py` — `LiteLLMModelProvider`, singleton `llm_provider`, helper `get_model()`
- `d:\AI\pentest_strix\src\sectest\llm\config.py` — `LLMConfig` dataclass reading from env vars (`LITELLM_BASE_URL`, `LITELLM_API_KEY`, `DEFAULT_MODEL`)
- `d:\AI\pentest_strix\tests\test_llm_provider.py` — unit tests with mocked `AsyncOpenAI`

**Dependencies:** T4 (LiteLLM Proxy running for integration test), T1 (dependencies)

**Acceptance Criteria:**
- `LiteLLMModelProvider.get_model("gpt-4o")` returns an `OpenAIChatCompletionsModel` with `model="gpt-4o"`
- `LiteLLMModelProvider.get_model(None)` returns a model with the configured default (e.g., `"gpt-4o"`)
- `AsyncOpenAI` client is constructed with `base_url` from `LITELLM_BASE_URL` env var (default `http://localhost:4000/v1`) and `api_key` from `LITELLM_API_KEY`
- `set_tracing_disabled(disabled=True)` is called at module level (Phase 1 only; documented for Phase 2 removal)
- `LLMConfig` reads from env vars with sensible defaults; raises clear error if `LITELLM_API_KEY` is missing
- Integration test: with LiteLLM Proxy running, `llm_provider.get_model("gpt-4o")` can make a real API call (manual smoke test)

**Estimated effort:** S

---

### T6: ReconAgent Implementation

**Title:** Implement single ReconAgent that executes security tools in Kali sandbox via LLM

**Description:**
Implement `ReconAgent` in `src/sectest/agents/recon.py` that creates an openai-agents SDK `Agent` with a custom `function_tool` shell wrapper bound to a `SandboxSession`. The agent receives a target, runs Nmap or Semgrep in the sandbox, parses results to structured JSON, and returns findings. The agent uses `SandboxSession.exec()` (NOT `agents.sandbox` types) and routes LLM calls through `llm_provider`.

**Files to create/modify:**
- `d:\AI\pentest_strix\src\sectest\agents\recon.py` — `ReconAgent` class with `run_scan(target, session) -> dict`
- `d:\AI\pentest_strix\tests\test_recon_agent.py` — integration tests with mock SandboxSession and mock LLM

**Dependencies:** T3 (SandboxManager), T5 (LiteLLM ModelProvider)

**Acceptance Criteria:**
- `ReconAgent.__init__()` accepts `SandboxManager` and optional `model` string
- `ReconAgent.run_scan(target, session)` creates an `Agent` with shell tool, runs via `Runner.run()`, and returns structured dict
- Shell tool uses `session.exec(command, timeout=300)` — delegates to `SandboxSession`, not `agents.sandbox` types
- Agent instructions include target, available tools, expected workflow, and structured output format
- Agent tool list does NOT import `ShellTool`, `ShellCommandRequest`, `ShellResult` from `agents.sandbox` — uses `function_tool` decorator from `agents`
- `ReconAgent._parse_output()` handles both valid JSON and raw text fallback
- Unit tests pass with mocked SandboxSession and mocked LLM Runner
- `grep -r "from agents.sandbox" src/sectest/agents/` returns empty (L-01 compliance)
- `grep -r "from agents.tool import ShellTool" src/sectest/agents/` returns empty (L-01 compliance — ShellTool is from `agents.sandbox`)

**Estimated effort:** M

---

### T7: Platform Entry Point and Startup Sequence

**Title:** Implement main.py with image pre-pull, streaming progress, session lifecycle, and cleanup orchestration

**Description:**
Implement `src/sectest/main.py` as the Phase 1 entry point. The startup sequence: (1) load configuration from env vars, (2) initialize `SandboxManager` with `sectest/kali-sandbox:latest`, (3) pre-pull Kali image at startup with progress reporting (L-06), (4) create ephemeral sandbox session (D-01, D-02), (5) run `ReconAgent` scan, (6) stream real-time progress as structured JSON lines to stdout at each phase transition (PULL_IMAGE → CREATE_SANDBOX → TOOL_EXEC → PARSE_RESULTS → DONE), each line containing `{"phase": str, "timestamp": iso8601, "status": "running"|"done"|"error", "message": str}`, (7) output final structured results, (8) schedule 15-minute delayed cleanup (D-03, D-04), (9) ensure cleanup runs on error via `try/finally` (L-08).

**Files to create/modify:**
- `d:\AI\pentest_strix\src\sectest\main.py` — `main()` async function with full startup→scan→cleanup loop + streaming JSON line output
- `d:\AI\pentest_strix\src\sectest\streaming.py` — `ProgressEmitter` utility class: `emit(phase, status, message)` writes JSON line to stdout; supports context manager protocol for automatic DONE/error emission

**Dependencies:** T3 (SandboxManager), T5 (LiteLLM provider), T6 (ReconAgent)

**Acceptance Criteria:**
- `uv run python -m sectest.main` starts without error (when Docker, LiteLLM Proxy, and Kali image are available)
- Image pre-pull runs before scan, reports progress (pull status, image availability)
- If image is already local, pre-pull is skipped (fast path)
- Sandbox is created with `SandboxManager.create_session()`
- Scan runs via `ReconAgent.run_scan(target, session)`
- Results printed to stdout as structured JSON
- `try/finally` block ensures `schedule_cleanup(session)` is called even if scan fails
- Cleanup task logs via `ProgressEmitter` (not raw print)
- Adding `--target` CLI argument: `uv run python -m sectest.main --target example.com` scans specified target
- `--target` defaults to `localhost` if not provided (safe default for smoke testing)
- `--progress-format json` flag enables JSON line output mode for downstream consumers
- `test_main.py::test_streaming_progress` captures stdout lines, asserts each phase JSON line present and valid
- `test_main.py::test_streaming_error_phase` asserts error phase JSON emitted on simulated scan failure

**Estimated effort:** M (was S; streaming adds ProgressEmitter + test coverage)

---

### T8: End-to-End Smoke Test Suite

**Title:** Create smoke test that validates the full agent-sandbox-LLM execution loop

**Description:**
Write an integration test that orchestrates the complete Phase 1 flow: SandboxManager creates a real (or mocked) session, ReconAgent runs a scan, output is structured JSON. The test uses mocked LLM responses (to avoid API cost) but real Docker sandbox lifecycle. Include a manual smoke test script for validating against real LLM + real Docker.

**Files to create/modify:**
- `d:\AI\pentest_strix\tests\test_e2e_smoke.py` — end-to-end integration test with mock LLM, real Docker sandbox
- `d:\AI\pentest_strix\tests\conftest.py` — update with shared fixtures (mock_sandbox_session, mock_llm_provider, sandbox_manager fixture with real Docker)

**Dependencies:** T3, T5, T6, T7 (all prior tasks)

**Acceptance Criteria:**
- `test_e2e_recon_scan_mocked_llm`: Creates real sandbox via SandboxManager, runs ReconAgent with mocked LLM, asserts structured output with expected keys (`target`, `open_ports`, `summary`)
- `test_e2e_sandbox_cleanup`: Creates session, runs mock scan, verifies container destroyed after cleanup
- `test_e2e_error_cleanup`: Simulates agent crash, verifies `finally` block triggers cleanup
- `test_guard_l01_sandbox_imports`: Runs `grep` guard check, asserts no `agents.sandbox` imports outside `sandbox/manager.py`
- `test_litellm_provider_fallback`: Mocks primary model returning HTTP 429, asserts secondary model is called (via `pytest-httpx` or `responses` library route mocking). Verifies fallback chain behavior without real API calls.
- Manual smoke test documented in `tests/manual_smoke.md` with step-by-step instructions for running with real LLM

**Estimated effort:** M

---

## 5. Dependency Graph

```
                    T1 (Scaffold + Dependencies)
                    /          |            \
                   /           |             \
              T2 (Kali)    T4 (LiteLLM    T3 (SandboxManager)
              Image)       Config + DC)    [depends on T1 only]
                 |           |               |
                 |           |               |
                 +-----+-----+               |
                       |                     |
                  T5 (ModelProvider)          |
                  [depends on T4]             |
                       |                     |
                       +----------+----------+
                                  |
                             T6 (ReconAgent)
                             [depends on T3, T5]
                                  |
                             T7 (Entry Point)
                             [depends on T3, T5, T6]
                                  |
                             T8 (E2E Smoke Tests)
                             [depends on T3, T5, T6, T7]
```

---

## 6. Execution Order (Parallelization Waves)

### Wave 1 (parallel)
- **T1** — Project Scaffold and Dependencies

### Wave 2 (parallel — after T1)
- **T2** — Kali Gold Image Dockerfile
- **T3** — SandboxManager Abstraction Layer
- **T4** — LiteLLM Proxy Configuration + Docker Compose

### Wave 3 (parallel — after T4)
- **T5** — LiteLLM ModelProvider

### Wave 4 (after T3 + T5)
- **T6** — ReconAgent Implementation

### Wave 5 (after T3 + T5 + T6)
- **T7** — Platform Entry Point and Startup Sequence

### Wave 6 (after T3, T5, T6, T7)
- **T8** — End-to-End Smoke Test Suite

### Critical Path
T1 -> T3 -> T6 -> T7 -> T8 (T3 is the longest task; T4->T5 can run in parallel time)

### Parallelization Strategy
- Waves 2 and 3 maximize parallelism: T2 (Docker build) and T3 (coding) are independent; T4 (config) and T3 are independent; T5 waits for T4 but T3 continues in parallel
- T6 cannot start until both T3 (SandboxManager) and T5 (ModelProvider) complete
- T8 benefits from running immediately after T7 — both can be done by the same executor

---

## 7. Threat Model

This is a security platform; the sandbox infrastructure itself must be secure.

### Assets

| Asset | Sensitivity | Exposure |
|-------|-------------|----------|
| User's source code (mounted into sandbox) | HIGH — proprietary code, secrets | Docker volume mounts, sandbox filesystem |
| LLM API keys (OpenAI, Anthropic) | CRITICAL — cost + data exfiltration risk | Environment variables, LiteLLM Proxy config |
| Host Docker socket (`/var/run/docker.sock`) | CRITICAL — container escape, host compromise | Docker SDK calls from backend |
| Scan results (vulnerability reports) | HIGH — sensitive security findings | Sandbox workspace volumes, main.py stdout |

### Threats and Mitigations

| Threat | Severity | Likelihood | Mitigation | Verified By |
|--------|----------|------------|------------|------------|
| **T-01: Container escape via --privileged or --network host** | CRITICAL | LOW | L-04 enforces least-privilege: `NET_ADMIN`, `NET_RAW`, `SYS_PTRACE` only. `--privileged` and `--network host` are banned by code review and guard check. | T3: `SandboxManager.create_session()` never passes privileged flags. CI check: `grep -r "privileged\|network.*host" src/sectest/` must be empty. |
| **T-02: FUSE/SYS_ADMIN auto-escalation by DockerSandboxClient** | HIGH | MEDIUM | `DockerSandboxClient._create_container` auto-adds `SYS_ADMIN` + `/dev/fuse` + `apparmor:unconfined` when manifest mounts require FUSE. Avoid FUSE-triggering mount types — use Docker bind mounts and named volumes instead of FUSE-based mounts. | T3: Manifest entries use `LocalDir` (bind mount) and inline `File` (not FUSE-triggering). Test verifies container `SecurityOpt` does NOT include `apparmor:unconfined`. |
| **T-03: LLM API key leakage via agent logs or stdout** | CRITICAL | MEDIUM | API keys stored in env vars only; never in code or config files (except `.env.example` with placeholders). `.gitignore` excludes `.env`. LiteLLM Proxy is the only component that reads raw API keys; the backend only knows the LiteLLM master key. | T4: `litellm_config.yaml` uses `os.environ/OPENAI_API_KEY` syntax. T5: `LLMConfig` reads from env vars. `.gitignore` excludes `.env`. |
| **T-04: Source code exfiltration via LLM context** | HIGH | MEDIUM | ReconAgent instructions explicitly prohibit exfiltrating source code. Tool output parsed to structured summaries before LLM consumption (L-07). Only summary + top-N findings go to the LLM, not raw full output. | T6: Agent instructions include data minimization guidance. T6: `_parse_output()` parses tool output before LLM consumption. |
| **T-05: Docker socket abuse via container breakout** | CRITICAL | LOW | The backend process runs on the host with Docker socket access. If compromised, attacker gains host root. Mitigated by: no network-exposed API in Phase 1 (CLI only). | Phase 1 is CLI-only. Phase 5 (Web UI) must add API auth before exposing Docker socket operations over network. |
| **T-06: Container resource exhaustion (fork bomb, disk fill)** | MEDIUM | LOW | `SandboxConfig` enforces `memory_limit="2g"` and `cpu_limit=2.0`. Docker daemon limits CPU/memory per container. | T3: `DockerSandboxClient.create()` via Docker SDK sets `mem_limit` and `cpu_quota`. |
| **T-07: Orphaned containers leaking disk space** | LOW | HIGH | `DockerSandboxClient.delete()` is best-effort; catches `NotFound` silently. `SandboxManager` adds 15-min retention timer + `try/finally` cleanup. Still, Docker daemon crashes can leak containers. | T7: `finally` block ensures `schedule_cleanup()` is called. Future: Phase 2 adds periodic orphan scanner. |
| **T-08: LiteLLM Proxy unprotected endpoint** | MEDIUM | LOW | LiteLLM Proxy port 4000 is exposed on `localhost` only (not `0.0.0.0`) in Phase 1. Master key `sk-sectest-lite` is configurable via env var. | T4: `docker-compose.yml` maps `127.0.0.1:4000:4000`. |
| **T-09: Shell command injection via SandboxSession.exec()** | HIGH | LOW | `SandboxSession.exec(command)` passes raw command strings to `DockerSandboxSession.exec()` which invokes `bash -c`. If an attacker-controlled string reaches `exec()` (e.g., LLM-generated commands with injected shell metacharacters), it could execute arbitrary commands inside the sandbox. | T3: `SandboxSession.exec()` validates `command` is a non-empty string. T6: ReconAgent instructions forbid command injection patterns. Sandbox isolation (no `--privileged`, no host network) limits blast radius even if injection occurs. Future: Phase 2 adds `shlex.quote()` for user-supplied arguments. |

---

## 8. Risk Register

| ID | Risk | Category | Likelihood | Impact | Mitigation | Contingency |
|----|------|----------|------------|--------|------------|-------------|
| **R-01** | openai-agents SDK SandboxAgent API breaks in v0.18+ (beta API) | Technical | MEDIUM | HIGH — only 1 file affected | L-01 + L-02: SandboxManager is the single integration point. If API breaks, fix is isolated to `src/sectest/sandbox/manager.py`. | Pin to `openai-agents==0.17.5` in pyproject.toml. Do not upgrade until v0.18 changelog reviewed. |
| **R-02** | Kali image pull fails or takes >15 minutes | Infrastructure | MEDIUM | MEDIUM — blocks all scans | L-06: pre-pull at startup. Progress reporting. Retry with exponential backoff. | Fall back to `kalilinux/kali-rolling` base image (no custom tools) if custom image build fails. |
| **R-03** | Docker daemon not available on user's machine | Infrastructure | MEDIUM | HIGH — platform cannot function | Document Docker Desktop / Docker Engine as hard prerequisite in README. Check Docker availability at startup with clear error message. | Provide Docker Compose setup that includes Docker-in-Docker (dind) for environments where Docker socket is unavailable. |
| **R-04** | LiteLLM Proxy Docker image pull fails | Infrastructure | LOW | MEDIUM | Use versioned tag (`main-latest`) with fallback to specific release tag. Cache image locally. | Run LiteLLM Proxy as Python process (`uv tool run litellm`) instead of Docker if Docker pull fails. |
| **R-05** | OpenAI or Anthropic API rate limits prevent end-to-end testing | External dependency | MEDIUM | LOW — tests use mocks | All automated tests use mocked LLM. Manual smoke test is documentation-only. | Provide clear instructions for configuring rate limits in `litellm_config.yaml`. |
| **R-06** | Windows line endings or path separator issues | Platform | LOW | MEDIUM — project targets multi-OS | Use `pathlib.Path` for all paths. Configure `.gitattributes` for line endings. | Test on Windows + Linux before merging. |
| **R-07** | `sectest/kali-sandbox` and `kalilinux/kali-rolling` image ambiguity | Configuration | MEDIUM | LOW — wrong image used | L-03: custom image is `sectest/kali-sandbox:latest`, not raw `kalilinux/kali-rolling`. `SandboxConfig.image` defaults to custom image. | T3: `SandboxConfig` default is `sectest/kali-sandbox:latest`, explicitly different from upstream. |
| **R-08** | Phase 1 has no CLI argument parsing | UX | LOW | LOW — hardcoded target in main.py | T7 adds `--target` via `argparse`. Default is `localhost` for safe smoke testing. | Hardcode target as fallback if `argparse` is delayed. |

---

## 9. Architecture Decisions Implemented

This plan implements the following locked and implementation decisions from 01-CONTEXT.md:

| Decision | Implementation | Task |
|----------|---------------|------|
| **L-01** | Only `src/sectest/sandbox/manager.py` imports `agents.sandbox`. Guard enforced by `grep` check in T8. | T3 |
| **L-02** | `SandboxManager` wraps all `DockerSandboxClient` calls. `SandboxSession` is an opaque handle exposing only `exec()` and `cleanup()`. | T3 |
| **L-03** | Custom `sectest/kali-sandbox:latest` built from `kalilinux/kali-rolling` via `docker/Dockerfile.kali`. | T2 |
| **L-04** | Container capabilities: `NET_ADMIN`, `NET_RAW`, `SYS_PTRACE` only. | T3 |
| **L-05** | LiteLLM Proxy with dual-provider fallback (OpenAI -> Anthropic). | T4, T5 |
| **L-06** | Image pre-pull in `main.py` startup before accepting scan requests. | T7 |
| **L-07** | `ExecResult` returns `str` (decoded bytes). ReconAgent parses Nmap XML/Semgrep JSON before LLM consumption. | T3, T6 |
| **L-08** | `try/finally` in `main.py` + `schedule_cleanup()` with 15-min timer. | T3, T7 |
| **D-01** | Per-scan container: each scan gets a new `SandboxSession` via `create_session()`. | T3, T7 |
| **D-02** | Lazy init: container created at scan start, not pre-warmed at platform boot. | T7 |
| **D-03** | Delayed destruction: container survives scan completion. | T3, T7 |
| **D-04** | 15-minute retention timer via `asyncio.create_task` with `asyncio.sleep(900)`. | T3 |

---

## 10. Test Strategy

### Testing Pyramid (Phase 1)

```
        ┌──────┐
        │ E2E  │  T8: 3 smoke tests (mocked LLM, real Docker)
        ├──────┤
        │ INT  │  T6: 2 integration tests (mock sandbox + mock LLM)
        │      │  T5: 1 integration test (LiteLLM provider against real proxy)
        ├──────┤
        │ UNIT │  T3: 8+ unit tests (SandboxManager lifecycle, cleanup, error paths)
        │      │  T4: 2 config tests (schema validation)
        │      │  T7: 2 startup tests (config loading, cleanup trigger)
        └──────┘
```

### Test File Allocation

| Test File | Owner Task | Test Count (target) | Mock Strategy |
|-----------|------------|---------------------|---------------|
| `tests/test_sandbox_manager.py` | T3 | 10+ | Mock `docker.from_env()`, mock `DockerSandboxClient`, real `asyncio` |
| `tests/test_litellm_config.py` | T4 | 3+ | Parse and validate YAML config, no live proxy needed |
| `tests/test_llm_provider.py` | T5 | 4+ | Mock `AsyncOpenAI`, test provider interface |
| `tests/test_recon_agent.py` | T6 | 4+ | Mock `SandboxSession`, mock `Runner.run()` |
| `tests/test_main.py` | T7 | 3+ | Mock `SandboxManager`, mock `ReconAgent` |
| `tests/test_e2e_smoke.py` | T8 | 3+ | Real `SandboxManager`, mock `Runner.run()`, real Docker sandbox |

### Guard Checks (run on every commit)

```bash
# L-01: No agents.sandbox imports outside SandboxManager
grep -r "from agents.sandbox" src/sectest/ --include="*.py" | grep -v "sandbox/manager.py"
# Must return empty

# L-04: No privileged or network host
grep -r "privileged\|network.*host" src/sectest/ --include="*.py"
# Must return empty

# No .env committed
git ls-files | grep "\.env$" | grep -v "\.env\.example$"
# Must return empty
```

---

## 11. Deliverables Checklist

At phase completion, the following files must exist and pass their tests:

- [ ] `pyproject.toml` — project metadata, dependencies, pytest config
- [ ] `.python-version` — `3.12`
- [ ] `.env.example` — template env vars
- [ ] `.gitignore` — Python + Docker + .env exclusions
- [ ] `docker/Dockerfile.kali` — Kali gold image
- [ ] `docker/build.sh` — build script
- [ ] `docker/.dockerignore` — build context exclusion
- [ ] `docker-compose.yml` — LiteLLM Proxy standalone (no DB stubs)
- [ ] `config/litellm_config.yaml` — dual-provider fallback config
- [ ] `config/docker-compose.override.yml` — dev overrides
- [ ] `src/sectest/__init__.py` — package init with `__version__`
- [ ] `src/sectest/sandbox/__init__.py` — re-exports SandboxManager types
- [ ] `src/sectest/sandbox/manager.py` — SandboxManager, SandboxConfig, SandboxSession, ExecResult
- [ ] `src/sectest/llm/__init__.py` — re-exports LiteLLMModelProvider
- [ ] `src/sectest/llm/provider.py` — LiteLLMModelProvider, singleton llm_provider
- [ ] `src/sectest/llm/config.py` — LLMConfig from env vars
- [ ] `src/sectest/agents/__init__.py` — re-exports ReconAgent
- [ ] `src/sectest/agents/recon.py` — ReconAgent with shell tool
- [ ] `src/sectest/main.py` — entry point with full startup -> scan -> cleanup loop
- [ ] `tests/__init__.py`
- [ ] `tests/conftest.py` — shared fixtures
- [ ] `tests/test_sandbox_manager.py` — 10+ unit tests
- [ ] `tests/test_litellm_config.py` — 3+ config validation tests
- [ ] `tests/test_llm_provider.py` — 4+ provider tests
- [ ] `tests/test_recon_agent.py` — 4+ agent tests
- [ ] `tests/test_main.py` — 3+ startup tests
- [ ] `tests/test_e2e_smoke.py` — 3+ end-to-end smoke tests

**Total files:** 26 (14 source + 8 test + 4 config/infra)

---

## 12. Estimated Total Effort

| Task | Effort | Rationale |
|------|--------|-----------|
| T1 | S (30 min) | Project init + deps is mechanical |
| T2 | M (1 hr) | Dockerfile is straightforward; build time dominates |
| T3 | L (3-4 hr) | Core abstraction with many boundary conditions, error paths, async wrapping |
| T4 | M (1-2 hr) | Config is well-documented; Compose integration requires iteration |
| T5 | S (30 min) | Simple provider wrapper, well-documented pattern |
| T6 | M (1-2 hr) | Agent prompt design + tool wiring + output parsing |
| T7 | S (30 min) | Orchestration script, straightforward once T3/T5/T6 exist |
| T8 | M (1-2 hr) | E2E tests require real Docker; fixture setup takes time |
| **Total** | **L (9-13 hr)** | Majority of time in T3 (SandboxManager) and T8 (integration testing) |

---

*PLAN.md created: 2026-06-18*
*Ready for execution: Yes*
*Next step: `/gsd-execute-phase 1`*
