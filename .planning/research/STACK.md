# Technology Stack

**Project:** Sectest -- Unified AI Security Testing Platform
**Researched:** 2026-06-18
**Overall confidence:** HIGH

## Recommended Stack

### Core Runtime

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Python | 3.12+ | Backend runtime | openai-agents SDK is Python-only; 3.12 is the current stable with mature async support. 3.13 production-stable as of 2026. |
| uv | latest | Package manager | Faster than pip (rust-based), replaces pip/poetry/pipenv. Both reference projects (Sectest, DeepAudit) use uv. |

### Agent Framework

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| openai-agents SDK | 0.17.5 | Multi-agent orchestration | MIT-licensed, production-grade as of 2026. SandboxAgent abstraction maps directly to Kali Docker sandboxes. Built-in handoffs, guardrails, streaming execution loop, RunHooks lifecycle. 22k+ GitHub stars. The April 2026 enterprise update (v0.14+) added provider-agnostic LLM support, long-horizon harnesses, and built-in tracing. |

**What NOT to use:** LangChain/LangGraph. While DeepAudit uses it (AGPL-3.0), openai-agents SDK is the superior choice for this project because: (1) SandboxAgent maps directly to our Kali Docker execution model, (2) native streaming execution loop with span-level tracing, (3) MIT license avoids AGPL constraints, (4) lighter weight -- fewer abstraction layers.

### LLM Provider Routing

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| LiteLLM | latest | Multi-LLM provider routing | De facto standard. 100+ providers through a single OpenAI-compatible API. Proxy mode for centralized key management + cost tracking + fallback chains. Native openai-agents SDK integration via custom ModelProvider. |

**Integration pattern:** Use LiteLLM Proxy (FastAPI service) as an internal gateway. The openai-agents SDK connects via a custom `ModelProvider` that points at the proxy's OpenAI-compatible endpoint. This gives us: provider switching without code changes, per-model cost tracking, automatic fallback on rate limits, and Redis-backed semantic caching to reduce API costs.

### Web API Framework

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| FastAPI | 0.136.1 | REST API backend | De facto standard for Python AI APIs (38% dev adoption, growing). Native async, automatic OpenAPI docs, Pydantic v2 validation. Used by both reference projects. |
| Uvicorn | 0.47.0 | ASGI server | Standard production ASGI server for FastAPI. |
| Pydantic | 2.13.x | Data validation | Rust-backed v2 core. `from_attributes=True` replaces `orm_mode`. v2 is required (v1 dropped in FastAPI >=0.128.0). |
| SQLAlchemy | 2.0.50 | ORM | Full async support via `AsyncSession` + `create_async_engine`. Use 2.0-style `select()` with `Mapped` annotations, NOT legacy `Column()` / `.query()`. |
| Alembic | 1.18.4 | Database migrations | Standard migration tool for SQLAlchemy. |
| asyncpg | 0.31.0 | Async PostgreSQL driver | Fastest async driver. Use `postgresql+asyncpg://` in connection strings. |

**What NOT to use:** Django. While Django has stronger built-in security (CSRF, XSS, clickjacking), FastAPI's async-native design and Pydantic validation are critical for LLM API call patterns where every endpoint blocks on external IO. Django's sync-first ORM is a bottleneck here.

### Database Layer

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| PostgreSQL | 16+ | Primary structured storage | ACID transactions, pgvector extension for hybrid vector+relational queries, mature connection pooling. Standard choice for AI agent platforms storing scan results, user data, agent state. |
| Redis | 7+ | Cache, queue, sessions | Multi-role: (1) Agent session state with TTL, (2) task queue via ARQ/BullMQ, (3) SSE pub/sub for real-time scan streaming, (4) rate limiting, (5) LiteLLM semantic cache. DeepAudit reference uses Redis 7 identically. |
| ChromaDB | 1.5.9 | RAG vector store | Apache 2.0, Rust core (4x faster vs pre-1.0), zero-config embedded mode. Perfect for code semantic indexing -- `PersistentClient` with HNSW indexing, per-project collection isolation. Used by DeepAudit. |

