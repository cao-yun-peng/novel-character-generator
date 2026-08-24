# API 规范

> [← 上一篇](08-task-recovery.md) · [文档索引](README.md) · [下一篇 →](10-provider-and-workflow-versioning.md)
>
> 文档版本：2.9 · 源章节：12. API 设计 · 修订日期：2026-08-24
>
> 当前接口以 FastAPI OpenAPI 和 [`GET /api/v1/capabilities`](../src/novel_character_generator/api/routes/capabilities.py) 为运行时真值。本页明确区分“已注册接口”和“目标接口”，不能仅因端点出现在设计中就认为已经可调用。

## 12. API 设计

### 12.1 统一规则

- 所有创建长任务的端点返回 `202 Accepted`；
- 支持 `Idempotency-Key`；
- 错误响应包含稳定 `code`、可读 `message` 和 `request_id`；
- 分页使用 cursor；
- 更新 RenderProfile 使用 `If-Match` 或 revision，防止覆盖他人修改；
- 管理类端点必须认证，不能裸露 Prompt/Provider 配置。

### 12.2 当前已注册端点

| 方法与路径 | 用途 | 实现状态 |
|---|---|---|
| `POST /api/v1/novels` | 上传 TXT 小说并创建首个不可变源版本 | 已实现 |
| `GET /api/v1/novels/{novel_id}` | 查询小说、源哈希和分块数量 | 已实现 |
| `POST /api/v1/novels/{novel_id}/versions` | 上传新源文档版本，保留历史版本 | 已实现 |
| `POST /api/v1/novels/{novel_id}/runs` | 创建文本分析任务 | 已实现，返回 `202` |
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
| `GET /api/v1/characters/{character_id}/observations` | 查询外观事实与证据 | 已实现基础 |
| `GET /api/v1/characters/{character_id}/expressions` | 查询外显神情观察 | 已实现基础 |
| `GET /api/v1/characters/{character_id}/appearance-states` | 查询阶段外观状态 | 已实现查询；自动聚合未闭环 |
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

### 12.3 一期目标接口：尚未注册

以下端点属于图像生成目标契约。当前 `/api/v1/capabilities` 返回 `image_generation=false`，调用这些路径会得到 `404`，实现前不得由客户端依赖：

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
