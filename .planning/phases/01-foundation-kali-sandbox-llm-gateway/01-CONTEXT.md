# Phase 1: Foundation — Kali Sandbox + LLM Gateway - Context

**Gathered:** 2026-06-18
**Status:** Ready for planning

## Phase Boundary

本阶段交付：平台能够创建和管理 Kali Linux Docker 沙箱容器，并通过 LLM 驱动的 Agent 在沙箱中执行安全工具，建立核心的 agent-sandbox-tool 执行闭环。

本阶段不交付：多 Agent 流水线（Phase 2）、CLI 接口（Phase 3）、Web 面板（Phase 5）。

**覆盖需求：** CORE-01（Kali 沙箱管理）、CORE-03（LiteLLM LLM 网关）

## Implementation Decisions

### 容器生命周期（沙箱管理）

- **D-01: Per-scan 容器策略** — 每次扫描使用一个长生命周期 Kali 容器，所有工具共享文件系统和网络状态。不每次工具调用创建新容器。
- **D-02: Lazy init 创建时机** — 扫描开始时创建容器（同步等待容器就绪），不在平台启动时预创建/预热容器池。
- **D-03: 延迟销毁** — 扫描完成后保留容器用于调试，不立即销毁。
- **D-04: 保留时长 15 分钟** — 扫描结束后容器存活 15 分钟，给用户窗口期 `docker exec` 检查现场。超时后自动清理。

### 已锁定决策（从 PROJECT.md 和调研继承，无需重新讨论）

- **L-01: openai-agents SDK SandboxAgent** — 底层使用 SandboxAgent + DockerSandboxClient（SDK 0.17.5）。Agent 代码永远不直接 `from agents.sandbox import`。
- **L-02: SandboxManager 抽象层** — 封装所有沙箱 API 调用，隔离 SDK beta API 变更风险。仅 SandboxManager 导入 `agents.sandbox` 类型。
- **L-03: Kali 黄金镜像** — 使用 `kalilinux/kali-rolling` 作为统一沙箱镜像。上游维护，避免多镜像维护负担。
- **L-04: 最小权限能力** — `NET_ADMIN`、`NET_RAW`、`SYS_PTRACE`。决不用 `--privileged` 或 `--network host`。
- **L-05: LiteLLM LLM 网关** — 提供商路由和故障切换。至少支持 OpenAI + Anthropic 双提供商。
- **L-06: 平台启动预拉取镜像** — 不在首次扫描时懒拉取 Kali 镜像，平台启动时预拉取。
- **L-07: 结构化工具输出解析** — 每个工具的输出在送入 LLM 之前解析为结构化格式（JSON/SARIF/XML），不直接喂原始文本。
- **L-08: 自动清理** — 沙箱容器在扫描完成或出错后自动清理（通过延迟销毁计时器或错误处理路径）。

### Claude's Discretion

以下领域由下游 Agent（researcher、planner）自行决定，无需用户再确认：
- 容器资源限制的具体数值（CPU/memory 配额）
- Docker volume 挂载策略的细节
- 容器日志收集和持久化方式
- 镜像拉取进度展示的具体 UI/CLI 实现

## Canonical References

**下游 Agent 在规划和实施前必须阅读。**

### 项目核心
- `.planning/ROADMAP.md` — 6 阶段路线图，Phase 1 目标、成功标准、依赖关系
- `.planning/PROJECT.md` — 项目定义、核心价值、关键决策记录
- `.planning/REQUIREMENTS.md` — 22 条 v1 需求（CORE-01、CORE-03 由 Phase 1 覆盖）、追溯矩阵

### 架构与调研
- `.planning/research/ARCHITECTURE.md` — 六层架构设计、数据流、模式（Sandbox Abstraction、Agent Pipeline、Polyglot Persistence、SSE Streaming）、反模式
- `.planning/research/STACK.md` — 完整技术栈（openai-agents SDK 0.17.5、FastAPI 0.136.1、Docker Kali Sandbox、LiteLLM 集成模式、MCP 集成模式、Langfuse 追踪架构）
- `.planning/research/FEATURES.md` — 功能全景、MVP 优先级建议、反功能清单
- `.planning/research/SUMMARY.md` — 执行摘要、关键发现、风险与缓解

### 外部参考
- [openai-agents SDK Sandbox Agents Quickstart](https://openai.github.io/openai-agents-python/sandbox_agents/) — Docker sandbox 集成模式，SandboxAgent 生命周期 API
- [LiteLLM + OpenAI Agents SDK Integration](https://docs.litellm.ai/docs/tutorials/openai_agents_sdk) — LiteLLM Proxy 配置、自定义 ModelProvider 集成

## Existing Code Insights

### 代码库现状

项目处于初始化阶段——无 Python 源码、无 Docker 配置、无前端代码。仅有 `.planning/` 下的规划文档和 `CLAUDE.md`。

### 影响 Phase 1 的关键点

- **空白画布** — 没有需要遵循的现有代码模式或需要兼容的 API 契约。Phase 1 的代码将成为所有后续阶段的基准模式。
- **SandboxManager 是第一个架构锚点** — 这个抽象层的接口设计会直接影响 Phase 2-4 所有 Agent 的沙箱使用方式。必须从一开始就正确设计。
- **项目结构需要建立** — Phase 1 执行时需要创建 `src/` 根目录、`pyproject.toml`（uv 管理）、基础包布局。

## Specific Ideas

无特定用户偏好——按标准方式实现。

## Deferred Ideas

None — 讨论过程未超出阶段范围。

---

*Phase: 1-Foundation-Kali-Sandbox-LLM-Gateway*
*Context gathered: 2026-06-18*