**Polyglot persistence rationale:** Each database serves a fundamentally different access pattern. PostgreSQL for relational data (scan results, projects, users, audit trails), Redis for ephemeral low-latency state (agent sessions, streaming events, queues, rate limiting), ChromaDB for high-dimensional semantic search (code embeddings, vulnerability pattern matching). Consolidating onto a single store would compromise performance at each tier.

**pgvector note:** PostgreSQL's pgvector extension can handle vector search and some deployments choose it over ChromaDB. However, ChromaDB's specialized HNSW indexing and embedding function integration (OpenAI, Ollama, HuggingFace) make it the better choice for RAG pipelines in the 2026 ecosystem.

### Frontend Framework

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| React | 19.2.7 | UI framework | React Compiler (auto-memoization), `use()` hook, Server Components. React 18 is security-patches-only. |
| TypeScript | 5.7+ | Type safety | Strict mode. Industry standard for React projects. |
| Vite | 8+ | Build tool | CRA deprecated Feb 2025; Vite is the official React recommendation. Rolldown-powered build. |
| shadcn/ui | latest | Component library | 42% usage in 2024 State of React survey, overtaking MUI. Accessible, customizable, Tailwind-native. |
| Tailwind CSS | 4.x | Styling | Utility-first. Pairs natively with shadcn/ui. |
| TanStack Query | 5.101.0 | Server state management | Stale-while-revalidate, cache invalidation, background refetching. Standard for API-driven dashboards. |
| Zustand | 5.0.14 | Client state management | ~1.2 KB gzipped, 14.2M weekly downloads (overtook Redux in 2025). For UI state (filters, theme, sidebar). |
| Recharts | latest | Charting | For common chart types in security dashboards (severity distribution, timeline, findings breakdown). |

**What NOT to use:** Redux Toolkit. Zustand has overtaken RTK in weekly downloads (14.2M vs 9.8M) and is 10x smaller. For a security dashboard with moderate client state (filters, selected project, UI toggles), RTK's middleware/action/reducer ceremony is unnecessary overhead. MUI is also not recommended -- shadcn/ui's Tailwind-native approach gives us full control over the security dashboard's visual language without fighting a design system.

### Docker Sandbox Management

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Docker Engine API | latest | Sandbox lifecycle | Programmatic container management via `docker` Python SDK. |
| Kali Linux Docker image | kalilinux/kali-rolling | Security tool environment | Single unified image with complete toolchain. Upstream maintained. Avoids custom tool image maintenance. ~3GB pull size. |
| openai-agents SandboxAgent | 0.17.5 | Agent-sandbox binding | SandboxAgent abstraction binds an LLM agent to a Docker container with capabilities (shell, filesystem, memory). Each scan session gets an ephemeral container -- "gold copy" model. |

**Isolation pattern (least privilege):**
```yaml
cap_add:
  - NET_ADMIN    # For Nmap, Metasploit
  - NET_RAW      # For raw socket tools
  - SYS_PTRACE   # For debugging/profiling tools
# Never use --privileged
# Never use --network host unless scanning a local subnet
```
Each scan session creates an ephemeral container from the Kali gold image, runs the toolchain, persists results to a Docker volume, then destroys the container. The gold image is never modified -- tools are pre-installed in the Dockerfile build stage.

**openai-agents SandboxAgent integration:** The SandboxAgent maps naturally to this pattern: each agent in the reconnaissance/analysis/verification pipeline gets a SandboxSession backed by `DockerSandboxClient`. The Manifest declares which files (source code, configuration) and capabilities (shell, filesystem) the agent needs. The Docker client provisions an ephemeral Kali container, mounts the workspace, and tears it down after the session.

### MCP (Model Context Protocol) Integration

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| mcp (Official SDK) | 1.27.1 | MCP client/servers | Official Python SDK for MCP. v1.x stable (maintenance mode). v2 alpha available, stable expected July 2026. |
| FastMCP | latest (SDK bundled) | Rapid MCP prototyping | High-level API incorporated into official SDK. `@mcp.tool()` decorator pattern. 70%+ of MCP servers use FastMCP. |

