# API 调用手册与错误目录

> [← 上一篇](19-feature-traceability-matrix.md) · [文档索引](README.md)
>
> 文档版本：2.9 · 修订日期：2026-08-24
>
> 当前适用范围：只覆盖源码已经注册的 `0.1.0` 接口。图像目标接口见[图像生成实现契约](18-image-generation-implementation-contract.md)，当前不可调用。

## 1. 基础约定

默认地址：

```text
http://127.0.0.1:8000
```

不想手写请求时，可以打开 `http://127.0.0.1:8000/ui` 使用轻量工作台。工作台调用的仍是本页接口，并按 `/capabilities` 禁用尚未实现的 2D 图像功能。

开发环境中，当 `USER_API_KEY` 和 `ADMIN_API_KEY` 都未配置时，请求以 `development` 身份执行，不需要认证头。配置 Key 后，普通接口使用：

```http
X-API-Key: <user-or-admin-key>
```

合并、拆分和 `/metrics` 等管理操作必须使用管理员 Key。需要记录操作者的写操作还必须提供：

```http
X-Actor-ID: <stable-visible-actor-id>
```

客户端可以发送 `X-Request-ID`；未发送时服务端生成，并在响应头和错误体中返回。

## 2. 错误信封

所有已处理错误返回稳定结构：

```json
{
  "code": "novel_not_found",
  "message": "novel_not_found",
  "request_id": "uuid"
}
```

客户端按 `code` 分支，不解析 `message` 文案。`request_id` 用于关联日志和故障报告。Pydantic 请求校验统一返回：

```json
{
  "code": "validation_error",
  "message": "Request validation failed",
  "request_id": "uuid"
}
```

## 3. 上传小说

PowerShell 7：

```powershell
$novel = Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/novels `
  -Form @{ file = Get-Item data/fixtures/upload-smoke-novel.txt }

$novel
```

响应 `201 Created`：

```json
{
  "id": "uuid",
  "title": "upload-smoke-novel",
  "status": "uploaded"
}
```

上传新源版本：

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/novels/$($novel.id)/versions" `
  -Form @{ file = Get-Item data/fixtures/upload-character-novel.txt }
```

只接受大小限制内的 `.txt`。源版本不可变；重新上传创建新版本，不覆盖旧文件。

## 4. 创建并处理文本 Run

```powershell
$run = Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/novels/$($novel.id)/runs" `
  -Headers @{ "Idempotency-Key" = "analysis-$($novel.id)-v1" }

$run
```

响应 `202 Accepted`：

```json
{
  "id": "uuid",
  "novel_id": "uuid",
  "status": "queued",
  "run_type": "text_analysis"
}
```

相同 Key 和相同目标返回已有 Run；相同 Key 被用于不同请求时返回 `409 idempotency_key_conflict`。当前公开的文本分析 Run 会先执行 `normalize_and_chunk`，再执行 `extract_characters`，上传后可以直接创建，不要求客户端先单独分块。

持续 Worker：

```powershell
uv run python -m novel_character_generator.workers.main
```

查询：

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/runs/$($run.id)"
```

## 5. SSE 续传

首次连接：

```text
GET /api/v1/runs/{run_id}/events?after=0&follow=true
Accept: text/event-stream
```

事件格式：

```text
id: 3
event: step_completed
data: {"step_key":"normalize_and_chunk"}
```

记录最后 `id`，断线后使用：

```text
GET /api/v1/runs/{run_id}/events?after=3&follow=true
```

当前实现使用 `after` 查询参数，不读取 `Last-Event-ID` Header。`follow=false` 只返回当前已存在事件后结束；无新事件时持续连接会发送 keep-alive 注释。

## 6. 取消与重试

```powershell
Invoke-RestMethod -Method Post "http://127.0.0.1:8000/api/v1/runs/$($run.id)/cancel"
Invoke-RestMethod -Method Post "http://127.0.0.1:8000/api/v1/runs/$($run.id)/retry"
```

取消是请求，不保证远程 Provider 已立即取消。当前 Run 不在允许状态时分别返回 `409 run_not_cancellable` 或 `409 run_not_retryable`；没有失败 Step、attempt 已耗尽时也不会盲目重跑。

## 7. 人物与证据查询

```powershell
$characters = Invoke-RestMethod "http://127.0.0.1:8000/api/v1/novels/$($novel.id)/characters"
$characterId = $characters[0].id

Invoke-RestMethod "http://127.0.0.1:8000/api/v1/characters/$characterId/mentions"
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/characters/$characterId/observations"
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/characters/$characterId/expressions"
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/characters/$characterId/appearance-states"
```

当前真实提取链路尚不会自动形成完整 AppearanceState/Profile；测试中的预置状态不代表自动聚合已经完成。

## 8. ETag、If-Match 与档案更新

先获取 Profile 和响应 `ETag`：

```powershell
$response = Invoke-WebRequest "http://127.0.0.1:8000/api/v1/characters/$characterId/render-profile"
$etag = $response.Headers.ETag
$profile = $response.Content | ConvertFrom-Json
```

