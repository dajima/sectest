# Project Research Summary

**Project:** Strix -- Unified AI Security Testing Platform
**Domain:** AI-powered security audit platform (SAST + DAST) with multi-agent orchestration
**Researched:** 2026-06-18
**Confidence:** HIGH

## Executive Summary

Strix is a unified AI security testing platform that combines static analysis (SAST) and dynamic testing (DAST) into a single multi-agent pipeline. Experts in this space build on three pillars: an agent orchestration framework for the AI pipeline, isolated sandbox execution for running dangerous security tools, and polyglot persistence (relational, ephemeral, and vector) to handle the fundamentally different data access patterns each tier demands. The two reference implementations -- Strix (MIT, openai-agents SDK) and DeepAudit (AGPL-3.0, LangGraph) -- validate this architecture but also demonstrate the critical fork in the road: openai-agents SDK provides the SandboxAgent abstraction that maps directly to Docker Kali sandboxes, while LangGraph carries AGPL-3.0 constraints and heavier abstraction layers.

The recommended approach is to build on openai-agents SDK 0.17.5 for multi-agent orchestration, Kali Linux Docker containers managed through a SandboxManager abstraction layer, and LiteLLM Proxy for provider-agnostic LLM routing. The frontend uses React 19 with shadcn/ui + TanStack Query, while the backend serves FastAPI with SSE streaming for real-time scan progress. Three databases serve distinct roles: PostgreSQL for structured data (projects, scan results, users), Redis for ephemeral state (sessions, queues, pub/sub), and ChromaDB for RAG-based semantic code indexing. Langfuse v4 provides self-hosted observability with OpenInference OTLP span export from the agent SDK.

The key risks are: (1) bleeding on the SandboxAgent beta API -- mitigated by a SandboxManager abstraction layer that insulates all agent code from SDK changes, (2) the ~3GB Kali image pull blocking scan initiation -- mitigated by pre-fetching at platform startup with progress UI, (3) LLM context window exhaustion during long multi-agent scans -- mitigated by output summarization at agent handoff boundaries rather than passing raw conversation history, and (4) AGPL-3.0 license contamination from DeepAudit architecture -- mitigated by treating DeepAudit as a specification, not a reference implementation, and designing all components independently from scratch. The overall research confidence is HIGH: the stack is validated by multiple production-grade references, the architecture patterns are well-documented, and the pitfalls are known from real-world security tooling projects.

## Key Findings

### Recommended Stack

The platform runs on Python 3.12+ with openai-agents SDK 0.17.5 as the multi-agent orchestration core. LiteLLM Proxy serves as an internal LLM gateway providing OpenAI-compatible API access to 100+ providers with cost tracking, fallback chains, and Redis-backed semantic caching. FastAPI 0.136.1 handles the REST API with SSE streaming for scan progress, backed by PostgreSQL 16+ (structured data), Redis 7+ (sessions, queues, pub/sub, rate limiting, LLM cache), and ChromaDB 1.5.9 (RAG vector store with HNSW indexing). The frontend uses React 19 with shadcn/ui, TanStack Query, Zustand, and Vite 8. Observability runs through Langfuse v4 self-hosted with OpenInference OTLP span export, structlog for structured logging, and Prometheus+Grafana for infrastructure metrics.

