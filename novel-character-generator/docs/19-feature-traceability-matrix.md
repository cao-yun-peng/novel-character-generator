# 功能—代码—测试追踪矩阵

> [← 上一篇](18-image-generation-implementation-contract.md) · [文档索引](README.md) · [下一篇 →](20-api-cookbook-and-error-catalog.md)
>
> 文档版本：2.9 · 状态快照日期：2026-08-24 · 项目版本：0.1.0

## 1. 用法

本矩阵回答“一个功能落在哪里、用什么验证、现在到底完成没有”。状态定义与[当前实现状态](00-current-status.md)一致：只有存在可运行入口和自动测试才算已实现；只有表或模型不算支持。

每次功能状态变化必须在同一个提交中核对：

1. API/OpenAPI 或 Worker 入口；
2. Application Service 与领域规则；
3. ORM、Migration 和 Artifact；
4. 关键业务日志；
5. 自动测试；
6. `/api/v1/capabilities`；
7. 本矩阵和当前实现状态。

## 2. 当前能力矩阵

| 功能 | 入口 | 核心实现/数据 | Worker Step | 自动验证 | 关键日志状态 | 状态 |
|---|---|---|---|---|---|---|
| 健康、认证、能力声明 | `/health/*`、`/capabilities` | `api/app.py`、`api/auth.py`、`settings.py` | — | `test_health.py`、`test_settings.py` | 仅基础请求 Metrics | 已实现 |
| TXT 上传与源版本 | `POST /novels`、`POST /novels/{id}/versions` | `IngestionService`、Document ORM、LocalArtifactStore、依赖失效传播 | 创建后续 Run | `test_document_versions.py`、`test_source_version_appearance_invalidation.py` | `generation.dependency.invalidated` 已插桩 | 已实现 |
| 规范化、章节和分块 | 创建文本 Run | `text_processing.py`、文档/Chunk Repository | `normalize_and_chunk` | `test_text_processing.py`、`test_text_analysis_run.py` | Step 完整事件待实现 | 已实现 |
| 角色、Mention 与外观事实提取 | 文本 Run、角色查询 API | Extraction Provider/Handler/Repository | `extract_characters` | `test_extraction_slice.py`、Provider 单测 | Provider/证据事件待实现 | 已实现基础 |
| Run 查询、SSE、取消、重试 | `/runs/{id}` 及子路径 | `RunService`、RunEvent Repository | 领取与状态推进 | `test_run_events_and_external_operations.py` | 当前只有少量异常日志 | 已实现 |
| Worker 租约、fencing、恢复 | Worker CLI | `task_claim.py`、Run/Step ORM | 所有 Step | `test_task_recovery.py` | claim/start/complete/fail 待统一 | 已实现 |
| 外部操作账本 | `/runs/{id}/external-operations` | `ExternalOperationRepository`、ORM | 尚无真实外部图像 Step | Repository/恢复测试 | submit/unknown 事件待实现 | 部分实现 |
| 时间线、事件、场景 | `/novels/{id}/timelines|events|scenes` | `StoryService`、Story ORM | Extraction 产生基础记录 | `test_story_temporal_api.py` | 修正审计事件待统一 | 已实现基础 |
| 人物合并/拆分 | `/characters/merge|split` | `CharacterEntityService`、操作审计表 | — | `test_character_entity_api.py` | 依赖失效事件待实现 | 已实现 |
| 外观状态、冲突、档案 | 角色 appearance/profile/conflict API | `AppearanceAggregationService`、`AppearanceService`、Character ORM；`conflict_kind` 区分人工保护 | `aggregate_appearance` | `test_appearance_aggregation_pipeline.py`、`test_source_version_appearance_invalidation.py` | started/derived/conflict/drafted/unchanged 已插桩 | 已实现核心 |
| 目标时点 Snapshot | `GET /characters/{id}/snapshot` | `AppearanceService.snapshot`，按父链分支点继承 | — | `test_character_appearance_api.py`、`test_timeline_inheritance.py` | `generation.snapshot.resolved` 待实现 | 已实现核心 |
| 人工审批 | `/approvals` | `ApprovalService`、Approval ORM | 恢复等待 Step | `test_approval_and_agent_api.py` | requested/decided/resumed 待统一 | 已实现 |
| 通用 AgentRuntime 与轨迹 | `/agent-runs` | `structured_runtime.py`、`AgentExecutionService`、Agent ORM | 尚未成为文本主流程必经 | `test_structured_agent_runtime.py`、`test_agent_execution_service.py` | 轨迹有业务表，事件待补 | 部分实现、默认关闭 |
| 评测数据层 | 暂无公开执行 API | Evaluation Repository/ORM | 尚无 Eval Runner | `test_evaluation_repository.py` | 评测事件待实现 | 已实现基础 |
| Metrics | `/metrics` | `api/metrics.py` | — | Health/Metrics 集成测试 | 请求计数与延迟 | 已实现基础 |
| 轻量可视化工作台 | `/ui`、`/ui/assets/*` | `api/routes/ui.py`、`web/index.html/css/js` | 通过公开 Run API 间接驱动 | `test_ui_shell_and_static_assets_are_served_without_api_auth` | 浏览器不产生业务真值 | 已实现基础 |
| OpenTelemetry 全链路 | 配置字段 | 尚无完整 instrumentation | — | 尚无 | 尚无 | 仅设计 |
| 结构化业务事件与 `log-check` | 目标 CLI | 设计见日志文档 | 覆盖所有关键 Step | 尚无夹具/检查器测试 | 事件规范已设计 | 仅设计 |
| 外观自动聚合闭环 | 现有查询/审批 API | `appearance_aggregation.py`、`appearance_aggregation_service.py`、聚合指纹与 stale 迁移 | `aggregate_appearance` | 策略单测、Pipeline/API、源版本失效、人工保护与时间线继承集成测试 | 核心聚合与依赖失效事件已插桩 | 已实现核心；精细差异重算已延期，当前保守重建 |
| GenerationContext | 尚无公开入口 | 目标 Builder/ORM | `freeze_generation_context` | 尚无 | frozen/rejected 未插桩 | 仅设计 |
| 图像 Provider 与候选图 | 目标 `/image-runs` | 目标见[图像契约](18-image-generation-implementation-contract.md) | submit/poll/persist | 尚无 | Provider/Artifact 事件未插桩 | 仅设计 |
| Drift Audit 与门禁 | 目标图像 API | DriftAudit、Gate、Critic 目标模型 | audit/gate/regenerate | 尚无 | audit/gate/regen 未插桩 | 仅设计 |
| 阶段 baseline 与 ImageSet | 目标 image-set API | Image ORM 预留 | 等待人工选择 | 尚无 | baseline/imageset 未插桩 | 仅设计 |

