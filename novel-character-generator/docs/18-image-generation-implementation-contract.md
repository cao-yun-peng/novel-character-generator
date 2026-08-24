# 图像生成端到端实现契约

> [← 上一篇](17-appearance-aggregation-contract.md) · [文档索引](README.md) · [下一篇 →](19-feature-traceability-matrix.md)
>
> 文档版本：2.9 · 修订日期：2026-08-24
>
> 当前状态：仅设计，目标接口尚未注册，`GET /api/v1/capabilities` 返回 `image_generation=false`。本页定义实现边界，不声明当前已经支持图像生成。

## 1. 前置条件

创建 Image Run 前必须同时满足：

- 角色存在已批准、未失效的 RenderProfile；
- 请求明确指定 timeline，并在多阶段情况下指定 event、scene、chapter 或已确认 stage；
- Profile 没有阻断生成的开放冲突；
- `GenerationContextBuilder` 能形成不可变 `context_hash`；
- 唯一一期 WorkflowProfile 已经过契约测试并发布；
- Provider 能力、许可证、预算和目标候选数量已经确认；
- 当前 capability 已由部署实例显式启用。

缺少任一条件时在收费提交前失败，不能创建“看似运行、实际永远无法完成”的远程任务。

## 2. API 契约

目标入口：

```http
POST /api/v1/characters/{character_id}/image-runs
Idempotency-Key: <client-stable-key>
Content-Type: application/json
```

```json
{
  "timeline_id": "uuid",
  "target_event_id": "uuid-or-null",
  "target_scene_id": "uuid-or-null",
  "target_chapter_ordinal": null,
  "stage_keys": ["adult"],
  "candidate_count": 4,
  "generate_character_sheet": false,
  "render_overrides": {},
  "budget_limit": "2.00"
}
```

成功返回 `202 Accepted`：

```json
{
  "run_id": "uuid",
  "character_id": "uuid",
  "status": "queued",
  "generation_context_ids": [],
  "estimated_cost": "1.20"
}
```

相同 `Idempotency-Key` 和相同请求指纹返回原 Run；同一 Key 携带不同请求返回 `409 idempotency_key_reused_with_different_payload`。客户端通过现有 Run 和 SSE 接口查询进度，不新增另一套任务状态协议。

## 3. Step 图

```text
validate_image_request
  → freeze_generation_context
  → plan_image
  → submit_image
  → poll_image
  → persist_image
  → audit_drift
  → gate_candidate
      ├─ hard_fail + 有预算 → regenerate_once → audit_drift → gate_candidate
      ├─ hard/soft_fail → waiting_approval
      └─ pass → waiting_baseline_selection
  → select_baseline（用户动作）
  → lock_image_set
```

每个 Step 必须有稳定 `step_key`、输入/输出 Schema、最大 attempt、可重试错误集合和取消语义。`regenerate_once` 最多执行一次；人工重新发起的新 Run 不计入同一自动循环，但必须引用上一 Run 和原因。

## 4. 确定性代码与 Agent 边界

| 工作 | 执行者 |
|---|---|
| 解析目标时点、选择有效状态、冻结 context hash | 确定性 Application Service |
| 选择构图、灯光、Prompt 表达 | Visual Director Agent |
| Workflow 兼容、预算、权限、幂等键 | 确定性策略层 |
| 提交、查询、下载远程任务 | Image Provider Adapter |
| 判断候选图可见属性和异常 | Multimodal Critic Agent + 确定性检查器 |
| hard/soft gate、重生成上限 | 确定性策略层 |
| 最终基准图、覆盖和锁定 | 用户/审批 Service |

Agent 不能直接提交收费任务、修改 Profile、锁定基准图或提升预算。Visual Director 和 Critic 共享同一 `GenerationContextSnapshot`；Critic 看到不同 `context_hash` 时必须返回 `audit_context_mismatch`。

## 5. GenerationContext 冻结

`freeze_generation_context` 按[角色渲染档案](05-character-render-profile.md)解析 `ResolvedCharacterSnapshot`，再按[视觉防漂移设计](06-image-generation-and-drift-control.md)形成不可变上下文。至少冻结：

- Profile、AppearanceState、timeline/event/scene 和 Snapshot 版本；
- 身份、阶段、场景和负向约束；
- Evidence IDs 与阶段基准图引用；
- Workflow、Prompt、AgentSpec、Evaluator Bundle 版本；
- 候选数量、预算和裁剪原因；
- `context_hash`。

Provider、Agent 和审计器只读取冻结上下文，不在运行中重新查询“最新 Profile”。Profile 后续变化通过失效传播处理，不能静默改变已提交 Run。

## 6. Provider 端口

```python
class ImageProvider(Protocol):
    async def submit(self, request: ImageSubmitRequest) -> ImageSubmission: ...
    async def query(self, provider_request_id: str) -> ImageRemoteStatus: ...
    async def cancel(self, provider_request_id: str) -> CancelResult: ...
    async def download(self, artifact_ref: str) -> AsyncIterator[bytes]: ...
    def capabilities(self) -> ImageProviderCapabilities: ...
```

`ImageProviderCapabilities` 明确声明幂等键、取消、Webhook、请求指纹查询、远程状态保留期和费用返回能力。不支持的能力不能由 Adapter 伪造。