**Core technologies:**
- **openai-agents SDK 0.17.5:** Multi-agent orchestration with SandboxAgent, handoffs, guardrails, built-in tracing. MIT license. Maps directly to Kali Docker sandbox model.
- **LiteLLM Proxy:** De facto standard for multi-LLM routing. 100+ providers, fallback chains, per-model cost tracking, Redis semantic cache. Native openai-agents SDK integration via custom ModelProvider.
- **FastAPI 0.136.1 + Uvicorn:** Async-native Python web framework with Pydantic v2 validation, automatic OpenAPI docs, SSE streaming. Critical for LLM API call patterns where every endpoint blocks on external IO.
- **PostgreSQL 16+ + Redis 7+ + ChromaDB 1.5.9:** Polyglot persistence -- each database serves a fundamentally different access pattern. Cannot consolidate without compromising performance at each tier.
- **React 19 + shadcn/ui + TanStack Query:** shadcn/ui (42% adoption) has overtaken MUI. Zustand (14.2M weekly downloads) has overtaken Redux. Both are lighter, more modern choices.
- **Langfuse v4 (self-hosted):** MIT core, first-class openai-agents SDK integration via OpenInference. Observations-first architecture. Tracks agent traces, token costs, handoff graphs, tool call latency.
- **Docker Kali Linux Sandbox:** Ephemeral per-scan containers via openai-agents DockerSandboxClient. Gold-image model (never modified). Least-privilege capabilities (NET_ADMIN, NET_RAW, SYS_PTRACE only -- never --privileged).
- **MCP Official SDK 1.27.1 + FastMCP:** External security tool wrapping (Semgrep, Nmap MCP servers). Four-layer capability architecture: Skill -> Tool -> Plugin -> MCP Client.

### Expected Features

**Must have (table stakes):**
- Source code import (Git clone, zip upload, local path) -- users need to point at code to audit
- Multi-language SAST scanning (Python, JS/TS, Java, Go) -- Semgrep + Bandit via tool registry
- Dynamic target scanning (URL, API endpoint, IP range) -- Nmap, Nuclei, FFuf via Kali sandbox
- Docker Kali sandbox execution -- all dangerous tools run isolated
- Vulnerability report generation (PDF, JSON, SARIF) -- audit deliverables
- LLM provider configuration (OpenAI, Anthropic, local) -- LiteLLM proxy handles this
- Authentication (JWT + RBAC) -- multi-user web deployment requirement
- CLI interface for local scanning -- Textual TUI wrapping same API as web
- Real-time scan progress streaming -- SSE from FastAPI; TanStack Query for reconnection

**Should have (competitive differentiators):**
- Unified SAST+DAST in single pipeline -- no other tool combines code audit + live penetration testing with AI agents
- PoC auto-generation and sandbox verification -- near-zero false positives; each finding has executable proof
- Skill/Tool/Plugin/MCP Client four-layer capability registry -- highly extensible, declarative vulnerability checks
- RAG-based code semantic indexing -- understands code context beyond pattern matching; Tree-sitter AST chunking
- Agent collaboration graph visualization -- users see which agent found what (Langfuse trace visualization)
- Hybrid deployment (CLI single-machine + Web team server) -- same engine, two interfaces, no feature disparity
- Scan replay and diff analysis -- re-run same scan with same agent state; git diff-based incremental re-scanning

**Defer (v2+):**
- Multi-agent collaboration visualization: v2 after single-agent pipeline is stable
- PoC auto-generation: v2 after basic detection works reliably
- RAG semantic indexing: v2 after pattern-based detection proves the pipeline
- Web dashboard: v2 after CLI validates the core engine
- MCP integration: v2 after built-in tools are stable
- Team/multi-user: v2 after single-user flow works

### Architecture Approach

The platform follows a six-layer architecture with clear component boundaries and single-owner data access. The Interface Layer (CLI Textual TUI + React 19 Web SPA) connects to the API Layer (FastAPI REST + SSE), which is backed by the Agent Orchestration Layer (openai-agents SDK pipeline with Recon -> Analysis -> Verification -> Report handoffs). Below that, the Capability Registry (Skill/Tool/Plugin/MCP Client) and Docker Sandbox (ephemeral Kali containers) provide execution isolation and tooling. The Data Layer uses polyglot persistence (PostgreSQL, Redis, ChromaDB) with single-owner services. The LLM Gateway (LiteLLM Proxy) handles provider routing, and the Observability Layer (Langfuse, Prometheus, Grafana) captures traces and metrics. The architecture follows four key patterns: Sandbox Abstraction (wrap openai-agents sandbox APIs behind SandboxManager), Agent Pipeline with Handoffs (sequential specialization), Polyglot Persistence with Clear Ownership (each store has exactly one owning service), and SSE Streaming for Scan Progress (Redis pub/sub backed).

