# 当前实现状态：哪些能用，哪些还只是设计

> [← 项目总览](00-start-here.md) · [文档索引](README.md) · [代码导航 →](00-code-navigation.md)
>
> 文档版本：2.9 · 状态快照日期：2026-08-24 · 项目版本：0.1.0

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
| 文本分析 Run | 一次请求顺序执行分块和角色提取 | 已实现 | [`novels.py`](../src/novel_character_generator/api/routes/novels.py)、[`test_text_analysis_run.py`](../tests/integration/test_text_analysis_run.py) |
| 角色与视觉事实提取 | 提取角色、mention、外观观察及原文证据 | 已实现基础 | [`extraction.py`](../src/novel_character_generator/workers/handlers/extraction.py)、[`openai_compatible.py`](../src/novel_character_generator/infrastructure/llm/openai_compatible.py)、[`test_extraction_slice.py`](../tests/integration/test_extraction_slice.py) |
| Mock/远程 LLM Provider | 本地稳定测试或调用 OpenAI-compatible 结构化输出 | 已实现 | [`mock.py`](../src/novel_character_generator/infrastructure/llm/mock.py)、[`workers/main.py`](../src/novel_character_generator/workers/main.py) |
| Run 查询、SSE、取消和重试 | 查看进度，断线后续传事件，取消或重试任务 | 已实现 | [`runs.py`](../src/novel_character_generator/api/routes/runs.py)、[`run_service.py`](../src/novel_character_generator/application/services/run_service.py) |
| Worker 租约与恢复 | claim、checkpoint、retry、fencing，避免旧 Worker 写入 | 已实现 | [`task_claim.py`](../src/novel_character_generator/workers/task_claim.py)、[`test_task_recovery.py`](../tests/integration/test_task_recovery.py) |
| 外部操作账本 | 保存幂等键、提交状态和租约代次 | 部分实现 | [`external_operations.py`](../src/novel_character_generator/infrastructure/db/repositories/external_operations.py) 已有仓储和测试，但 capability 中 reconciliation 仍为 `false` |
| 时间线、事件和场景查询 | 查看故事时间结构与场景绑定 | 已实现基础 | [`story.py`](../src/novel_character_generator/api/routes/story.py)、[`story_service.py`](../src/novel_character_generator/application/services/story_service.py) |
| 场景时间绑定修正 | 人工修改 timeline/event/reality status，使用 revision 防冲突 | 已实现 | [`test_story_temporal_api.py`](../tests/integration/test_story_temporal_api.py) |
| 角色合并与拆分 | 修正重复人物或错误共指，并保留审计记录 | 已实现 | [`character_entity_service.py`](../src/novel_character_generator/application/services/character_entity_service.py)、[`test_character_entity_api.py`](../tests/integration/test_character_entity_api.py) |
| 外观状态与冲突 | 保存分阶段外观，识别同优先级、重叠时间范围的字段冲突 | 部分实现 | [`appearance_service.py`](../src/novel_character_generator/application/services/appearance_service.py)；状态自动聚合入口尚未闭合，目标见[聚合实现契约](17-appearance-aggregation-contract.md) |
| 渲染档案审批 | 更新档案、解决冲突、批准档案版本 | 部分实现 | API 与 Service 已实现，但依赖预先存在的 AppearanceState；见 [`test_character_appearance_api.py`](../tests/integration/test_character_appearance_api.py) |
| 目标时点外观快照 | 按 timeline/event/scene/chapter 解析有效外观并生成 `snapshot_hash` | 已实现核心 | [`AppearanceService.snapshot`](../src/novel_character_generator/application/services/appearance_service.py)、对应集成测试 |
| 人工审批 | 创建、分页查询、批准/拒绝/修改/延后，并恢复等待任务 | 已实现 | [`approval_service.py`](../src/novel_character_generator/application/services/approval_service.py)、[`approvals.py`](../src/novel_character_generator/api/routes/approvals.py) |
| Structured AgentRuntime | 强类型工具、权限、预算、停止原因和轨迹持久化 | 部分实现 | [`structured_runtime.py`](../src/novel_character_generator/agents/structured_runtime.py)；默认 `agent_runtime_enabled=false`，尚未成为文本主流程必经步骤 |
| Agent 轨迹查询 | 查询 AgentRun、Turn、ToolCall 和 DecisionRecord | 已实现 | [`agent_runs.py`](../src/novel_character_generator/api/routes/agent_runs.py)、[`test_agent_execution_service.py`](../tests/integration/test_agent_execution_service.py) |
| 评测数据层 | 数据集冻结、case/result/grader 版本和唯一性 | 已实现基础 | [`evaluation.py`](../src/novel_character_generator/infrastructure/db/repositories/evaluation.py)、[`test_evaluation_repository.py`](../tests/integration/test_evaluation_repository.py) |
| 指标端点 | API 请求计数、延迟和受保护的 `/metrics` | 已实现基础 | [`metrics.py`](../src/novel_character_generator/api/metrics.py) |
| 轻量可视化工作台 | 上传 TXT、创建分析任务、查看进度、角色证据和 2D 生成入口 | 已实现基础 | [`web/index.html`](../src/novel_character_generator/web/index.html)、[`web/app.js`](../src/novel_character_generator/web/app.js)、[`ui.py`](../src/novel_character_generator/api/routes/ui.py)；图像区随 capability 关闭 |
| 完整 OpenTelemetry 链路 | API→Worker→Provider→Artifact Trace 与 Span Link | 仅设计 | 配置字段存在，但尚未看到完整 instrumentation 实现 |
| 关键结构化业务日志 | 快照、预算、Provider、漂移门禁、审批和锁定事件 | 仅设计 | 事件规范见[日志设计](13-observability-logging-and-cost.md)，当前只有少量 Worker 异常日志 |
| `log-check` 检查器 | 检查断链、重复收费、context hash 和错误锁定 | 仅设计 | 尚无命令、规则执行器或测试夹具 |
| 图像生成 Provider | 根据快照生成角色候选图 | 仅设计 | 图像领域模型和 ORM 已预留，但 `image_generation=false`，`infrastructure/image` 尚无实现；实现边界见[图像生成契约](18-image-generation-implementation-contract.md) |
| Visual Director / Critic | 规划画面并检查身份、阶段和时间线漂移 | 仅设计 | 设计见[图像生成与视觉防漂移](06-image-generation-and-drift-control.md) |
| 阶段基准图锁定 | 从候选图中选择每个阶段基准图 | 仅设计 | 数据模型已预留，尚无生成和选择 API |
| 完整管理后台 | 可视化审批、冲突解决、评测、配置和运维入口 | 仅设计 | 当前只有轻量工作台和 REST API/OpenAPI，不等同于管理后台 |
| LoRA 与 3D | 角色 LoRA、多视图、3D、骨骼和动画 | 二期 | 见[路线图](14-roadmap.md) |

