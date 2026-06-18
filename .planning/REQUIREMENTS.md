# Requirements: Strix — Unified AI Security Testing Platform

**Defined:** 2026-06-18
**Core Value:** AI agent 能够自主完成从代码审计到动态渗透的端到端安全评估，在 Kali 沙箱中运行真实安全工具，通过 PoC 严格验证每个发现的漏洞，输出可操作的安全报告。

## v1 Requirements

### 用户入口

- [ ] **ENTRY-01**: 平台支持多目标、多模式组合输入——单次扫描可同时传入代码仓库（Git URL/本地路径）、Web URL、SSH 凭证、IP 范围等多种目标类型
- [ ] **ENTRY-02**: 用户入口的输入模式采用可扩展架构——新增目标类型（如 Kubernetes cluster、S3 bucket）只需实现 TargetProvider 接口并注册到能力中心
- [ ] **ENTRY-03**: 平台提供 CLI 命令行工具——支持 `strix scan --target <url|repo|ssh|ip>` 多目标本地扫描，终端输出实时进度和报告摘要
- [ ] **ENTRY-04**: 平台提供 Web 管理界面——Vue 3 + Vite 前端，支持 SSE 实时推送扫描进度、项目管理、报告查看

### 核心引擎

- [ ] **CORE-01**: 平台能创建和管理 Docker Kali Linux 沙箱容器（镜像预拉取、容器生命周期、资源限制、自动清理）
- [ ] **CORE-02**: 平台实现多 Agent 协作框架——支持两种模式：（1）顺序流水线模式（Recon → Analysis → Verification → Report）通过 openai-agents SDK handoff 机制传递结构化摘要；（2）动态探索模式——各阶段 Agent 可在内部动态 spawn 子 Agent 深入挖掘特定漏洞路径，子 Agent 独立运行、回报结果后销毁
- [ ] **CORE-03**: 平台集成 LiteLLM Proxy 作为 LLM 网关——支持多提供商路由、自动 Fallback、按模型/扫描追踪成本
- [ ] **CORE-04**: 平台实现 Skill（Markdown 知识）/ Tool（沙箱执行）/ Plugin（Skill+Tool 组合）/ MCP Client 四层能力注册中心，支持运行时注册与发现

### 灰盒扫描

- [ ] **GBOX-01**: 平台支持通过 SSH 凭证连接目标内网系统——在 Kali 沙箱中建立 SSH 连接，执行文件系统扫描、进程/服务枚举、配置审计、内网横向移动探测
- [ ] **GBOX-02**: 平台支持通过 MCP Client 接入远程安全工具 MCP Server——远程工具能力自动注册到能力中心，Agent 通过 MCP 协议调用远程执行

### SAST 静态代码审计

- [ ] **SAST-01**: 平台支持三种源码导入方式——Git 仓库 clone、ZIP 压缩包上传、本地路径指定
- [ ] **SAST-02**: 平台集成 Semgrep（多语言规则扫描）和 Bandit（Python 专项安全检查）作为 SAST 工具
- [ ] **SAST-03**: 平台能对 SAST 发现的疑似漏洞在 Kali 沙箱中自动生成 PoC 脚本，执行验证，失败时自修复重试（最多 3 次）

### DAST 动态渗透测试

- [ ] **DAST-01**: 平台能在 Kali 沙箱中运行侦察工具——Nmap 端口/服务扫描、子域名枚举、攻击面映射
- [ ] **DAST-02**: 平台能在 Kali 沙箱中运行漏洞扫描工具——Nuclei 模板扫描、FFuf Web 模糊测试、SQLMap 注入测试
- [ ] **DAST-03**: 平台能在 Kali 沙箱中运行浏览器自动化——Playwright 驱动的 XSS、CSRF、认证流程测试
- [ ] **DAST-04**: 平台能在 Kali 沙箱中运行 HTTP 代理——请求拦截、重放、篡改（如 mitmproxy/Caido），代理流量可供 Agent 查询和分析

### 报告与部署

- [ ] **RPT-01**: 平台能生成可交付的安全审计报告——PDF（正式审计报告）+ Markdown（技术详情），包含漏洞描述、严重等级、PoC、修复建议
- [ ] **RPT-02**: 平台支持通过 Docker Compose 在单机上一键部署全部服务（后端、前端、PostgreSQL、Redis、LiteLLM Proxy、Kali 沙箱）
- [ ] **RPT-03**: 平台支持部署到远程服务器——多用户可通过 Web 面板并发创建和管理扫描任务

### 高级能力

- [ ] **ADV-01**: 平台支持扫描回放——使用相同的 Agent 状态和输入重新执行历史扫描，以及基于 Git diff 的增量扫描
- [ ] **ADV-02**: 平台的漏洞检测覆盖 OWASP Top 10 所有类别，输出报告支持 CWE 编号映射

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### 核心引擎

- **CORE-05**: Langfuse 分布式追踪——Agent 执行链路可视化、Token 消耗归因、Prompt 版本管理
- **CORE-06**: OS Agent 部署模式——轻量 Python agent 通过安全通道回连平台，在目标系统执行命令和文件访问，适合长时间深度审计

### SAST 静态代码审计

- **SAST-04**: RAG 代码语义索引——Tree-sitter AST 解析生成代码向量嵌入，ChromaDB 存储，支持跨文件语义漏洞搜索

### DAST 动态渗透测试

- **DAST-05**: PoC 自动生成覆盖 DAST 发现的漏洞（v1 仅 SAST 支持 PoC 验证）

### 部署与运维

- **RPT-04**: JWT + RBAC 多用户认证与权限管理
- **RPT-05**: 多租户数据隔离——用户间的项目、扫描、报告数据互相不可见

### 高级能力

- **ADV-03**: CI/CD 集成——GitHub Action / GitLab CI 触发自动安全扫描
- **ADV-04**: 自定义扫描规则——用户可编写 YAML 规则文件定义新的漏洞检测模式和 PoC 模板

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| 生产环境 WAF/RASP 部署 | 聚焦审计和测试，不涉及运行时防护 |
| 移动端 App 渗透测试 | v1 聚焦 Web 应用和代码仓库 |
| GUI 安全工具集成（Burp Suite 等） | Kali Docker 跑 headless，GUI 工具不可自动化 |
| 自定义 LLM 训练/微调 | GPU 基础设施成本高，Prompt Engineering + RAG 已满足需求 |
| 实时攻击面持续监控 | 不同产品品类（点式审计 vs 持续监控） |
| 非 Docker 部署方式 | 架构强依赖 Docker 沙箱 |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| ENTRY-01 | — | Pending |
| ENTRY-02 | — | Pending |
| ENTRY-03 | — | Pending |
| ENTRY-04 | — | Pending |
| CORE-01 | — | Pending |
| CORE-02 | — | Pending |
| CORE-03 | — | Pending |
| CORE-04 | — | Pending |
| GBOX-01 | — | Pending |
| GBOX-02 | — | Pending |
| SAST-01 | — | Pending |
| SAST-02 | — | Pending |
| SAST-03 | — | Pending |
| DAST-01 | — | Pending |
| DAST-02 | — | Pending |
| DAST-03 | — | Pending |
| DAST-04 | — | Pending |
| RPT-01 | — | Pending |
| RPT-02 | — | Pending |
| RPT-03 | — | Pending |
| ADV-01 | — | Pending |
| ADV-02 | — | Pending |

**Coverage:**
- v1 requirements: 22 total
- Mapped to phases: 0
- Unmapped: 22 ⚠️

---
*Requirements defined: 2026-06-18*
*Last updated: 2026-06-18 after initial definition*