**Major components:**
1. **Agent Orchestrator (openai-agents SDK):** Multi-agent pipeline execution with handoffs, guardrails, trace export. Communicates with LiteLLM Proxy for LLM calls and Docker Sandbox for tool execution.
2. **Docker Kali Sandbox:** Ephemeral per-scan containers with gold-image model. Least-privilege capabilities. SandboxManager abstraction insulates agent code from SDK beta API changes.
3. **Capability Registry:** Four-layer architecture (Skill -> Tool -> Plugin -> MCP Client). Declarative vulnerability check registration. Tools like Semgrep, Bandit, Nuclei, Nmap, FFuf, SQLMap registered here.
4. **LiteLLM Proxy:** Internal LLM gateway with provider switching, cost tracking, fallback chains, Redis semantic caching. OpenAI-compatible endpoint consumed by openai-agents SDK.
5. **Langfuse v4:** Self-hosted observability. OTLP ingestion from OpenInference spans auto-exported by openai-agents SDK. Token cost attribution, prompt management, eval datasets.
6. **Data Services (PostgreSQL + Redis + ChromaDB):** ProjectService (PG), SessionService (Redis), RAGService (ChromaDB) -- single owners, no cross-store joins.
7. **FastAPI Backend:** REST API with Pydantic v2 validation, JWT auth, SSE streaming, Celery task dispatch.
8. **React 19 Frontend:** shadcn/ui + TanStack Query + Zustand + Vite 8. SSE EventSource for real-time scan progress.

### Critical Pitfalls

1. **Locking into SandboxAgent Beta API** -- openai-agents SDK SandboxAgent, DockerSandboxClient, and Manifest are beta through v0.17.x. Direct usage scatters the dependency across all agent modules. Prevention: SandboxManager abstraction layer from day 1. Only SandboxManager imports from agents.sandbox. All agent code uses SandboxManager. Guard: grep for "from agents.sandbox import" outside sandbox_manager.py.

2. **Kali Image Pull Blocking Scan Start** -- The kalilinux/kali-rolling image is ~3GB (5-15 minute pull). Synchronous docker pull when a scan starts creates terrible UX. Prevention: pre-fetch at platform startup (Docker Compose healthcheck). Surface progress message if not ready. Re-pull weekly.

3. **LLM Context Window Exhaustion in Long Scans** -- Security scans can run 50-300+ turns. Naively passing full conversation history through handoffs fills the context window; the LLM forgets early findings and costs balloon. Prevention: summarize agent output before handoff (not raw conversation). Cap turns per agent. Store detailed findings in PostgreSQL, not conversation context. Monitor tokens-per-turn in Langfuse.

4. **AGPL-3.0 Code Contamination from DeepAudit** -- DeepAudit SAST patterns, RAG pipeline, and sandbox verification are AGPL-3.0 licensed. Copying creates a derivative work. Prevention: treat DeepAudit as a specification (what/why), not reference implementation (how). Implement from scratch using openai-agents SDK primitives. Different agent names, prompt templates, RAG chunking strategy.

5. **Missing Tool Output Parsing** -- Security tools output structured data (XML, JSON, SARIF) but raw text fed to LLMs causes misinterpretation. Prevention: parse every tool output to structured format before LLM consumption. Use machine-readable formats (Nmap XML, Nuclei JSON, Semgrep SARIF). Only pass summary + top-N findings.

6. **Synchronous Docker API Calls in Async Context** -- docker-py sync calls block the event loop. Prevention: use docker-py async API or wrap in asyncio.to_thread(). For long-running execution use asyncio.create_subprocess_exec with docker exec.

7. **CORS Misconfiguration in Production** -- allow_origins=["*"] surviving to production with JWT in localStorage enables cross-origin token theft. Prevention: explicit CORS origins from env var. JWT in httpOnly cookies. CSP headers in Nginx.

