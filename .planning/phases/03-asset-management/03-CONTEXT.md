# Phase 3: Asset Management — Project/Asset/Scan Hierarchy - Context

**Created:** 2026-06-18
**Status:** Placeholder — context gathering not started
**Phase:** 3 of 7 (NEW — inserted during Phase 1 planning update)

## Phase Boundary

本阶段交付：平台提供持久化的安全资产管理能力——用户创建 Project（项目）→ Asset（资产）→ Scan（扫描任务）三级结构。资产类型包括代码仓库、API 端点、环境/域名、凭证。资产清单作为扫描目标的数据源，扫描历史自动关联到对应资产，支持按资产累积发现和趋势分析。

本阶段不交付：SAST 扫描（Phase 4）、DAST 扫描（Phase 5）、Web UI（Phase 6）。

**覆盖需求：** ASSET-01（资产管理）、ENTRY-01（多目标输入）、ENTRY-02（可扩展目标架构）

## Success Criteria (from ROADMAP.md)

1. User can create a Project and register Assets of four types: code repository, API endpoint, environment target, and credential
2. Asset registry is extensible — new AssetProvider subclasses register without scan orchestration changes
3. User can tag assets with labels and filter/search the asset inventory
4. User launches a scan from CLI: `sectest scan --asset <asset-id>` — platform fetches asset config, provisions sandbox, executes pipeline
5. Scan results persisted and linked to source asset — viewing an asset shows complete scan history with findings trend
6. Credential assets encrypted at rest (AES-256-GCM via platform master key), decrypted only in sandbox for scan session

## Blocked Decisions (need discussion)

This phase needs a full `/gsd-discuss-phase 3` session. Key open questions:

- Database schema design: PostgreSQL tables for projects/assets/scans/findings
- AssetProvider interface design — what methods must subclasses implement?
- Credential encryption key management (where is master key stored? How rotated?)
- Asset type taxonomy: are four types sufficient, or should it be open-ended?
- Integration surface with Phase 2 capability registry (how do asset providers register?)

## Canonical References

- `.planning/ROADMAP.md` — Phase 3 definition, success criteria, dependency graph
- `.planning/REQUIREMENTS.md` — ASSET-01, ENTRY-01, ENTRY-02
- `.planning/research/ARCHITECTURE.md` — Data layer section (PostgreSQL for structured storage)

---

*Context placeholder created: 2026-06-18*
*Next: `/gsd-discuss-phase 3`*