**Integration pattern:** MCP servers wrap external security tools (e.g., an MCP server for Semgrep, an MCP server for Nmap). The openai-agents SDK agents connect as MCP clients via `mcp.ClientSession`, discovering tools dynamically. This follows the project's Skill/Tool/Plugin/MCP Client four-layer capability architecture -- MCP servers are the "external ecosystem" layer.

**Protocol versions:** Target `2025-06-18` (latest) with fallback to `2025-03-26` (stable).

### Observability Stack

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Langfuse | 4.7.1 (Python SDK) | Tracing, prompt management, evals | Self-hosted (MIT core), first-class openai-agents SDK integration via OpenInference instrumentation. Observations-first architecture in v4. Tracks agent execution traces, token costs, handoffs, tool calls. |
| OpenInference | latest | OpenTelemetry spec | Apache 2.0 spec for AI span kinds (CHAIN, LLM, RETRIEVER, TOOL, AGENT). Used by Langfuse, Arize Phoenix, and Grafana. Spans auto-exported from openai-agents SDK. |
| OpenTelemetry | latest | Standard trace/span wire protocol | OTLP exporter for Langfuse ingestion. Standard `gen_ai.*` semantic conventions. |
| structlog | latest | Structured logging | Standard for Python async apps. JSON-formatted logs with trace context (trace_id, span_id). |
| Prometheus + Grafana | latest | Metrics and dashboards | Standard for infrastructure metrics (Docker container stats, API latency, DB pool utilization). |

**What NOT to use:** LangSmith. While it has native LangGraph/LangChain semantics, it's closed-source (MIT SDK only) and LangChain-centric -- wrong fit for an openai-agents SDK project. Arize Phoenix is a strong alternative but Langfuse's self-hosted MIT core + prompt management + dataset features make it the better OSS choice.

**Trace architecture:**
```
openai-agents SDK (built-in tracing)
  → OpenInference OTel spans
    → OTLP exporter
      → Langfuse ingestion (v4 observations)
        → Dashboard: agent traces, token $, handoff graphs, tool call latency
```