## RAG Pipeline Design

The RAG pipeline performs semantic indexing of source code for context-aware vulnerability detection beyond simple pattern matching. Tree-sitter parses code into AST chunks (function-level granularity), embeddings are generated via configurable providers (OpenAI, Ollama, HuggingFace), and ChromaDB stores vectors with HNSW indexing in per-project collections. The RAGService is the single owner of all ChromaDB access. CRITICAL: the RAG implementation must be designed independently from DeepAudit approach. Use Tree-sitter for AST-based code chunking (a well-established technique), but develop novel chunking heuristics and embedding strategies. The pipeline is deferred to v2 (MVP uses pattern-based Semgrep/Bandit detection first), which provides time to design cleanly without AGPL contamination risk.

## Multi-Agent Orchestration Design

The agent pipeline follows a sequential specialization pattern using openai-agents SDK handoffs: ReconAgent (information gathering) -> AnalysisAgent (vulnerability detection) -> VerificationAgent (PoC validation) -> ReportAgent (deliverable generation). Each agent has a specialized tool set and system prompt. Handoffs transfer summarized output (not raw conversation) to prevent context window exhaustion. The RunHooks lifecycle (on_start, on_end) handles sandbox provisioning and teardown. Guardrails validate both agent inputs and outputs. The entire execution is traced via OpenInference OTLP spans auto-exported to Langfuse, providing per-agent token cost attribution and handoff visualization.

For SAST scans, ReconAgent performs Tree-sitter parsing and initial code understanding; AnalysisAgent runs Semgrep/Bandit in the sandbox and queries ChromaDB for vulnerability patterns; VerificationAgent generates and executes PoC exploits with self-healing retry. For DAST scans, ReconAgent runs Nmap/service enumeration; AnalysisAgent runs Nuclei/FFuf/SQLMap; VerificationAgent validates exploitable findings with browser automation.

## Kali Sandbox Tool Ecosystem

Kali Linux Docker containers provide the execution environment for all security tools. The gold image (kalilinux/kali-rolling) is pre-built with the complete toolchain: Nmap (network reconnaissance), Nuclei (vulnerability scanning), FFuf (web fuzzing), SQLMap (SQL injection testing), Metasploit (exploitation framework), and Semgrep/Bandit (SAST -- installed in Dockerfile build stage). Each scan session creates an ephemeral container from the gold image, mounts the workspace volume, executes tools, persists results, and destroys the container. Least-privilege capabilities (NET_ADMIN, NET_RAW, SYS_PTRACE) are used; --privileged and --network host are never used. openai-agents SDK SandboxAgent provides the agent-container binding, with SandboxManager wrapping it for API stability insulation.

## Integration Architecture

**LiteLLM Proxy Integration:** LiteLLM runs as a separate Docker Compose service. The openai-agents SDK connects via a custom ModelProvider pointing at the LiteLLM Proxy OpenAI-compatible endpoint. This enables provider switching without code changes, per-model cost tracking, automatic fallback on rate limits, and Redis-backed semantic caching to reduce repeat LLM API costs. Model selection uses deployment-level aliases (e.g., security-audit-large, security-audit-fast) rather than hardcoded provider names.

**MCP Client Integration:** MCP servers wrap external security tools as MCP resources (e.g., semgrep-mcp-server, nmap-mcp-server). The openai-agents SDK agents connect as MCP clients via mcp.ClientSession, discovering tools dynamically. This forms the external ecosystem layer of the four-layer capability architecture. Target protocol version 2025-06-18 with fallback to 2025-03-26. MCP integration is deferred to v2 after built-in tools are stable.

