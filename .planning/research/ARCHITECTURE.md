# Architecture Patterns

**Domain:** AI-powered security audit platform (SAST + DAST)
**Researched:** 2026-06-18

## Recommended Architecture

The platform follows a layered architecture with clear component boundaries:

```
┌─────────────────────────────────────────────────────────┐
│                    Interface Layer                       │
│  ┌──────────┐  ┌────────────────────────────────────┐   │
│  │ CLI (TUI)│  │ Web Dashboard (React 19 SPA)        │   │
│  │ Textual  │  │ shadcn/ui + TanStack Query + Zustand│   │
│  └────┬─────┘  └──────────────┬─────────────────────┘   │
│       │                       │ SSE / REST                │
├───────┼───────────────────────┼─────────────────────────┤
│       │         API Layer      │                          │
│       │  ┌─────────────────────▼──────────────────────┐   │
│       │  │ FastAPI 0.136.1 + Uvicorn                 │   │
│       │  │ - REST endpoints for CRUD                  │   │
│       │  │ - SSE streaming for scan progress          │   │
│       │  │ - JWT auth middleware                      │   │
│       │  │ - Pydantic v2 request/response models      │   │
│       │  └──────────────────┬─────────────────────────┘   │
│       │                     │                             │
├───────┼─────────────────────┼───────────────────────────┤
│       │        Agent Orchestration Layer                  │
│       │  ┌──────────────────▼─────────────────────────┐   │
│       │  │ openai-agents SDK 0.17.5                   │   │
│       │  │ - Agent pipeline (Recon→Analysis→Verify)   │   │
│       │  │ - SandboxAgent → DockerSandboxClient       │   │
│       │  │ - RunHooks lifecycle (on_start, on_end)    │   │
│       │  │ - Guardrails (input/output validation)     │   │
│       │  │ - Handoffs (delegation between agents)     │   │
│       │  │ - TraceProcessor → OpenInference spans     │   │
│       │  └───┬──────────────┬─────────────────────────┘   │
│       │      │              │                              │
├───────┼──────┼──────────────┼────────────────────────────┤
│       │      │ Capability    │ Execution                   │
│       │      │ Registry      │ Sandbox                     │
│       │  ┌───▼──────────┐   ┌▼──────────────────────────┐  │
│       │  │ Skill/Tool/   │   │ Docker Kali Sandbox        │  │
│       │  │ Plugin/MCP    │   │ - Ephemeral containers     │  │
│       │  │ Registry      │   │ - Tool execution (shell)   │  │
│       │  │ - Semgrep     │   │ - File system access       │  │
│       │  │ - Bandit      │   │ - Network scanning         │  │
│       │  │ - Nuclei      │   │ - Browser automation       │  │
│       │  │ - Nmap        │   │ - Python runtime           │  │
│       │  │ - FFuf        │   │ - Result persistence       │  │
│       │  │ - SQLMap      │   │   (volume mounts)          │  │
│       │  │ - MCP Clients │   │                            │  │
│       │  └──────────────┘   └────────────────────────────┘  │
│       │                                                     │
├───────┼─────────────────────────────────────────────────────┤
│       │              Data Layer                             │
│       │  ┌──────────┐ ┌──────────┐ ┌────────────────────┐   │
│       │  │PostgreSQL│ │  Redis 7 │ │  ChromaDB 1.5.9    │   │
│       │  │ 16+      │ │          │ │                    │   │
│       │  │- Projects│ │- Sessions│ │ - Code embeddings  │   │
│       │  │- Scans   │ │- Task Q  │ │ - Vuln patterns    │   │
│       │  │- Findings│ │- SSE pub │ │ - Semantic search  │   │
│       │  │- Users   │ │- RateLim │ │ - Per-project      │   │
│       │  │- AuditLog│ │- LLMCache│ │   collections      │   │
│       │  └──────────┘ └──────────┘ └────────────────────┘   │
│       │                                                     │
├───────┼─────────────────────────────────────────────────────┤
│       │         LLM Gateway                                 │
│       │  ┌──────────────────────────────────────────────┐    │
│       │  │ LiteLLM Proxy (internal FastAPI service)     │    │
│       │  │ - 100+ providers via unified API             │    │
│       │  │ - Fallback chains (OpenAI → Anthropic)      │    │
│       │  │ - Cost tracking per model/per scan           │    │
│       │  │ - Rate limit handling                        │    │
│       │  │ - Semantic caching (Redis)                   │    │
│       │  └──────────────────────────────────────────────┘    │
│       │                                                     │
├───────┼─────────────────────────────────────────────────────┤
│       │        Observability                                │
│       │  ┌──────────────────────────────────────────────┐    │
│       │  │ Langfuse v4 (self-hosted)                    │    │
│       │  │ - Agent trace ingestion (OTLP)               │    │
│       │  │ - Token cost attribution per span            │    │
│       │  │ - Prompt management + versioning             │    │
│       │  │ - Eval datasets for vulnerability detection  │    │
│       │  │ - Scan replay from stored traces             │    │
│       │  └──────────────────────────────────────────────┘    │
│       │  ┌──────────────────────────────────────────────┐    │
│       │  │ Prometheus + Grafana                         │    │
│       │  │ - Docker container metrics                   │    │
│       │  │ - API latency/error rates                    │    │
│       │  │ - DB connection pool utilization             │    │
│       │  │ - Redis hit rates                            │    │
│       │  └──────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### Component Boundaries

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| CLI (Textual) | Local TUI for single-machine scanning. Invokes same backend API as web. | FastAPI REST endpoints |
| Web Dashboard (React SPA) | Team-facing UI for project management, scan monitoring, report viewing. | FastAPI REST + SSE endpoints |
| FastAPI Backend | API contract enforcement, auth, data validation, SSE streaming, Celery task dispatch. | PostgreSQL, Redis, Agent Orchestrator |
| Agent Orchestrator (openai-agents SDK) | Multi-agent pipeline execution, handoffs, guardrails, trace export. | LiteLLM Proxy, Capability Registry, Docker Sandbox |
| Capability Registry | Skill/Tool/Plugin/MCP Client registration, discovery, and lifecycle. | Agent Orchestrator (tools passed to agents) |
| Docker Sandbox | Isolated Kali Linux execution environment. Ephemeral per-scan containers. | Agent Orchestrator (via SandboxAgent), Docker Engine API |
| LiteLLM Proxy | LLM provider abstraction, routing, fallback, cost tracking. | Agent Orchestrator (as OpenAI-compatible endpoint) |
| PostgreSQL | Structured data: projects, scans, findings, users, audit trails. | FastAPI Backend, Celery workers |
| Redis | Session cache, task queue (Celery broker), SSE pub/sub, rate limiting, LLM semantic cache. | FastAPI Backend, Celery workers, LiteLLM Proxy |
| ChromaDB | Code embeddings, vulnerability pattern vectors, semantic search. | FastAPI Backend (RAG service), Agent Orchestrator (retrieval tools) |
| Langfuse | Agent trace ingestion, token cost aggregation, prompt registry. | Agent Orchestrator (OpenInference OTLP export) |
| Prometheus + Grafana | Infrastructure metrics, API SLOs, Docker stats. | FastAPI (metrics endpoint), Docker Engine, PostgreSQL exporter |

### Data Flow

**SAST Scan Flow:**
1. User uploads code or provides Git URL via CLI/Web
2. Backend stores project in PostgreSQL, queues scan task (Redis/Celery)
3. Orchestrator spawns ReconAgent → AnalysisAgent → VerificationAgent pipeline
4. ReconAgent: Tree-sitter parses code into AST chunks, embeds via RAG pipeline, stores in ChromaDB
5. AnalysisAgent: Queries ChromaDB for vulnerability patterns, runs Semgrep/Bandit in Docker sandbox, uses LLM (via LiteLLM) for deep analysis
6. VerificationAgent: Generates PoC exploit in sandbox, executes, validates. Retries with self-correction on failure.
7. All agent traces exported to Langfuse via OpenInference OTLP
8. Findings stored in PostgreSQL, streamed to UI via Redis SSE pub/sub
9. Report generated from findings (Jinja2 → PDF/JSON/SARIF)

**DAST Scan Flow:**
1. User provides target URL/endpoint via CLI/Web
2. Backend stores target config in PostgreSQL, provisions ephemeral Kali Docker container
3. ReconAgent: Runs Nmap, subdomain enumeration, service detection in sandbox
4. AnalysisAgent: Runs Nuclei (vulnerability scanning), FFuf (fuzzing), SQLMap (injection testing) in sandbox
5. VerificationAgent: Validates exploitable findings with proof, browser automation (Playwright) for XSS/CSRF
6. Same tracing, storage, and reporting pipeline as SAST

### Patterns to Follow

#### Pattern 1: Sandbox Abstraction Layer

**What:** Wrap openai-agents SDK SandboxAgent/DockerSandboxClient behind a project-specific interface. This insulates the codebase from SDK beta API changes.

**When:** Always. The SandboxAgent is in beta through v0.17.x. GA timeline unknown.

**Example:**
```python
# Our abstraction, not openai-agents directly
class SandboxManager:
    def __init__(self, image: str = "kalilinux/kali-rolling:latest"):
        self._image = image
        self._client = DockerSandboxClient(image=image)

    async def create_session(self, manifest: SandboxManifest) -> SandboxSession:
        """Create ephemeral session. Underlying client may change."""
        return await self._client.create_session(manifest.to_sdk_manifest())

    async def execute(self, session: SandboxSession, command: str) -> str:
        return await session.run_command(command)

    async def destroy(self, session: SandboxSession):
        await self._client.delete_session(session.id)
