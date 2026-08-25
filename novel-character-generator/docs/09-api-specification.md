# API 规范

> [← 上一篇](08-task-recovery.md) · [文档索引](README.md) · [下一篇 →](10-provider-and-workflow-versioning.md)
>
> 文档版本：3.0 · 源章节：12. API 设计 · 修订日期：2026-08-24
>
> 当前接口以 FastAPI OpenAPI 和 [`GET /api/v1/capabilities`](../src/novel_character_generator/api/routes/capabilities.py) 为运行时真值。本页明确区分“已注册接口”和“目标接口”，不能仅因端点出现在设计中就认为已经可调用。

## 12. API 设计

### 12.1 统一规则

- 所有创建长任务的端点返回 `202 Accepted`；
- 支持 `Idempotency-Key`；
- 错误响应包含稳定 `code`、可读 `message` 和 `request_id`；
- 已实现分页的列表使用 cursor；Observation 列表目前是明确例外；
- 更新 RenderProfile 使用 `If-Match` 或 revision，防止覆盖他人修改；
- 管理类端点必须认证，不能裸露 Prompt/Provider 配置。

### 12.2 当前已注册端点

| 方法与路径 | 用途 | 实现状态 |
|---|---|---|
| `POST /api/v1/novels` | 上传 TXT 小说并创建首个不可变源版本 | 已实现 |
| `GET /api/v1/novels/{novel_id}` | 查询小说、源哈希和分块数量 | 已实现 |
| `POST /api/v1/novels/{novel_id}/versions` | 上传新源文档版本，保留历史版本 | 已实现 |
| `POST /api/v1/novels/{novel_id}/runs` | 创建文本分析任务 | 已实现，返回 `202` |
| `POST /api/v1/novels/{novel_id}/retrieval-index-runs` | 为当前源版本幂等创建细粒度检索索引任务，支持旧项目回填 | 已实现，返回 `202` |
| `GET /api/v1/runs/{run_id}` | 查询 Run 与 Step 状态 | 已实现 |
| `GET /api/v1/runs/{run_id}/events` | 按 `after` 序号读取或持续跟随 SSE | 已实现 |
| `POST /api/v1/runs/{run_id}/cancel` | 请求取消 | 已实现，返回 `202` |
| `POST /api/v1/runs/{run_id}/retry` | 重试允许重试的失败步骤 | 已实现，返回 `202` |
| `GET /api/v1/runs/{run_id}/agent-runs` | 查询 Agent 子任务与预算摘要 | 已实现 |
| `GET /api/v1/runs/{run_id}/external-operations` | 查询远程操作账本 | 已实现查询；自动对账未实现 |
| `GET /api/v1/agent-runs/{agent_run_id}` | 查询 Agent 轨迹、工具调用和决策 | 已实现 |
| `GET /api/v1/approvals` | 分页查询审批项 | 已实现 |
| `POST /api/v1/approvals/{approval_id}/resolve` | 批准、拒绝、修改或延后 | 已实现 |
| `GET /api/v1/novels/{novel_id}/characters` | 查询人物 | 已实现基础 |
| `GET /api/v1/characters/{character_id}/mentions` | 查询人物原文提及区间 | 已实现 |
| `GET /api/v1/characters/{character_id}/observations` | 查询规范字段、人生阶段、章节与原文证据 | 已实现基础 |
| `GET /api/v1/characters/{character_id}/expressions` | 查询外显神情观察 | 已实现基础 |
| `GET /api/v1/characters/{character_id}/appearance-states` | 查询真实 Observation 自动聚合的阶段外观状态 | 已实现核心 |
| `GET /api/v1/characters/{character_id}/conflicts` | 查询档案冲突 | 已实现 |
| `POST /api/v1/conflicts/{conflict_id}/resolve` | 解决冲突 | 已实现 |
| `GET /api/v1/characters/{character_id}/snapshot` | 按 timeline/event/scene/chapter 解析快照 | 已实现核心 |
| `GET /api/v1/characters/{character_id}/render-profile` | 获取档案并返回 `ETag` | 已实现 |
| `PUT /api/v1/characters/{character_id}/render-profile` | 使用 `If-Match` 更新档案 | 已实现 |
| `POST /api/v1/characters/{character_id}/approve` | 审批档案版本 | 已实现 |
| `POST /api/v1/characters/merge` | 管理员合并人物 | 已实现 |
| `POST /api/v1/characters/{character_id}/split` | 管理员拆分人物 | 已实现 |
| `GET /api/v1/novels/{novel_id}/timelines` | 查询时间线 | 已实现基础 |
| `GET /api/v1/novels/{novel_id}/events` | 查询故事事件 | 已实现基础 |
| `GET /api/v1/novels/{novel_id}/scenes` | 查询场景 | 已实现基础 |
| `PUT /api/v1/scenes/{scene_id}/temporal-binding` | 修正场景时间与现实层级 | 已实现 |
| `GET /api/v1/capabilities` | 查询部署实例实际能力 | 已实现 |
| `GET /health/live`、`GET /health/ready` | 存活和就绪检查 | 已实现 |
| `GET /metrics` | Prometheus 指标，受管理员权限保护且不进入 OpenAPI | 已实现基础 |