**Langfuse Integration:** The trace pipeline flows: openai-agents SDK built-in tracing -> OpenInference OTel spans -> OTLP exporter -> Langfuse v4 ingestion -> observations-first dashboard. This provides agent trace visualization, per-span token cost attribution, prompt management with versioning, eval datasets for vulnerability detection accuracy, and scan replay from stored traces. Langfuse runs self-hosted in Docker Compose. Instrumentation is integrated early (Phase 2) rather than retrofitted.

## Implications for Roadmap

Based on research, four phases deliver a working CLI-first MVP, then progressively add web UI and competitive differentiators.

### Phase 1: Core Engine -- Single-Agent Pipeline (CLI)

**Rationale:** Everything depends on the agent->sandbox->tool execution loop. This phase validates the core innovation (AI-driven security testing in isolated containers) before investing in multi-agent complexity, web UI, or RAG infrastructure. The Kali sandbox lifecycle, LiteLLM integration, and basic tool execution must work before anything else can.

**Delivers:** CLI tool (strix scan --target ./app) that imports source code or targets a URL, provisions a Kali Docker sandbox, runs a single ReconAgent with Semgrep/Nmap tools via LiteLLM, and outputs a JSON vulnerability report.

**Addresses (from FEATURES.md):** Source code import, basic SAST/DAST scanning, Docker Kali sandbox lifecycle, LLM provider config, CLI interface, JSON report output.

**Avoids (from PITFALLS.md):** SandboxAgent beta API lock-in (SandboxManager from day 1), Kali image pull blocking scan start (pre-fetch at startup), missing tool output parsing (structured parsing from day 1), sync Docker API calls (use async patterns).

**Research flag:** MEDIUM -- Docker sandbox integration with openai-agents SDK needs hands-on validation of SandboxAgent API surface and Kali image toolchain behavior.

### Phase 2: Multi-Agent Pipeline + Observability

**Rationale:** Once single-agent execution works, the pipeline extends to the full Recon->Analysis->Verification->Report handoff chain. Langfuse instrumentation is integrated here (not retrofitted) to provide tracing for debugging multi-agent interactions. This phase establishes the scalable architecture before adding user-facing complexity.

**Delivers:** Multi-agent pipeline with handoffs, context compression between agents, Langfuse trace visualization, structured report generation (PDF/SARIF), basic auth (JWT).

**Addresses:** Agent collaboration graph (Langfuse traces), report generation, authentication. Implements the full agent pipeline architecture pattern.

**Uses:** openai-agents SDK handoffs, RunHooks lifecycle, Langfuse v4 with OpenInference OTLP export, Celery for background scan tasks.

**Avoids:** LLM context window exhaustion (summarization at handoff boundaries, not raw conversation), AGPL-3.0 contamination (implement pipeline from scratch using openai-agents primitives).

**Research flag:** HIGH -- Agent handoff patterns with context summarization need careful design. Few documented examples of multi-turn security agent pipelines with context compression exist.

### Phase 3: Web Dashboard + Team Features

**Rationale:** The CLI validates the engine. The web UI makes it accessible to teams. React 19 SPA with real-time scan streaming, project management, and multi-user support. This phase also introduces the capability registry for extensible tool management.

**Delivers:** React 19 SPA (shadcn/ui + TanStack Query + Zustand), real-time scan progress via SSE, project/scan management CRUD, RBAC, capability registry (Skill/Tool/Plugin layers).

**Addresses:** Real-time scan progress streaming, web dashboard, team/multi-user, capability registry.

**Uses:** FastAPI SSE streaming with Redis pub/sub, TanStack Query stale-while-revalidate, shadcn/ui dashboard components.

**Avoids:** CORS misconfiguration (httpOnly cookies, explicit origins, CSP headers from day 1), Docker resource leaks (auto_remove=True, cleanup cron).

**Research flag:** LOW -- React 19 + shadcn/ui + TanStack Query dashboard pattern is well-documented. Standard patterns apply.

### Phase 4: RAG Pipeline + MCP Integration (v2)

**Rationale:** These are competitive differentiators that require a stable foundation. RAG semantic indexing depends on the SAST pipeline producing reliable baseline results. MCP integration depends on the capability registry being stable. Both are deferred to v2 per MVP recommendation.

