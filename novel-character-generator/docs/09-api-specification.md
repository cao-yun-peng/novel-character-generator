# API 规范

> [← 上一篇](08-task-recovery.md) · [文档索引](README.md) · [下一篇 →](10-provider-and-workflow-versioning.md)
>
> 文档版本：2.7 · 源章节：12. API 设计 · 修订日期：2026-08-22

## 12. API 设计

### 12.1 统一规则

- 所有创建长任务的端点返回 `202 Accepted`；
- 支持 `Idempotency-Key`；
- 错误响应包含稳定 `code`、可读 `message` 和 `request_id`；
- 分页使用 cursor；
- 更新 RenderProfile 使用 `If-Match` 或 revision，防止覆盖他人修改；
- 管理类端点必须认证，不能裸露 Prompt/Provider 配置。

### 12.2 一期端点

```text
POST   /api/v1/novels                         上传小说
GET    /api/v1/novels/{novel_id}
POST   /api/v1/novels/{novel_id}/runs        创建文本提取任务

GET    /api/v1/runs/{run_id}                  查询状态
GET    /api/v1/runs/{run_id}/events           SSE进度
POST   /api/v1/runs/{run_id}/cancel           请求取消
POST   /api/v1/runs/{run_id}/retry            重试可重试步骤
GET    /api/v1/runs/{run_id}/agent-runs        查询Agent子任务与预算
GET    /api/v1/runs/{run_id}/external-operations 查询远程提交与对账状态
GET    /api/v1/agent-runs/{agent_run_id}        查询轨迹摘要和工具调用
GET    /api/v1/approvals                         查询待审批项，支持status/type/cursor
POST   /api/v1/approvals/{approval_id}/resolve  批准、拒绝或修改待审批动作

GET    /api/v1/novels/{novel_id}/characters
GET    /api/v1/novels/{novel_id}/timelines
GET    /api/v1/novels/{novel_id}/events
GET    /api/v1/novels/{novel_id}/scenes
PUT    /api/v1/scenes/{scene_id}/temporal-binding 修正timeline/event/presentation
GET    /api/v1/characters/{character_id}/observations
GET    /api/v1/characters/{character_id}/expressions
GET    /api/v1/characters/{character_id}/appearance-states
GET    /api/v1/characters/{character_id}/conflicts
POST   /api/v1/conflicts/{conflict_id}/resolve
GET    /api/v1/characters/{character_id}/snapshot  按timeline/event/scene解析
GET    /api/v1/characters/{character_id}/render-profile
PUT    /api/v1/characters/{character_id}/render-profile
POST   /api/v1/characters/{character_id}/approve
POST   /api/v1/characters/merge
POST   /api/v1/characters/{character_id}/split

POST   /api/v1/characters/{character_id}/image-runs
GET    /api/v1/characters/{character_id}/images
GET    /api/v1/characters/{character_id}/image-set
PUT    /api/v1/characters/{character_id}/image-set/stages 确认阶段、排序和预算
POST   /api/v1/stage-images/{stage_image_id}/select-baseline
PUT    /api/v1/characters/{character_id}/image-set/default-representative

GET    /api/v1/capabilities
GET    /health/live
GET    /health/ready
GET    /metrics                              Prometheus 格式指标；仅内网或受保护端点
```

### 12.3 二期端点

二期增加 `/prompts`、`/agents`、`/tools`、`/prototypes`、`/loras`、`/models3d`、批量生成、关系图谱与管理审计端点。未启用的二期模块不在一期注册返回空列表的假接口；一期 `/capabilities` 已明确告知当前启用能力，二期只扩展其返回内容。

---

[← 上一篇](08-task-recovery.md) · [文档索引](README.md) · [下一篇 →](10-provider-and-workflow-versioning.md)