具体请求、响应、认证、SSE 和错误码见 [API 调用手册与错误目录](20-api-cookbook-and-error-catalog.md)。功能是否形成用户闭环仍以[当前实现状态](00-current-status.md)为准。

`GET /` 会重定向到轻量工作台 `GET /ui`，静态资源位于 `/ui/assets/*`。这些页面路由不属于业务 API，也不进入 OpenAPI；工作台内部仍按本节公开接口和权限规则调用后端。

`GET /api/v1/characters/{character_id}/observations` 当前返回 `chapter_ordinal`、`temporal_scope`、`life_phase_key`、`life_phase_label`、`is_visual` 和 `visual_category`。API 会把旧字段别名投影为规范路径；页面据此先展示视觉事实，按人生阶段分组，并显示章节、grounding、置信度和原文证据。该列表目前未分页，调用方不能假设通用 cursor 规则已覆盖此端点。

当 `aggregate_appearance` 尚未完成时，阶段数和冲突数为零只表示“尚未评估”，不能解释为“已确认无冲突”；工作台会明确区分这两种状态。

小说详情同时返回 `retrieval_index_build_id`、`retrieval_index_status` 和 `retrieval_passage_count`。回填索引直接从不可变源文件重新生成约 1K/100 的 passage、FTS 条目及向量，不创建新的源版本，也不修改已有 Character 或 Observation。相同源版本和索引版本重复请求返回同一 Build/Run；Embedding 未配置时工作台会阻止创建，避免得到不能执行视觉精提取的半成品索引。

### 12.3 检索增强视觉精提取接口

以下接口已注册；`visual_enrichment` capability 只在部署配置了 Embedding Provider 时声明为 `true`：

```text
GET  /api/v1/characters/{character_id}/visual-field-gaps
POST /api/v1/characters/{character_id}/visual-enrichment-runs
GET  /api/v1/characters/{character_id}/visual-enrichment-runs
GET  /api/v1/visual-enrichment-runs/{run_id}/evidence
POST /api/v1/feature-suggestions/{suggestion_id}/resolve
```

字段缺口接口返回当前源版本和可选人生阶段下七个字段组的覆盖状态、已观察字段路径、推荐补齐组及索引状态。当前 v1 是字段组级规划：组内存在至少一个有效、可定位的 asserted Observation 即视为该组已覆盖，不代表组内所有原子字段都完整。

创建请求须使用 `Idempotency-Key`，并携带可选人生阶段和调用预算。调用方可以显式传入目标 `field_groups`；也可以传空列表并保持 `auto_plan=true`，由服务端使用同一缺口策略固化本次目标组。没有可补缺口时返回 `visual_field_gaps_empty`。索引未就绪必须返回 `retrieval_index_not_ready`，不得隐式退化为全文模型调用。完整契约见[检索增强的角色视觉精提取实现设计](21-retrieval-augmented-visual-enrichment.md)。

`field_groups` 当前支持 `hair`、`face`、`body`、`clothing`、`accessories`、`marks_injuries` 和 `disguise_cleanliness`。Suggestion 的接受/拒绝需要管理员 Key 和 `X-Actor-ID`；接受只表示批准该建议，不会把推断伪装成原文 Observation。

图像生成的目标接口如下。当前 `/api/v1/capabilities` 返回 `image_generation=false`，调用这些路径会得到 `404`，实现前不得由客户端依赖：

```text
POST   /api/v1/characters/{character_id}/image-runs
GET    /api/v1/characters/{character_id}/images
GET    /api/v1/characters/{character_id}/image-set
PUT    /api/v1/characters/{character_id}/image-set/stages
POST   /api/v1/stage-images/{stage_image_id}/select-baseline
PUT    /api/v1/characters/{character_id}/image-set/default-representative
```

请求状态、Step 拆分、事务和幂等契约见[图像生成实现契约](18-image-generation-implementation-contract.md)。

### 12.4 二期端点

二期增加 `/prompts`、`/agents`、`/tools`、`/prototypes`、`/loras`、`/models3d`、批量生成、关系图谱与管理审计端点。未启用的二期模块不在一期注册返回空列表的假接口；一期 `/capabilities` 已明确告知当前启用能力，二期只扩展其返回内容。

---

[← 上一篇](08-task-recovery.md) · [文档索引](README.md) · [下一篇 →](10-provider-and-workflow-versioning.md)