**Delivers:** Tree-sitter AST chunking, ChromaDB HNSW indexing, semantic code search, MCP server ecosystem (Semgrep MCP, Nmap MCP), PoC auto-generation with sandbox verification, scan replay and diff analysis.

**Addresses:** RAG-based semantic indexing, MCP integration, PoC auto-generation, scan replay.

**Uses:** ChromaDB, Tree-sitter, MCP SDK 1.27.1+ / v2 (stable by July 2026), openai-agents SandboxAgent verification harness.

**Avoids:** AGPL-3.0 contamination (independent RAG design, novel chunking strategy).

**Research flag:** HIGH -- RAG pipeline design for code semantic indexing is sparse in public documentation. DeepAudit has a working implementation but it is AGPL-3.0 and cannot be referenced. MCP server wrapping patterns for security tools are emerging but not well-documented.

### Phase Ordering Rationale

The ordering follows a strict dependency chain: the sandbox and single-agent loop (Phase 1) must work before multi-agent orchestration (Phase 2), which must work before the web UI can stream real-time results (Phase 3), which must be stable before RAG and MCP integration (Phase 4) adds competitive differentiation. Each phase produces a usable increment -- Phase 1 produces a working CLI audit tool, Phase 2 adds tracing and structured reports, Phase 3 adds team collaboration, and Phase 4 adds the differentiators. This also follows the MVP recommendation: build the core engine first, validate it works, then add the web layer and advanced features.

The grouping isolates risk. Docker sandbox and LiteLLM integration are the highest technical risk items and are contained in Phase 1. Multi-agent context compression is the next highest risk and is contained in Phase 2. The web dashboard is well-understood and lower risk, fitting naturally in Phase 3. RAG and MCP require independent design work and are deferred to Phase 4 where they can be built without the pressure of the MVP timeline.

### Research Flags

Phases likely needing deeper research during planning:

- **Phase 1:** Docker sandbox integration with openai-agents SDK -- SandboxAgent API surface validation, Kali gold image toolchain build, capability declaration patterns. Needs hands-on prototyping.
- **Phase 2:** Multi-agent handoff context management -- few documented examples of security agent pipelines with context compression at scale. Agent prompt engineering for security analysis roles.
- **Phase 4:** RAG pipeline design for code semantic indexing -- must be designed independently from DeepAudit. Sparse public documentation on code-specific embedding strategies. MCP server wrapping for security tools is nascent.

Phases with standard patterns (skip research-phase):

- **Phase 3:** React 19 + shadcn/ui + TanStack Query dashboard is thoroughly documented. FastAPI SSE with Redis pub/sub is an established pattern. RBAC with JWT is well-understood.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All recommendations backed by official docs, multiple production references (Strix, DeepAudit), and high-confidence tutorials. Versions pinned to current stable releases. Alternatives clearly evaluated with rationale. |
| Features | HIGH | Table stakes derived from security tooling expectations. Differentiators validated against reference implementations. Anti-features clearly scoped by PROJECT.md boundaries. MVP recommendation follows logical dependency chain. |
| Architecture | HIGH | Patterns validated by two independent reference implementations. Layered architecture with clear component boundaries. Data flow diagrams cover both SAST and DAST paths. Scalability considerations address each tier from single-user to SaaS. |
| Pitfalls | HIGH | Pitfalls sourced from real-world security tooling experience and multi-agent platform patterns. Preventions are specific, testable, and practical. Phase-specific warnings map pitfalls to implementation stages. Detection criteria provided for each critical pitfall. |

**Overall confidence:** HIGH

The research is comprehensive and actionable. All major architectural decisions have clear rationale. Reference implementations exist for the core patterns. The primary uncertainties are: (1) the exact API surface of openai-agents SDK SandboxAgent beta -- mitigated by the SandboxManager abstraction, (2) the performance characteristics of context compression in long security scans -- mitigated by early instrumentation and Langfuse monitoring, and (3) the design of an RAG pipeline that achieves DeepAudit-level quality without AGPL-3.0 contamination -- mitigated by deferring RAG to v2 and designing independently from first principles.

