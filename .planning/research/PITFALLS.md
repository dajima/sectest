# Domain Pitfalls

**Domain:** AI-powered security audit platform (SAST + DAST)
**Researched:** 2026-06-18

## Critical Pitfalls

Mistakes that cause rewrites or major issues.

### Pitfall 1: Locking into SandboxAgent Beta API

**What goes wrong:** The openai-agents SDK SandboxAgent system (DockerSandboxClient, Manifest, Capabilities) is still beta as of v0.17.x. Direct usage throughout agent code means an SDK API change forces a full rewrite of every agent.

**Why it happens:** SandboxAgent is the most natural abstraction — it maps perfectly to the Kali Docker use case. The temptation to use it directly is strong.

**Consequences:** v0.18+ could rename Manifest fields, change capability registration, alter session lifecycle. Every agent module breaks.

**Prevention:** Create a `SandboxManager` abstraction layer that wraps all SandboxAgent/DockerSandboxClient usage. Only `SandboxManager` imports from `agents.sandbox`. All agent code uses `SandboxManager`. When the SDK stabilizes (GA), consider removing the abstraction.

**Detection:** Grep your codebase for `from agents.sandbox import`. If it appears outside `sandbox_manager.py`, you have a problem.

### Pitfall 2: Kali Image Pull Blocking Scan Start

**What goes wrong:** The Kali Docker image (`kalilinux/kali-rolling`) is ~3GB. If `docker pull` runs synchronously when a user starts a scan, they wait 5-15 minutes before any security testing begins.

**Why it happens:** The natural implementation: start scan → check if image exists → if not, pull → then create container. Blocking the entire pipeline on image availability.

**Consequences:** Terrible UX. Scans appear hung. Users Ctrl+C and abandon.

**Prevention:** Pre-fetch the Kali image at platform startup (systemd service or Docker Compose healthcheck dependency). Run `docker pull kalilinux/kali-rolling:latest` in the background during initialization. If a scan starts and the image isn't available, surface a clear "Image is being prepared, estimated X minutes remaining" progress message. Cache the image pull timestamp and re-pull weekly.

**Detection:** Time the "start scan" endpoint. If it takes >5 seconds before the first agent log, the image pull is blocking.

### Pitfall 3: LLM Context Window Exhaustion in Long Scans

**What goes wrong:** A single agent accumulates conversation history across hundreds of turns (tool calls, observations, sub-agent results). Eventually the context window fills, the LLM loses earlier context, and analysis quality degrades.

**Why it happens:** Security scans can run for 50-300+ turns. Each agent handoff transfers the full conversation. Naively, the final VerificationAgent receives the entire history of Recon + Analysis.

**Consequences:** Mid-scan, the LLM starts "forgetting" the initial code structure or target configuration. Findings become inconsistent. Token costs balloon.

**Prevention:** Use openai-agents SDK's built-in memory compression. Implement explicit context window management: summarize previous agent output before handoff, not raw conversation. Cap conversation turns per agent. Store detailed findings in PostgreSQL, not in conversation context.

**Detection:** Monitor average tokens per agent turn in Langfuse. If it grows linearly with scan duration, context is accumulating without compression.

### Pitfall 4: AGPL-3.0 Code Contamination

**What goes wrong:** DeepAudit (AGPL-3.0) has excellent SAST agent patterns. Copying code or closely translating its RAG pipeline, agent orchestration, or sandbox verification logic creates a derivative work, forcing the entire project under AGPL-3.0.

**Why it happens:** DeepAudit solves the exact SAST problems we need. The architecture is well-documented and publicly visible. The line between "inspired by" and "derived from" is legally blurry.

**Consequences:** License contamination. If the project takes any VC funding or wants proprietary features, AGPL-3.0 is a blocker. Even if staying open-source, AGPL-3.0 restricts downstream commercial use more than Apache 2.0 or MIT.