```

#### Pattern 2: Agent Pipeline with Handoffs

**What:** Sequential pipeline (Recon → Analysis → Verification → Report) using openai-agents SDK handoffs. Each agent specializes in one phase and delegates to the next.

**When:** Primary scan orchestration flow.

#### Pattern 3: Polyglot Persistence with Clear Ownership

**What:** Each data store has a single-owner service that abstracts access. No cross-store joins in application code.

**When:** Every data access.

**Example:**
- `ProjectService` owns PostgreSQL project/finding/scan tables
- `SessionService` owns Redis session/queue/cache keys
- `RAGService` owns ChromaDB collections and retrieval

#### Pattern 4: SSE Streaming for Scan Progress

**What:** FastAPI StreamingResponse with Redis pub/sub backing. Frontend TanStack Query with EventSource.

**When:** Long-running scan operations (minutes to hours).

### Anti-Patterns to Avoid

#### Anti-Pattern 1: Direct SandboxAgent API Usage in Agent Code

**What:** Agents directly importing `from agents.sandbox import SandboxAgent, DockerSandboxClient`.

**Why bad:** The SandboxAgent API is beta and may break. Direct usage scatters the dependency across all agent modules.

**Instead:** Use the SandboxManager abstraction layer. Only SandboxManager imports openai-agents sandbox types.

#### Anti-Pattern 2: Single Database for Everything

**What:** Using only PostgreSQL (even with pgvector) for structured data, sessions, caching, and vector search.

**Why bad:** PostgreSQL is not designed for ephemeral cache workloads or high-dimensional ANN search at scale. Session TTL management in SQL is awkward. Vector search perf degrades without specialized indexing.

**Instead:** Polyglot persistence. PostgreSQL for structured data. Redis for ephemeral state. ChromaDB for vectors.

#### Anti-Pattern 3: Synchronous HTTP Calls in Agent Code

**What:** Using `requests` library in agent tool implementations.

**Why bad:** Blocks the async event loop. Agent execution is IO-bound (LLM API calls, Docker exec, DB queries). Every blocking call cascades to stall all concurrent agents.

**Instead:** `httpx.AsyncClient` for all outbound HTTP. `asyncpg` for PostgreSQL. `redis.asyncio` for Redis.

### Scalability Considerations

| Concern | At 1 user (CLI local) | At 10 users (team server) | At 100+ users (SaaS) |
|---------|----------------------|--------------------------|---------------------|
| Docker sandboxes | Single container at a time. Sequential scans. | Connection pool of 5-10 concurrent containers. Resource limits (CPU/memory per container). | Kubernetes pod per scan with node taints for Kali images. GPU node pools for local LLM. |
| PostgreSQL | SQLite could suffice but stick with PostgreSQL for consistency. | Connection pool: 20 (pool_size) + 30 (max_overflow). | Read replicas for report queries. PgBouncer for connection pooling. |
| Redis | Single instance, no persistence needed. | Single instance with AOF persistence. | Redis Cluster for sharding. Separate instances for cache vs queue vs pub/sub. |
| ChromaDB | Embedded PersistentClient (single process). | Embedded PersistentClient still works for <1M vectors. | ChromaDB server mode or migration to Qdrant for >1M vectors. |
| LLM costs | Direct provider billing. LiteLLM SDK mode. | LiteLLM Proxy for centralized cost tracking. Redis semantic cache to reduce repeat LLM calls. | Per-team virtual keys with budgets. ML-powered routing for cost optimization. |
| Observability | Langfuse local (Docker Compose). | Langfuse with PostgreSQL + ClickHouse backend. | Langfuse Cloud or self-hosted with separate tracing DB. |