更新必须携带相同 revision：

```powershell
$body = @{
  identity_anchor = $profile.identity_anchor
  default_stage_key = $profile.default_stage_key
  appearance_state_ids = $profile.appearance_state_ids
  palette = $profile.palette
  field_sources = $profile.field_sources
  field_suggestions = $profile.field_suggestions
  style_preset = $profile.style_preset
} | ConvertTo-Json -Depth 10

Invoke-RestMethod `
  -Method Put `
  -Uri "http://127.0.0.1:8000/api/v1/characters/$characterId/render-profile" `
  -Headers @{ "If-Match" = $etag } `
  -ContentType application/json `
  -Body $body
```

其他客户端先更新后，旧 ETag 会返回 `409 render_profile_revision_conflict`。客户端应重新读取、展示差异并让用户决定，不能自动覆盖。

批准档案还需要 `X-Actor-ID`：

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/characters/$characterId/approve" `
  -Headers @{ "If-Match" = $etag; "X-Actor-ID" = "local-reviewer" }
```

## 9. 目标时点 Snapshot

```text
GET /api/v1/characters/{character_id}/snapshot
  ?timeline_id=<uuid>
  &event_id=<uuid>
  &scene_id=<uuid>
  &chapter_ordinal=<int>
```

参数按实际目标选择，不要求全部提供，但存在时间线数据时通常必须明确 `timeline_id`。多个阶段都可能有效而目标不明确时返回 `409 ambiguous_appearance_state`；不能由客户端静默选择“最新”阶段。

查询角色冲突时，响应中的 `conflict_kind=incompatible_values` 表示自动事实之间矛盾，`conflict_kind=human_confirmation` 表示新自动事实与已批准或人工确认值冲突。两者都必须通过冲突解决接口处理，后者尤其不得由自动任务替用户选择新值。

## 10. 常见错误目录

| HTTP | code | 含义与处理 |
|---|---|---|
| 400 | `invalid_if_match_revision` | `If-Match` 不是允许的整数 revision；重新读取资源 |
| 400 | `approval_cursor_not_found` | 分页 cursor 无效或已不存在；从首页重新查询 |
| 401 | `invalid_api_key` | Key 缺失或错误；检查 `X-API-Key` |
| 403 | `admin_api_key_required` | 普通 Key 调用了管理操作；使用管理员身份 |
| 404 | `novel_not_found`、`run_not_found`、`character_not_found`、`scene_not_found` | 资源不存在或 ID 不属于当前环境 |
| 404 | `render_profile_not_found`、`agent_run_not_found`、`approval_not_found` | 对应派生/审计记录尚未形成或不存在 |
| 409 | `idempotency_key_conflict` | 同一幂等键对应不同业务请求；修正客户端 Key 生成策略 |
| 409 | `render_profile_revision_conflict`、`appearance_conflict_revision_conflict`、`character_revision_conflict` | 并发修改冲突；重新读取后人工合并 |
| 409 | `appearance_conflicts_unresolved` | 开放冲突阻止批准或 Snapshot；先解决冲突 |
| 409 | `render_profile_stale` | 源文档已替换，旧档案仅供审计；等待新分析形成活动草稿 |
| 409 | `ambiguous_appearance_state`、`target_timeline_required` | 目标时间/阶段不明确；补充查询参数 |
| 409 | `run_not_cancellable`、`run_not_retryable`、`run_has_no_failed_step`、`task_attempts_exhausted` | Run 当前不允许该动作；检查状态和 attempt |
| 409 | `entity_operation_idempotency_conflict` | 合并/拆分幂等键冲突；不要换 Key 盲目重试 |
| 413 | `file_too_large` | 超过 `MAX_UPLOAD_BYTES` |
| 415 | `unsupported_file_type`、`txt_file_required` | 只支持 TXT |
| 422 | `validation_error` | 请求 Schema 不合法 |
| 422 | `empty_text_file` | TXT 解码后没有有效文本 |
| 422 | `appearance_state_character_mismatch` | Profile 引用了其他人物的 State |
| 422 | `appearance_state_stale` | Profile 引用了已失效的旧源版本 State；重新读取当前状态 |
| 500 | `internal_error` | 未处理异常；携带 `request_id` 查询服务日志，避免无上限重试 |

错误码会随功能增加，但已有 code 的语义不能静默改变。新增或删除 code 时必须同步路由测试、本目录和 OpenAPI 示例。

## 11. 当前不存在的接口

以下能力在设计文档中存在，但当前请求会得到 `404`：

- `/api/v1/characters/{id}/image-runs`；
- `/api/v1/characters/{id}/images`；
- `/api/v1/characters/{id}/image-set`；
- 阶段 baseline 和默认代表图设置接口；
- Prompt、AgentSpec、WorkflowProfile 在线管理接口；
- EvalRun 执行与报告接口。

客户端应先读取 `/api/v1/capabilities` 再展示功能，不根据文档标题推断部署实例能力。

---

[← 上一篇](19-feature-traceability-matrix.md) · [文档索引](README.md)