### Infrastructure & Deployment

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Docker Compose | v2.x | Multi-service orchestration | Define PostgreSQL, Redis, ChromaDB, LiteLLM Proxy, FastAPI backend, React frontend as services. |
| Nginx | latest | Reverse proxy + static serving | Terminate TLS, serve React static build, proxy /api to FastAPI. Security headers (CSP, HSTS, X-Frame-Options). |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| httpx | latest | Async HTTP client | All outbound HTTP calls (API integrations, webhooks). Replaces `requests` in async contexts. |
| python-jose | 3.5.0 | JWT authentication | Token generation/validation for API auth. |
| passlib[bcrypt] | latest | Password hashing | User authentication. |
| Celery | latest | Background task queue | Long-running scan tasks. Redis as broker, PostgreSQL as result backend. |
| docker-py | latest | Docker SDK for Python | Programmatic container lifecycle management from the backend. |
| tree-sitter | latest | AST-based code parsing | Semantic code chunking for RAG indexing (inherited from DeepAudit's approach). |
| bandit | latest | Python SAST | Integrated as a Tool in the capability registry. |
| semgrep | latest | Multi-language SAST | Integrated as a Tool in the capability registry. |

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Agent framework | openai-agents SDK | LangChain/LangGraph | AGPL license constraints (DeepAudit is AGPL-3.0), heavier abstraction layers, no SandboxAgent equivalent |
| Agent framework | openai-agents SDK | CrewAI | Role-decomposable pipelines but no sandbox abstraction, less mature tracing |
| Agent framework | openai-agents SDK | Pydantic AI | Type-safe but lacks multi-agent primitives (handoffs, guardrails, sandboxes) |
| Web framework | FastAPI | Django | Sync-first ORM is an async bottleneck for LLM API calls |
| Web framework | FastAPI | Litestar | ~2x serialization speed but smaller ecosystem, fewer AI integration examples |
| Frontend state | Zustand | Redux Toolkit | 10x larger bundle, more ceremony, fewer weekly downloads in 2026 |
| Frontend components | shadcn/ui | MUI | shadcn/ui gives full visual control; MUI constrains to Material Design |
| Vector store | ChromaDB | pgvector | ChromaDB's HNSW indexing and embedding functions are purpose-built for RAG; pgvector is a bolt-on |
| Vector store | ChromaDB | Qdrant | Qdrant is more scalable but requires separate deployment; ChromaDB's embedded mode is simpler for single-machine |
| Observability | Langfuse | LangSmith | Closed-source, LangChain-centric |
| Observability | Langfuse | Arize Phoenix | Phoenix is strong but Langfuse's prompt management + MIT license + v4 observations-first architecture is better for OSS |
| LLM routing | LiteLLM | Custom provider wrappers | LiteLLM is the de facto standard; custom wrappers duplicate 100+ provider integrations |
| Docker sandbox | openai-agents SandboxAgent | Custom docker-py wrapper | SandboxAgent provides declarative manifests, capability system, session management, and state serialization out of the box |
| MCP client | Official mcp SDK + FastMCP | Dedalus MCP | Dedalus is leaner (122 KB vs 8.2 MB) but the official SDK has broader ecosystem support and is the spec reference implementation |

## Installation

```bash
# Core agent framework
uv add "openai-agents[docker]"      # openai-agents SDK + Docker sandbox support
uv add "openai-agents[redis]"       # Redis-backed sessions

# LLM routing
uv add litellm

# Web API
uv add "fastapi[standard]" uvicorn[standard]
uv add sqlalchemy[asyncio] alembic asyncpg
uv add pydantic

# MCP
uv add "mcp[cli]"                   # Official MCP SDK (v1.x, pin <2)

# Observability
uv add langfuse openinference-instrumentation-openai-agents
uv add opentelemetry-sdk opentelemetry-exporter-otlp
uv add structlog

# Database clients
uv add redis[hiredis] chromadb

# Auth
uv add python-jose[cryptography] passlib[bcrypt]

# Infrastructure
uv add docker celery httpx

# SAST integration
uv add bandit semgrep tree-sitter

# Dev dependencies
uv add --dev pytest pytest-asyncio pytest-cov
uv add --dev ruff mypy pre-commit
```

## Sources

- [OpenAI Agents SDK v0.17.5 -- GitHub](https://github.com/openai/openai-agents-python) -- HIGH confidence
- [OpenAI Agents SDK Sandbox Agents Quickstart](https://openai.github.io/openai-agents-python/sandbox_agents/) -- HIGH confidence
- [Sectest (usestrix/strix) -- GitHub](https://github.com/usestrix/strix) -- HIGH confidence (reference architecture)
- [DeepAudit (lintsinghua/DeepAudit) -- GitHub](https://github.com/lintsinghua/DeepAudit) -- HIGH confidence (reference architecture)
- [LiteLLM + OpenAI Agents SDK Integration](https://docs.litellm.ai/docs/tutorials/openai_agents_sdk) -- HIGH confidence
- [FastAPI 0.136.1 Production Stack 2026](https://tech-insider.org/fastapi-tutorial-python-rest-api-13-steps-2026/) -- HIGH confidence
- [React 19 + Vite + shadcn/ui Dashboard Guide 2026](https://www.usedatabrain.com/how-to/create-react-dashboard) -- HIGH confidence
- [Langfuse Python SDK v4](https://github.com/langfuse/langfuse-python) -- HIGH confidence
- [MCP Python SDK v1.27.1](https://pypi.org/project/mcp/1.27.1/) -- HIGH confidence
- [ChromaDB v1.5.9](https://cookbook.chromadb.dev/) -- HIGH confidence
- [Docker Kali Linux Security Tools Best Practices 2026](https://oneuptime.com/blog/post/2026-02-08-how-to-run-kali-linux-tools-in-docker/view) -- MEDIUM confidence
- [AI Agent Observability Tools Comparison 2026](https://futureagi.com/blog/best-ai-agent-observability-tools-2026/) -- MEDIUM confidence
- [SQLAlchemy 2.0 async PostgreSQL Best Practices 2026](https://nerdleveltech.com/courses/build-production-rest-api/learn/database-layer/production-database-design) -- HIGH confidence
- [Polyglot Persistence for AI Agent Platforms 2026](https://deepwiki.com/theexperiencecompany/gaia/2.4-data-layer) -- MEDIUM confidence