**Prevention:** Treat DeepAudit as a "specification" not a "reference implementation." Read their docs and DeepWiki for the *what* and *why*, not the *how*. Implement from scratch using openai-agents SDK primitives (not LangGraph). Different agent names, different prompt templates, different RAG chunking strategy. Document design decisions as "based on published research patterns" not "adapted from DeepAudit."

**Detection:** Code review checklist item: "Does this code resemble DeepAudit's implementation more than the general problem pattern?" If yes, redesign.

## Moderate Pitfalls

### Pitfall 5: Synchronous Docker API Calls in Async Context

**What goes wrong:** The `docker-py` library has both sync and async APIs. Using sync `client.containers.run()` in an async FastAPI handler blocks the event loop.

**Prevention:** Use `docker-py`'s async API or wrap sync calls in `asyncio.to_thread()` for container lifecycle operations. For long-running container execution, use `asyncio.create_subprocess_exec` with `docker exec`.

### Pitfall 6: Missing Tool Output Parsing

**What goes wrong:** Security tools (Nmap, Nuclei, Semgrep) output structured data (XML, JSON, SARIF) but LLMs are fed the raw text output. The LLM misinterprets tool results or hallucinates findings from noisy output.

**Prevention:** Parse tool output into structured findings before feeding to LLMs. Use each tool's machine-readable output format (Nmap XML, Nuclei JSON, Semgrep SARIF). Only pass summary + top-N findings to the LLM, not full raw output.

### Pitfall 7: Redis as Sole Message Broker for Critical Tasks

**What goes wrong:** Redis pub/sub is fire-and-forget. If a Celery worker crashes mid-scan, the task is lost (unless using Redis Streams or a proper message broker).

**Prevention:** For critical scan state, use PostgreSQL as the source of truth (scan status column). Redis is the transport, not the record. Implement idempotent task processing: replay from PostgreSQL state if a worker restarts.

## Minor Pitfalls

### Pitfall 8: Hardcoded LLM Model Names in Agent Code

**What goes wrong:** Agents reference `model="gpt-4o"` directly instead of using LiteLLM's routing names.

**Prevention:** Use LiteLLM model names (`openai/gpt-4o`, `anthropic/claude-sonnet-4-20250514`). Better: use deployment-level aliases (`security-audit-large`, `security-audit-fast`) so model selection is a LiteLLM config change.

### Pitfall 9: Forgetting to Clean Up Docker Resources

**What goes wrong:** Ephemeral containers are not removed after scan completion/failure. Disk space fills with stopped containers and dangling volumes.

**Prevention:** Always use `auto_remove=True` on container creation. Implement a cleanup cron that prunes containers older than 1 hour. Set Docker daemon limits (`docker system prune --filter "until=24h"`).

### Pitfall 10: CORS Misconfiguration in Production

**What goes wrong:** During development, CORS is set to `allow_origins=["*"]`. This reaches production. Combined with JWT in localStorage, it enables cross-origin token theft.

**Prevention:** FastAPI CORSMiddleware with explicit origin list from environment variable. JWT in httpOnly cookies (not localStorage). CSP headers in Nginx.

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Docker Sandbox | Kali image pull blocks scan start (Pitfall 2) | Async pre-fetch at startup; progress UI for pending pull |
| Agent Core | Direct SandboxAgent API usage (Pitfall 1) | SandboxManager abstraction from day 1 |
| Agent Core | LLM context exhaustion (Pitfall 3) | Implement context compression before first multi-turn agent test |
| RAG Pipeline | AGPL-3.0 contamination from DeepAudit patterns (Pitfall 4) | Design RAG pipeline independently; document design rationale |
| Tool Integration | Missing tool output parsing (Pitfall 6) | Parse every tool output to structured format before LLM consumption |
| Frontend | CORS misconfiguration (Pitfall 10) | httpOnly cookies from day 1; explicit CORS origins |
| Deployment | Docker resource leaks (Pitfall 9) | auto_remove=True; cleanup cron; disk monitoring alert |
| Observability | Tracing added retroactively | Integrate Langfuse instrumentation in Phase 2, not Phase 6 |