## 7. 外部提交与事务边界

收费提交必须使用 `ExternalOperation` 关闭崩溃窗口：

1. 事务 A：校验当前 lease/fencing，写入 `prepared`、请求指纹、幂等键哈希和预计费用；
2. 提交事务 A；
3. 调用 Provider `submit`；
4. 事务 B：保存 Provider request ID、提交结果、费用快照并推进 Step；
5. 如果第 3 步结果未知，写 `submission_unknown`，停止自动重提，进入查询指纹/人工对账；
6. 重启后先读取 `ExternalOperation`，查询已知远程任务，不重新调用 submit。

稳定 Provider 幂等键：

```text
context_hash + workflow_profile_version + seed + candidate_index + attempt_index
```

下载先写临时文件，完成大小、MIME、图像解码和 SHA-256 校验后原子移动，再在事务中写 Artifact 与 GeneratedImage。数据库记录和文件必须能通过哈希对账。

## 8. 错误分类与恢复

| 分类 | 示例 | 自动行为 |
|---|---|---|
| 请求阻断 | 未批准 Profile、目标阶段歧义、开放冲突 | 不提交 Provider，返回 409/422 |
| 可重试远程错误 | 429、暂时性 5xx、查询超时 | 指数退避、有限重试，保留同一 ExternalOperation |
| 提交结果未知 | 网络在 submit 后中断 | `submission_unknown`，查询或人工对账，禁止盲目重提 |
| 永久远程错误 | Workflow/模型不兼容、请求非法 | Step 失败，不自动换模型或 Workflow |
| 产物错误 | MIME、大小、解码或哈希失败 | 拒绝落库，可有限重新下载，不锁定 |
| 审计 hard fail | 错身份、错阶段、错时间线、多余人物 | 禁止锁定；最多自动重生成一次 |
| 预算/截止时间耗尽 | 预计费用超限、deadline 到期 | 停止并转人工，不扩大预算 |
| 取消 | 本地取消且 Provider 支持/不支持取消 | 记录真实远程状态；不能谎称已取消收费任务 |

## 9. 候选、审计与锁定

每张候选图必须按顺序具有：

```text
GeneratedImage
  → DriftAuditResult
  → GateDecision
  → 可选 HumanApproval
  → BaselineSelection
```

没有审计或 gate 的图不能进入选择池；`hard_fail` 不能成为 baseline，除非规则明确允许且存在有效人工覆盖记录。成为阶段 baseline 后仍不反向写入 FeatureObservation、AppearanceState 或身份事实，只能作为后续生成的受控参考图。

Profile、目标状态、关键证据、Workflow 或 Evaluator 发生影响语义的变化时，旧候选和 baseline 标记 stale，进入重新确认队列；历史文件和审计记录保留。

## 10. 关键日志

实现必须使用[可观测性与日志检查](13-observability-logging-and-cost.md)定义的稳定事件：

- `generation.snapshot.resolved`；
- `generation.context.frozen` / `generation.context.rejected`；
- `budget.check.completed`；
- `provider.operation.submit_started/succeeded/unknown`；
- `artifact.persisted`；
- `generation.drift_audit.completed`；
- `generation.gate.decided`；
- `generation.regeneration.scheduled/blocked`；
- `generation.baseline.selected`、`generation.imageset.locked`；
- `generation.dependency.invalidated`。

日志只保存 ID、版本、哈希、状态和费用摘要，不保存完整 Prompt、密钥、签名 URL 或人脸 embedding。业务表先提交，日志后输出。

## 11. 实现顺序

1. `GenerationContextBuilder`、持久化 Schema 和 hash 稳定性测试；
2. WorkflowProfile 注册、固定 Mock Image Provider 和契约测试；
3. Image Run API、Step 图与 ExternalOperation 恢复；
4. 一个真实 Provider Adapter 的 submit/query/download；
5. Artifact 原子落库和完整性检查；
6. 确定性基础审计，再接 Multimodal Critic；
7. gate、一次受控重生成、人工审批和 baseline 锁定；
8. 结构化日志与最小 `log-check`；
9. 评测集、成本门禁和 capability 开启。

不能先注册空图像端点、返回假成功或仅保存 Provider URL，再回头补 ExternalOperation、context hash 和审计。

## 12. 完成定义

将 `image_generation` 改为 `true` 前必须满足：

- 目标端点已经注册并有 OpenAPI/错误契约；
- 从已批准快照到候选图、审计、gate、人工选择形成闭环；
- 重复请求、Worker 崩溃、submit 未知、重复回调均不重复收费或产物；
- hard fail 无法无记录锁定；
- Profile 变化会使依赖产物 stale；
- Provider、Workflow、模型、Prompt、seed、context hash、费用和文件哈希可追溯；
- Provider 契约、恢复、安全、评测和日志检查测试通过；
- [API 规范](09-api-specification.md)、[当前实现状态](00-current-status.md)和[追踪矩阵](19-feature-traceability-matrix.md)同步更新。

---

[← 上一篇](17-appearance-aggregation-contract.md) · [文档索引](README.md) · [下一篇 →](19-feature-traceability-matrix.md)