### Gaps to Address

- **SandboxAgent GA timeline:** The openai-agents SDK SandboxAgent is beta through v0.17.x. GA timeline is unknown. Monitor for breaking API changes and update SandboxManager accordingly. The abstraction layer handles this gap.
- **Kali gold image optimization:** The base kalilinux/kali-rolling is ~3GB. Tool pre-installation adds size. Investigate Docker layer caching strategies and multi-stage builds to minimize pull time. Profile which tools are actually needed vs. nice-to-have.
- **Multi-agent prompt engineering:** Security-specific agent prompts (reconnaissance, vulnerability analysis, exploit verification) are not widely documented. Prompts will need iterative refinement during Phase 2 based on Langfuse eval results.
- **RAG code chunking strategy:** Tree-sitter AST-based chunking for vulnerability detection is an active research area. Optimal chunking granularity (function-level vs. class-level vs. cross-file) needs empirical validation during Phase 4.
- **MCP protocol stability:** MCP SDK v2 is in alpha (June 2026), stable expected July 2026. Phase 4 should target v2 if stable, with v1.27.1 as fallback. Monitor the spec transition.

## Sources

### Primary (HIGH confidence)
- [OpenAI Agents SDK v0.17.5 -- GitHub](https://github.com/openai/openai-agents-python) -- agent framework, SandboxAgent, handoffs, guardrails, tracing
- [OpenAI Agents SDK Sandbox Agents Quickstart](https://openai.github.io/openai-agents-python/sandbox_agents/) -- Docker sandbox integration patterns
- [Strix (usestrix/strix) -- GitHub](https://github.com/usestrix/strix) -- reference architecture, multi-agent pipeline design
- [DeepAudit (lintsinghua/DeepAudit) -- GitHub](https://github.com/lintsinghua/DeepAudit) -- reference architecture (AGPL-3.0, patterns only)
- [LiteLLM + OpenAI Agents SDK Integration](https://docs.litellm.ai/docs/tutorials/openai_agents_sdk) -- LiteLLM proxy configuration for openai-agents SDK
- [FastAPI 0.136.1 Production Stack 2026](https://tech-insider.org/fastapi-tutorial-python-rest-api-13-steps-2026/) -- FastAPI + SQLAlchemy 2.0 async patterns
- [React 19 + Vite + shadcn/ui Dashboard Guide 2026](https://www.usedatabrain.com/how-to/create-react-dashboard) -- frontend stack validation
- [Langfuse Python SDK v4](https://github.com/langfuse/langfuse-python) -- observability, OpenInference integration
- [MCP Python SDK v1.27.1](https://pypi.org/project/mcp/1.27.1/) -- MCP client/server protocol
- [ChromaDB v1.5.9](https://cookbook.chromadb.dev/) -- vector store, HNSW indexing, embedding functions
- [SQLAlchemy 2.0 async PostgreSQL Best Practices 2026](https://nerdleveltech.com/courses/build-production-rest-api/learn/database-layer/production-database-design) -- async ORM patterns

### Secondary (MEDIUM confidence)
- [Docker Kali Linux Security Tools Best Practices 2026](https://oneuptime.com/blog/post/2026-02-08-how-to-run-kali-linux-tools-in-docker/view) -- Kali Docker configuration, toolchain setup
- [AI Agent Observability Tools Comparison 2026](https://futureagi.com/blog/best-ai-agent-observability-tools-2026/) -- Langfuse vs alternatives evaluation
- [Polyglot Persistence for AI Agent Platforms 2026](https://deepwiki.com/theexperiencecompany/gaia/2.4-data-layer) -- multi-database architecture validation

---
*Research completed: 2026-06-18*
*Ready for roadmap: yes*
