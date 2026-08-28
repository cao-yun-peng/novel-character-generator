# 当前实现状态：哪些能用，哪些还只是设计

> [← 项目总览](00-start-here.md) · [文档索引](README.md) · [代码导航 →](00-code-navigation.md)
>
> 文档版本：3.5 · 状态快照日期：2026-08-27 · 项目版本：0.1.0

## 怎么理解状态

| 状态 | 含义 |
|---|---|
| 已实现 | 有实际代码入口和自动测试，能够从 API、Service、Worker 或 Repository 使用 |
| 部分实现 | 核心模型或局部能力已存在，但默认关闭、缺少上游/下游步骤，或尚未形成完整用户流程 |
| 仅设计 | 技术文档已定义，但尚无对应的可运行实现 |
| 二期 | 明确不属于当前一期交付范围 |

本表以当前源码、API、Worker 和测试为依据。运行时还可以查询 [`GET /api/v1/capabilities`](../src/novel_character_generator/api/routes/capabilities.py)，它是部署实例对外声明能力的直接入口。

## 功能状态总表

| 功能 | 用户能得到什么 | 状态 | 代码或测试证据 |
|---|---|---|---|
| 健康检查与 API Key | 存活/就绪检查，普通与管理员权限分离 | 已实现 | [`app.py`](../src/novel_character_generator/api/app.py)、[`auth.py`](../src/novel_character_generator/api/auth.py)、[`test_health.py`](../tests/integration/test_health.py) |
| TXT 小说上传 | 创建小说和第一个不可变源文档版本 | 已实现 | [`novels.py`](../src/novel_character_generator/api/routes/novels.py)、[`ingestion_service.py`](../src/novel_character_generator/application/services/ingestion_service.py) |
| 源文档版本 | 中途重新上传时保留历史版本和替代关系 | 已实现 | [`document.py`](../src/novel_character_generator/domain/entities/document.py)、[`test_document_versions.py`](../tests/integration/test_document_versions.py) |
| 章节识别与分块 | 规范化文本、识别章节、生成稳定文本块 | 已实现 | [`text_processing.py`](../src/novel_character_generator/domain/policies/text_processing.py)、[`ingestion.py`](../src/novel_character_generator/workers/handlers/ingestion.py) |
| 文本分析 Run | 一次请求顺序执行分块、角色提取、人物阶段解析和外观聚合 | 已实现 | [`novels.py`](../src/novel_character_generator/api/routes/novels.py)、[`test_text_analysis_run.py`](../tests/integration/test_text_analysis_run.py) |
| 角色与视觉事实提取 | 提取局部人物 mention、原子视觉字段、显式时间信号及精确原文证据 | 已实现基础（R1 v3.1 + R2 解析主链） | Provider 返回 `VisualCandidateExtractionResult` v3.1；服务端 locator 形成带稳定 mention_id 的候选包，不再按 `representative_name` 直接创建人物。实体解析模型逐 Chunk 读取累计记忆，每 10 Chunk 固定收敛，尾批执行最终收敛；只有 final 人物绑定生成 pending Observation。见 [`entity_resolution.py`](../src/novel_character_generator/application/ports/entity_resolution.py)、[`extraction.py`](../src/novel_character_generator/workers/handlers/extraction.py)和[R2 人物实体解析契约](24-character-entity-resolution-contract.md) |
| R3 人物阶段与时间作用域 | 将已归属人物的观察绑定到 timeline、人生阶段、呈现/现实状态、形态和章节范围；歧义失败关闭 | 已实现基础 | 独立 `resolve_character_phases` Worker 位于 R2 与聚合之间；final 观察激活，`needs_review` 保持 pending；提供审核、阶段查询和 revision 修订 API。见 [`phase_resolution_service.py`](../src/novel_character_generator/application/services/phase_resolution_service.py)、[`phase_resolution.py`](../src/novel_character_generator/workers/handlers/phase_resolution.py)、[`test_phase_resolution_pipeline.py`](../tests/integration/test_phase_resolution_pipeline.py)和[R3 契约](25-character-phase-resolution-contract.md) |
| 细粒度文本库与混合召回 | 上传后建立 1K/100 passage、中文 BM25、向量召回、RRF 融合和邻居上下文 | 已实现基础 | 已有检索表迁移、`source_indexing` Run、安全切分、FTS5/BM25、OpenAI-compatible EmbeddingPort、Qdrant Local、批量续建、RRF、实体加分、同章双向邻居和证据区间映射；Embedding 未配置时明确降级，完整黄金集评测仍待执行 |
| 检索增强角色视觉精提取 | 只对选定角色/字段组召回证据并精提取；推断进入审核建议 | 已实现基础 | 字段组按维度完整度评分；生理年龄阶段与小说内具体人生阶段分离，只有唯一映射时自动解析，阶段查询排除无阶段事实，避免跨阶段污染。见 [`visual_enrichment_service.py`](../src/novel_character_generator/application/services/visual_enrichment_service.py)、[`visual_query_plan.py`](../src/novel_character_generator/domain/policies/visual_query_plan.py) 和 [`test_visual_query_plan.py`](../tests/unit/domain/test_visual_query_plan.py) |
| Direct → Visual Evidence Agent 路由 | 根据 Direct 持久化结果、人物/阶段状态、证据覆盖和预算，确定性路由到完成、Agent、实体/阶段审核、`not_stated` 或停止 | 仅设计 | 当前 visual-enrichment 是固定 Direct 流水线；`DirectEnrichmentOutcome`、原因码、RoutingPolicy 和 Agent Worker 尚未实现。通用 AgentRuntime 已有，目标契约见[Agent 增强架构](07-agent-architecture.md)和[视觉精提取设计 21.5.2](21-retrieval-augmented-visual-enrichment.md) |
| Mock/远程 LLM Provider | 本地稳定测试或调用 OpenAI-compatible 结构化输出 | 已实现 | [`mock.py`](../src/novel_character_generator/infrastructure/llm/mock.py)、[`workers/main.py`](../src/novel_character_generator/workers/main.py) |
| Run 查询、SSE、取消和重试 | 查看进度，断线后续传事件，取消或重试任务 | 已实现 | [`runs.py`](../src/novel_character_generator/api/routes/runs.py)、[`run_service.py`](../src/novel_character_generator/application/services/run_service.py) |
| Worker 租约与恢复 | claim、checkpoint、retry、fencing，避免旧 Worker 写入 | 已实现 | [`task_claim.py`](../src/novel_character_generator/workers/task_claim.py)、[`test_task_recovery.py`](../tests/integration/test_task_recovery.py) |
| 外部操作账本 | 保存幂等键、提交状态和租约代次 | 部分实现 | [`external_operations.py`](../src/novel_character_generator/infrastructure/db/repositories/external_operations.py) 已有仓储和测试，但 capability 中 reconciliation 仍为 `false` |
| 时间线、事件和场景查询 | 查看已有或人工创建的故事时间结构与场景绑定 | 部分实现 | Story ORM、[`story.py`](../src/novel_character_generator/api/routes/story.py)和[`story_service.py`](../src/novel_character_generator/application/services/story_service.py)保留；v3 视觉抽取不再自动生产场景/时间线，新的按需生产步骤待实现 |
| 场景时间绑定修正 | 人工修改已有 scene 的 timeline/event/reality status，使用 revision 防冲突 | 已实现 API，缺少 v3 上游 | 修正服务和路由保留；旧联合抽取测试夹具已随 v2 写入入口删除 |
| 角色合并与拆分 | 修正重复人物或错误共指，并保留审计记录 | 已实现 | [`character_entity_service.py`](../src/novel_character_generator/application/services/character_entity_service.py)、[`test_character_entity_api.py`](../tests/integration/test_character_entity_api.py) |
| 外观状态与冲突 | 真实 Observation 自动形成分阶段外观，并识别同一范围内的不兼容字段 | 已实现核心 | [`appearance_aggregation.py`](../src/novel_character_generator/domain/policies/appearance_aggregation.py)、[`appearance_aggregation_service.py`](../src/novel_character_generator/application/services/appearance_aggregation_service.py)、[`test_appearance_aggregation_pipeline.py`](../tests/integration/test_appearance_aggregation_pipeline.py)；源版本替换及人工确认保护见 [`test_source_version_appearance_invalidation.py`](../tests/integration/test_source_version_appearance_invalidation.py)，父子时间线继承见 [`test_timeline_inheritance.py`](../tests/integration/test_timeline_inheritance.py) |
| 渲染档案审批 | 聚合结果自动形成待审核档案，可解决冲突、编辑和批准版本 | 已实现核心 | 聚合 Worker 已接入现有 API 与 [`appearance_service.py`](../src/novel_character_generator/application/services/appearance_service.py)，真实提取链路见 [`test_appearance_aggregation_pipeline.py`](../tests/integration/test_appearance_aggregation_pipeline.py) |
| 目标时点外观快照 | 按 timeline/event/scene/chapter 解析有效外观并生成 `snapshot_hash` | 已实现核心 | [`AppearanceService.snapshot`](../src/novel_character_generator/application/services/appearance_service.py)、对应集成测试 |
| 角色设计缺口与出图就绪度 | 区分小说未写、明确无、冲突与人工设计缺口，并分别判断概念图、角色设定图和一致性场景图资格 | 部分实现 | `render-readiness-v1` 已在 Mock 链路按来源完整度、身份/阶段/造型、可信简报、负向约束和身份参考图失败关闭；完整 `CharacterDesignGap` 持久化与审批闭环仍待实现。见 [`image_rendering.py`](../src/novel_character_generator/domain/policies/image_rendering.py) |
| 场景简报与 Prompt 编译 | 将角色快照、场景表演、美术镜头、负向约束和参考资产编译为 Provider 中立 `ImageRenderSpec` | 部分实现 | 已有 strict `SceneRenderBrief`、稳定 `brief_hash/spec_hash` 和六类分块；`canonical-zh-character-v1` 可插拔 Renderer 将字段转为自然中文并保存逐短句 provenance，golden test 防止内部字段路径泄漏。真实 approved/locked 上游和持久化简报审批仍待闭环 |
| 人工审批 | 创建、分页查询、批准/拒绝/修改/延后，并恢复等待任务 | 已实现 | [`approval_service.py`](../src/novel_character_generator/application/services/approval_service.py)、[`approvals.py`](../src/novel_character_generator/api/routes/approvals.py) |
| Structured AgentRuntime | 强类型工具、权限、预算、停止原因和轨迹持久化 | 部分实现 | [`structured_runtime.py`](../src/novel_character_generator/agents/structured_runtime.py)；默认 `agent_runtime_enabled=false`，尚未成为文本主流程必经步骤 |
| Agent 轨迹查询 | 查询 AgentRun、Turn、ToolCall 和 DecisionRecord | 已实现 | [`agent_runs.py`](../src/novel_character_generator/api/routes/agent_runs.py)、[`test_agent_execution_service.py`](../tests/integration/test_agent_execution_service.py) |
| 评测数据层 | 数据集冻结、case/result/grader 版本和唯一性 | 已实现基础 | 正式 Evaluation Repository 已有；当前默认是 31-case dataset v1.1 / rubric v3.1，并有 6 个 source-backed 真实审计切片。评分器覆盖 required/allowed/forbidden、mention、deferred、temporal、重复与 asserted/deferred 排他；首轮 74 份候选已离线重评。旧 25-case v0 只保留用于历史复现；当前规模仍不等同于 80–120 case 发布黄金集或公开 Eval Runner。见 [`extraction_evaluation_service.py`](../src/novel_character_generator/application/services/extraction_evaluation_service.py)、[`visual_extraction_seed_v1.json`](../tests/evaluation/visual_extraction_seed_v1.json)和[`test_evaluation_repository.py`](../tests/integration/test_evaluation_repository.py) |
| 小说分解质量报告 | 用确定性指标评价 grounding、人物绑定、阶段覆盖、污染、冲突、检索覆盖和成本；复杂问题条件调用 Review Agent | 仅设计 | 当前本地检查器只能评价格式、局部 grounding 和 Provider 用量；正式 `DecompositionQualityReport`、API 和 Review 分支尚未接入 Pipeline |
| 指标端点 | API 请求计数、延迟和受保护的 `/metrics` | 已实现基础 | [`metrics.py`](../src/novel_character_generator/api/metrics.py) |
| R1–R3 Run Inspector | 按 Run 查看 R1 候选/定位、R2 人物解析/收敛、R3 阶段/作用域的进度、运行指标、调用用量、异常原因和结构化产出 | 已实现基础 | [`run_inspector_service.py`](../src/novel_character_generator/application/services/run_inspector_service.py)、[`runs.py`](../src/novel_character_generator/api/routes/runs.py)、[`test_text_analysis_run.py`](../tests/integration/test_text_analysis_run.py)、[`test_phase_resolution_pipeline.py`](../tests/integration/test_phase_resolution_pipeline.py)；当前指标是诊断信号，不等同于黄金集质量分数 |
| 轻量可视化工作台 | 上传 TXT、恢复历史项目和失败任务的部分角色、查看 R1–R3 阶段产出、回填旧项目精细索引，并按人生阶段展示视觉事实、字段缺口、精提取证据和审核建议 | 已实现基础 | [`web/index.html`](../src/novel_character_generator/web/index.html)、[`web/app.js`](../src/novel_character_generator/web/app.js)、[`ui.py`](../src/novel_character_generator/api/routes/ui.py)；图像区随 capability 关闭 |
| 完整 OpenTelemetry 链路 | API→Worker→Provider→Artifact Trace 与 Span Link | 仅设计 | 配置字段存在，但尚未看到完整 instrumentation 实现 |
| 关键结构化业务日志 | 快照、预算、Provider、漂移门禁、审批和锁定事件 | 仅设计 | 事件规范见[日志设计](13-observability-logging-and-cost.md)，当前只有少量 Worker 异常日志 |
| `log-check` 检查器 | 检查断链、重复收费、context hash 和错误锁定 | 仅设计 | 尚无命令、规则执行器或测试夹具 |
| 可插拔图像生成链路 | 根据冻结渲染规格，通过 Mock 或市场 Provider 生成并保存候选图 | 部分实现、默认关闭 | Provider/PromptRenderer 均经注册表构造；DashScope `qwen-image-plus` 已完成一张 1328×1328 真实候选图，Prompt/版本/provenance sidecar 已保存。可信审批、漂移 Gate、费用回填和 baseline 锁定尚未实现，默认仍关闭 |
| Visual Director / Critic | 规划画面并检查身份、阶段和时间线漂移 | 仅设计 | 设计见[图像生成与视觉防漂移](06-image-generation-and-drift-control.md) |
| 阶段基准图锁定 | 从候选图中选择每个阶段基准图 | 仅设计 | 数据模型已预留，尚无生成和选择 API |
| 完整管理后台 | 可视化审批、冲突解决、评测、配置和运维入口 | 仅设计 | 当前只有轻量工作台和 REST API/OpenAPI，不等同于管理后台 |
| LoRA 与 3D | 角色 LoRA、多视图、3D、骨骼和动画 | 二期 | 见[路线图](14-roadmap.md) |

