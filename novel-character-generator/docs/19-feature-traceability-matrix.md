# 功能—代码—测试追踪矩阵

> [← 上一篇](18-image-generation-implementation-contract.md) · [文档索引](README.md) · [下一篇 →](20-api-cookbook-and-error-catalog.md)
>
> 文档版本：3.2 · 状态快照日期：2026-08-26 · 项目版本：0.1.0

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
| 角色、Mention 与外观事实提取 | 文本 Run、角色查询 API | v3 Candidate Schema、服务端 evidence locator、最小 GroundedVisual DTO、Provider/Repository；Chat/Responses、reasoning/output/deadline/item 门禁 | `extract_characters`，cursor schema v3 按 Chunk checkpoint；Provider 耗尽有界重试后 deferred，等待显式人工重试 | `test_extraction_slice.py`、`test_openai_compatible_extraction.py`、`test_evidence_locator.py`、`test_visual_candidate_adapter.py`、`test_task_recovery.py` | `provider.extraction.completed/deferred/failed`，含 usage、request ID、finish reason、延迟和候选结果 hash | R1 核心已实现；旧八类联合写入已删除；真实 v3 质量/成本门禁待跑 |
| 细粒度检索库与混合召回 | 小说详情返回当前 build/status；Worker 内可执行混合召回 | 检索表、passage、FTS5、中文词典、EmbeddingPort、Qdrant Local、RRF、实体加分与邻居扩展 | `build_retrieval_index` 已接线并按批 checkpoint | `test_retrieval.py`、`test_openai_compatible_embedding.py`、`test_qdrant_local_vector_store.py`、`test_retrieval_indexing.py` 覆盖 429、维度拒绝、过滤、恢复、混合召回和邻居 | `retrieval.index.started/lexical_ready/ready/failed` | 已实现基础（黄金集门禁待做） |
| 检索增强视觉精提取 | 角色页、field-gaps API、visual-enrichment Run/API、evidence API、Suggestion resolve API | 字段组缺口策略、版本化 QueryPlan、命中审计、邻居扩展、结构化 Provider、唯一 chunk 回映、Observation/Suggestion 分流 | `plan_visual_retrieval → retrieve_visual_evidence → extract_visual_evidence → persist_visual_evidence → aggregate_appearance` | `test_visual_query_plan.py`、`test_visual_enrichment_pipeline.py`、UI 浏览器 smoke；黄金集 Runner/门禁按功能稳定度暂缓 | `visual_enrichment.planned/retrieved/packet_built/extracted/evidence_persisted/suggested/completed` | 已实现基础 |
| 原子视觉字段、人生阶段与证据修复 | Observation API、工作台角色详情 | `visual_fields.py`、`grounding.py`、`ObservationDraft`、Extraction Repository；阶段保存在 `temporal_scope` | `extract_characters` | `test_visual_fields.py`、`test_extraction_slice.py`、Observation API 测试 | 复用提取/聚合日志；专用规范化事件待实现 | 已实现基础 |
| R3 人物阶段与观察时间作用域 | temporal-review、life-phases、resolve API | `phase_resolution_service.py`、PhaseResolutionRepository、StoryService；`temporal_signals`、`character_life_phases`、`observation_scope_bindings` | `resolve_character_phases` | `test_phase_resolution_service.py`、`test_phase_resolution_pipeline.py`、迁移测试 | 输入哈希、resolver version、DecisionRecord | 已实现基础 |
| extractor version 替换 | 新文本 Run | `<provider>:<model>:visual-observation-v3`；旧自动 Observation superseded，人工 Observation 保留 | `extract_characters` 首 chunk | `test_extraction_slice.py` | 专用 superseded 事件待实现 | 已实现 |
| 场景重分析覆盖 | 新文本 Run、Story API | `(novel_id, narrative_order)` 稳定槽位；自动结果原位更新，人工 corrected binding 保留 | `extract_characters` | `test_reanalysis_updates_automatic_scene_when_span_changes`、场景人工修正集成测试 | 复用 Step 事件 | 已实现 |
| Run 查询、SSE、取消、重试 | `/runs/{id}` 及子路径 | `RunService`、RunEvent Repository | 领取与状态推进 | `test_run_events_and_external_operations.py` | 当前只有少量异常日志 | 已实现 |
| Worker 租约、fencing、恢复 | Worker CLI | `task_claim.py`、Run/Step ORM | 所有 Step | `test_task_recovery.py` | claim/start/complete/fail 待统一 | 已实现 |
| 外部操作账本 | `/runs/{id}/external-operations` | `ExternalOperationRepository`、ORM | Mock `submit_image/poll_image/persist_image` 已使用；真实 Provider 待接 | Repository 与 `test_image_generation_pipeline.py` 恢复测试 | submit/unknown 事件待补 | 部分实现 |
| 时间线、事件、场景 | `/novels/{id}/timelines|events|scenes` | `StoryService`、Story ORM；历史数据可读 | v3 Extraction 不再生产，后续按需步骤待实现 | 路由声明测试；新的独立 producer 测试待补 | 修正审计事件待统一 | 部分实现（读取/修正保留，上游待重建） |
| 人物合并/拆分 | `/characters/merge|split` | `CharacterEntityService`、操作审计表 | — | `test_character_entity_api.py` | 依赖失效事件待实现 | 已实现 |
| 外观状态、冲突、档案 | 角色 appearance/profile/conflict API | `AppearanceAggregationService`、`AppearanceService`、Character ORM；`conflict_kind` 区分人工保护 | `aggregate_appearance` | `test_appearance_aggregation_pipeline.py`、`test_source_version_appearance_invalidation.py` | started/derived/conflict/drafted/unchanged 已插桩 | 已实现核心 |
| 目标时点 Snapshot | `GET /characters/{id}/snapshot` | `AppearanceService.snapshot`，按父链分支点继承 | — | `test_character_appearance_api.py`、`test_timeline_inheritance.py` | `generation.snapshot.resolved` 待实现 | 已实现核心 |
| 人工审批 | `/approvals` | `ApprovalService`、Approval ORM | 恢复等待 Step | `test_approval_and_agent_api.py` | requested/decided/resumed 待统一 | 已实现 |
| 通用 AgentRuntime 与轨迹 | `/agent-runs` | `structured_runtime.py`、`AgentExecutionService`、Agent ORM | 尚未成为文本主流程必经 | `test_structured_agent_runtime.py`、`test_agent_execution_service.py` | 轨迹有业务表，事件待补 | 部分实现、默认关闭 |
| 评测数据层 | 暂无公开执行 API | Evaluation Repository/ORM；25-case 视觉抽取开发种子集与确定性评分器 | 尚无正式 Eval Runner | `test_evaluation_repository.py`、`test_extraction_evaluation_service.py` | 评测事件待实现 | 已实现基础；真实差异先抽象为跨作品通用 case 再增补，冻结黄金集待扩充 |
| Metrics | `/metrics` | `api/metrics.py` | — | Health/Metrics 集成测试 | 请求计数与延迟 | 已实现基础 |
| 轻量可视化工作台 | `/ui`、`/ui/assets/*` | `api/routes/ui.py`、`web/index.html/css/js`；历史项目、重启分析、视觉优先、人生阶段、字段缺口、精提取进度/证据/Suggestion 审核 | 通过公开 Run API 间接驱动 | UI 静态资源集成测试、Observation/visual-enrichment API 测试、桌面与移动端浏览器 smoke | 浏览器不产生业务真值 | 已实现基础 |
| OpenTelemetry 全链路 | 配置字段 | 尚无完整 instrumentation | — | 尚无 | 尚无 | 仅设计 |
| 结构化业务事件与 `log-check` | 目标 CLI | 设计见日志文档 | 覆盖所有关键 Step | 尚无夹具/检查器测试 | 事件规范已设计 | 仅设计 |
| 外观自动聚合闭环 | 现有查询/审批 API | `appearance_aggregation.py`、`appearance_aggregation_service.py`、聚合指纹与 stale 迁移 | `aggregate_appearance` | 策略单测、Pipeline/API、源版本失效、人工保护与时间线继承集成测试 | 核心聚合与依赖失效事件已插桩 | 已实现核心；精细差异重算已延期，当前保守重建 |
| GenerationContext | `POST /characters/{id}/image-runs` | `GenerationContextBuilder`、GenerationContext ORM、规范 JSON/hash | `freeze_generation_context` | `test_image_generation_pipeline.py` | `generation.context.frozen` | 已实现基础 |
| Mock 图像 Provider 与候选图 | `POST /characters/{id}/image-runs`、`GET /image-runs/{id}`、角色 Image Run 列表 | Image Provider Port、Mock Adapter、Artifact/GeneratedImage ORM | `submit_image → poll_image → persist_image` | `test_image_generation_pipeline.py` 覆盖候选落库、幂等、去重和恢复 | 复用 Run/ExternalOperation 状态；Provider 结构化事件待补 | 部分实现、默认关闭；真实 Provider 待做 |
| Drift Audit 与门禁 | 目标图像 API | DriftAudit、Gate、Critic 目标模型 | audit/gate/regenerate | 尚无 | audit/gate/regen 未插桩 | 仅设计 |
| 阶段 baseline 与 ImageSet | 目标 image-set API | Image ORM 预留 | 等待人工选择 | 尚无 | baseline/imageset 未插桩 | 仅设计 |

## 3. 下一实现批次的纵向切片

为了避免“表建了、API 有了、用户仍用不了”，后续按纵向闭环交付：

| 批次 | 最小可验收结果 | 必须同时完成 |
|---|---|---|
| A：外观聚合 | 真实提取结果可形成待审核 Profile | Step、Policy、Service、迁移、API 复用、冲突/幂等/恢复测试、聚合日志 |
| A0：检索增强视觉精提取 | 上传后混合索引就绪；选定角色可补齐有证据的视觉字段，候选可审核 | 索引迁移、中文分词/BM25、EmbeddingPort/vector index、RRF、QueryPlan/Hit 审计、Worker、精确回映、Suggestion 分流、恢复/黄金集测试 |
| B：冻结上下文（核心已完成） | 已批准 Profile 可形成稳定 context hash | Builder、持久化、hash 测试和 frozen 事件已完成；失效传播/rejected 事件待补 |
| C：Mock 图像链路（产物链已完成） | 不收费的 Mock Provider 跑通候选落库与恢复 | Image Run API、Step 图、ExternalOperation、Artifact、恢复测试已完成；固定审计器与 gate 待补 |
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