## 当前最重要的边界

### 已经形成闭环

- TXT 上传 → 不可变源版本 → 分块 → 角色提取 → 查询角色与证据。
- Run/Step 创建 → Worker 领取 → checkpoint → 完成或重试 → SSE 查询。
- 人物合并/拆分 → revision 与幂等保护 → 审计记录。
- 预置外观状态 → 冲突检测/解决 → 档案批准 → 目标时点快照。

### 还没有形成闭环

- Observation 自动聚合成 AppearanceState，再形成待审核 RenderProfile。
- 已批准快照提交图像 Provider，保存候选图与费用。
- 候选图执行漂移审计、门禁、有界重生成和人工锁定。
- 关键业务事件统一结构化输出，再由 `log-check` 对账。
- 评测数据层自动执行完整 EvalRun、报告和发布门禁。

## 建议的下一阶段实现顺序

1. 完成 Observation → AppearanceState → RenderProfile 的确定性聚合和人工审核入口。
2. 实现 `GenerationContextBuilder`，冻结生成与审计共用的 context hash。
3. 接入一套固定 Image Provider/WorkflowProfile，先跑通单阶段候选图。
4. 实现确定性基础检查和最小 Multimodal Critic，再加入 hard/soft gate。
5. 在上述关键状态边界打结构化日志，实现最小 `log-check`。
6. 用评测数据层建立从文本到阶段图的发布门禁。

逐项 API、代码、数据、日志和测试落点见[功能—代码—测试追踪矩阵](19-feature-traceability-matrix.md)。

## 状态维护规则

- 新功能只有同时存在可运行入口和自动测试时，才从“仅设计”升级为“已实现”。
- 只有模型或表结构、没有调用链时，标记为“部分实现”，不能写成“支持”。
- 默认关闭的功能必须注明开关和降级行为。
- 每次变更本表时，同时核对 `/api/v1/capabilities`，避免文档与运行时声明不一致。

---

[← 项目总览](00-start-here.md) · [文档索引](README.md) · [代码导航 →](00-code-navigation.md)