## 当前最重要的边界

### 已经形成闭环

- TXT 上传 → 不可变源版本 → 分块 → 角色提取 → 查询角色与证据。
- 综合 `appearance`/旧别名 → 原子视觉字段 → 人生阶段标记 → 精确证据区间 → 视觉优先页面展示。
- Observation → 确定性聚合 → AppearanceState/Conflict → 待审核 RenderProfile。
- Run/Step 创建 → Worker 领取 → checkpoint → 完成或重试 → SSE 查询。
- Run → R1/R2/R3 阶段摘要 → 结构化中间/最终产出下钻；不在摘要中复制小说原文或 Prompt。
- 人物合并/拆分 → revision 与幂等保护 → 审计记录。
- 真实提取结果 → 冲突检测/解决 → 档案编辑与批准 → 目标时点快照。
- 角色/字段组 → 版本化 QueryPlan → 混合召回与命中审计 → 结构化精提取 → 精确事实/审核建议分流 → 外观重聚合。
- 期望字段 → Provider 中立 `ImageRenderSpec` → 版本化自然语言 Renderer/provenance → DashScope 单图 submit/query/download → 本地 PNG 与 Prompt sidecar；同一规格 hash 稳定，明确拒绝与提交未知分流。

### 还没有形成闭环

- 角色/字段级精细差异重算已延期；当前源版本替换继续采用安全的整角色保守重建。更大规模多层分支黄金集仍待完善。
- 文本 Provider 已用 output/deadline/retry 控制最坏调用规模，但按真实币种执行的调用前金额门禁仍需版本化价格表或 Provider 计费报价，当前不能把 Token 上限描述成完整费用门禁。
- approved/locked 快照经正式 Image Run 提交真实收费 Provider，并把费用、Prompt Artifact 和图片记录统一落库；当前真实图来自有界 expected-field smoke，不是已批准档案。
- 小说事实缺口 → 人工角色设计补全与持久化审批 → 更高两档出图就绪度的完整可审核桥梁；当前只有契约、编译器和失败关闭门禁。
- 候选图执行漂移审计、门禁、有界重生成和人工锁定。
- 关键业务事件统一结构化输出，再由 `log-check` 对账。
- 评测数据层目前只保留数据仓储和后续 Runner/Grader 接口；完整 EvalRun、报告和发布门禁将在功能契约稳定后实现。