## 3. 下一实现批次的纵向切片

为了避免“表建了、API 有了、用户仍用不了”，后续按纵向闭环交付：

| 批次 | 最小可验收结果 | 必须同时完成 |
|---|---|---|
| A：外观聚合 | 真实提取结果可形成待审核 Profile | Step、Policy、Service、迁移、API 复用、冲突/幂等/恢复测试、聚合日志 |
| B：冻结上下文 | 已批准 Profile 可形成稳定 context hash | Builder、持久化、失效传播、hash 测试、frozen/rejected 日志 |
| C：Mock 图像链路 | 不收费的 Mock Provider 跑通候选→审计→gate | Image Run API、Step 图、ExternalOperation、Artifact、固定审计器、恢复测试 |
| D：真实 Provider | 单一 WorkflowProfile 安全生成候选图 | 契约测试、submit unknown、下载校验、费用门禁、Provider 日志 |
| E：人工锁定 | 用户可选择阶段 baseline，hard fail 无法越权锁定 | Approval、ImageSet、ETag/revision、失效传播、log-check 规则 |
| F：发布门禁 | 固定 EvalDataset 自动给出可追溯报告 | Eval Runner、grader 版本、阈值、CI/Release 输出 |

## 4. 状态升级规则

- “仅设计 → 部分实现”：至少存在可运行的一个下游入口和对应测试，但用户闭环仍缺关键步骤；
- “部分实现 → 已实现”：API/Worker、数据、恢复、安全、日志与验收路径都完成；
- capability 只能在部署实例真的具备闭环时开启；
- 默认关闭的功能必须保留“部分实现、默认关闭”描述；
- 计划接口不得注册返回空列表或假成功来制造完成感；
- 删除或重命名入口时同步修正代码导航、API 文档、测试链接和本矩阵。

---

[← 上一篇](18-image-generation-implementation-contract.md) · [文档索引](README.md) · [下一篇 →](20-api-cookbook-and-error-catalog.md)