## 建议的下一阶段实现顺序

1. 用现有 25-case 种子集和 locator/Adapter 边界测试验证已切换的 v3；运行真实 v3 诊断时，把每个新失败抽象为跨作品通用 case 后回填，逐步扩充到 30–40 个。
2. 不再进行付费 v2/v3 Shadow；成本对照只读取已保存的 v2 响应、usage 和 fixture。用多部不同类型小说补齐实体、阶段、留白和关键污染 case，发布前再冻结 80–120 case。
3. 为 Mock 候选补确定性基础检查和最小 gate，再接 Multimodal Critic。
4. 把已实现的 DashScope Provider 接到 approved/locked Profile 正式 Run，并补费用回填与 Prompt Artifact 持久化。
5. 实现候选漂移审计、人工选择、阶段 baseline 锁定和依赖失效传播；功能契约稳定后再实现正式 Eval Runner 和发布门禁。

### 已延期事项

- 角色/字段级精细差异重算：不影响当前 TXT 上传、角色提取、外观聚合和人工审批闭环；在小说源版本替换时暂时以更多重算换取一致性与实现安全性。
- 这里的延期项与“抽取 Schema 升级时失效旧自动事实”不同：后者已经实现，但目前仍以一次 Run 的保守替换和整角色聚合为边界，不会只重算真正变化的单个字段。

逐项 API、代码、数据、日志和测试落点见[功能—代码—测试追踪矩阵](19-feature-traceability-matrix.md)。

## 状态维护规则

- 新功能只有同时存在可运行入口和自动测试时，才从“仅设计”升级为“已实现”。
- 只有模型或表结构、没有调用链时，标记为“部分实现”，不能写成“支持”。
- 默认关闭的功能必须注明开关和降级行为。
- 每次变更本表时，同时核对 `/api/v1/capabilities`，避免文档与运行时声明不一致。

---

[← 项目总览](00-start-here.md) · [文档索引](README.md) · [代码导航 →](00-code-navigation.md)
