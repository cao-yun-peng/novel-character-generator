# 可观测性、日志检查与成本

> [← 上一篇](12-evaluation-and-acceptance.md) · [文档索引](README.md) · [下一篇 →](14-roadmap.md)
>
> 文档版本：2.7 · 源章节：16. 可观测性与成本控制 · 修订日期：2026-08-22

## 16. 可观测性与成本控制

### 16.1 双层可观测模型

系统同时维护运行时观测和业务追溯，两者通过关联 ID 连接，但用途与保留方式不同：

```text
HTTP / Worker / Scheduler
  → OpenTelemetry Trace（trace_id / span_id）
    → API Span
      → Pipeline Step Span
        → Agent / LLM / Tool / Provider Span
          → Artifact / Evaluation / Approval Span

业务数据库
  PipelineRun → PipelineStep
    → AgentRun / AgentTurn / ToolCall / ModelCall
      → GeneratedImage / Evaluation / HumanApproval / Artifact
```

- 运行时链路回答请求在哪里等待、失败或变慢，使用 OpenTelemetry Trace、Metrics 和结构化日志；
- 业务链路回答为什么产生某项事实或图像、使用了哪些证据、模型、工作流、审批和费用，以业务表为真值；
- Trace 只保存诊断属性和业务 ID，不替代 `pipeline_runs`、`model_calls`、`human_approvals` 等业务记录；
- API 创建根 Span，Worker 从任务记录中的 `traceparent` 或 `trace_context` 恢复父上下文；若原 Trace 已结束，则创建新 Trace 并使用 Span Link 关联原提交 Span；
- Provider 不回传 W3C Trace Context 时，在本地 Client Span 中保存 Provider request ID；不得把内部 Trace Header 发送给未批准的第三方；
- `run_id` 是跨重试、跨进程和长周期业务关联键，`trace_id` 是一次运行时调用树标识，两者不得混用。

一期必须覆盖以下 Span：

| Span | 关键属性 |
|---|---|
| HTTP 请求 | route、method、status、request_id、run_id |
| Worker 领取 | run_id、step_id、queue_wait_ms、lease_generation、attempt |
| Workflow/AgentRuntime 节点 | pipeline_version、node_name；仅启用 LangGraph 时记录 graph_version/checkpoint_id/resume_reason |
| Agent 运行 | agent_id/version、agent_run_id、turn_count、stop_reason、approval_required |
| LLM 调用 | provider、model_revision、usage、cache usage、finish_reason、provider_request_id |
| Tool 调用 | tool_id/version、tool_call_id、side_effect_level、approval_id、result_status |
| 图像 Provider | workflow_profile、external_job_id、submit/query/download 阶段、submission_state |
| 数据库与存储 | operation、表/仓储名、duration、result；不记录 SQL 参数和正文 |
| 人工审批 | approval_id、action_hash、decision、wait_duration；不记录审批密钥 |

### 16.2 日志关联字段

每条结构化日志必须包含 `service_name`、`service_version`、`environment`、时间戳和日志级别；其余关联字段在当前上下文存在时填写：

```text
service_name, service_version, environment,
trace_id, span_id, request_id, run_id, step_id,
agent_run_id, agent_id, tool_call_id, approval_id,
novel_id, character_id, provider, model, workflow_profile,
attempt, lease_generation, duration_ms, error_code
```

日志级别约定：

- `INFO` 记录状态转换、外部调用摘要、审批结果和任务恢复；
- `WARN` 记录可恢复错误、预算临界、租约临近过期和采样降级；
- `ERROR` 记录步骤最终失败、重复副作用风险、数据不一致及人工介入原因；
- 高频轮询、心跳和正常重试使用聚合指标或受控 `DEBUG`，避免日志量随任务时长线性增长。

不记录完整正文、完整 Prompt、API Key、Cookie、Authorization Header、原始人脸 embedding 和带签名下载 URL。错误堆栈在写出前经过统一脱敏过滤器；无法确认安全性的 Provider 原始响应只保存内容哈希和受限摘要。

### 16.3 关键业务日志事件

日志使用单行 JSON，事件名采用稳定的 `domain.action.result` 形式。每条事件除 16.2 的公共关联字段外，必须包含 `event_name`、`event_version`、`event_id`、`occurred_at` 和 `result`。字段增加采用向后兼容方式；删除、改名或语义变化必须提升 `event_version`。

关键事实必须先写入业务表并提交事务，再输出带业务记录 ID 的结构化日志；不能用“日志已写”代替事实、审批、费用或产物落库。日志后端不可用时业务仍可继续，但要递增遥测丢弃指标，并允许检查器通过业务数据库指出 `LOG_MISSING`。

以下位置必须打日志：

| 关键位置 | 事件名 | 级别 | 关键字段与检查目的 |
|---|---|---|---|
| API 接收任务 | `pipeline.run.accepted` | INFO | `request_id`、`run_id`、`pipeline_version`、调用者类型；确认入口唯一 |
| Worker 领取/开始步骤 | `pipeline.step.claimed`、`pipeline.step.started` | INFO | `step_id`、`attempt`、`lease_generation`、`queue_wait_ms`；检查租约和重复执行 |
| 快照解析开始/完成 | `generation.snapshot.resolved` | INFO | `character_id`、`render_profile_id/version`、目标 timeline/event/scene、`resolved_snapshot_hash`、状态数量；确认没有默认使用错误阶段 |
| 生成上下文冻结 | `generation.context.frozen` | INFO | `generation_context_id`、`context_hash`、约束数量、critical 约束数量、裁剪数量、各版本号；检查生成与审计使用同一上下文 |
| 上下文拒绝 | `generation.context.rejected` | WARN/ERROR | `error_code`、未解决冲突数、缺失关键字段、预算缺口；防止带脏状态继续生成 |
| 费用门禁 | `budget.check.completed` | INFO/WARN | 预测成本、剩余预算、计价快照版本、`decision`、`approval_id`；证明收费提交前已检查 |
| 外部任务提交 | `provider.operation.submit_started`、`provider.operation.submit_succeeded`、`provider.operation.submit_unknown` | INFO/WARN | `external_operation_id`、幂等键哈希、Provider、外部 job/request ID、submission state；检查重复扣费和崩溃窗口 |
| 外部任务查询/下载 | `provider.operation.polled`、`artifact.download.completed` | DEBUG/INFO | 查询次数、Provider 状态、artifact ID、内容哈希、尺寸；正常轮询可采样，最终状态必须保留 |
| 产物落库 | `artifact.persisted` | INFO | `artifact_id`、SHA-256、MIME、存储后端、`generated_image_id`；检查数据库与文件一致 |
| 漂移审计完成 | `generation.drift_audit.completed` | INFO/WARN | `drift_audit_id`、`generated_image_id`、`context_hash`、evaluator bundle、各级 finding 数、`overall_decision`、reason codes |
| 门禁决策 | `generation.gate.decided` | INFO/WARN/ERROR | `gate_decision_id`、审计 ID、`pass/soft_fail/hard_fail/needs_human`、规则版本、人工覆盖需求 |
| 安排重生成 | `generation.regeneration.scheduled` | WARN | `previous_attempt_id`、触发 finding IDs、下一 attempt、累计次数、预计追加成本；检查有界循环 |
| 重生成被限制 | `generation.regeneration.blocked` | WARN | 次数、预算或截止时间限制、`stop_reason`；确认不会无限调用 |
| 人工审批等待/恢复 | `approval.requested`、`approval.decided`、`pipeline.step.resumed` | INFO | `approval_id`、动作哈希、决定、操作者 ID 的不可逆化标识、等待时长、恢复 attempt |
| 基准图选择/锁定 | `generation.baseline.selected`、`generation.imageset.locked` | INFO | `baseline_image_id`、ImageSet/Profile 版本、`context_hash`、gate decision、override approval ID；检查硬失败未被静默锁定 |
| 依赖失效 | `generation.dependency.invalidated` | WARN | 原因、旧/新 Profile 或快照哈希、受影响阶段/产物数、重审队列 ID；检查增量更新没有遗留陈旧产物 |
| 步骤完成/失败 | `pipeline.step.completed`、`pipeline.step.failed` | INFO/ERROR | 最终 attempt、lease generation、duration、error category、产物和费用摘要；闭合步骤生命周期 |
| Run 完成/取消 | `pipeline.run.completed`、`pipeline.run.cancelled`、`pipeline.run.failed` | INFO/ERROR | 各状态步骤数、总费用、产物数、漂移结果汇总、终止原因；闭合整个业务链路 |

日志插桩必须位于状态转换的确定性边界，而不是只在 API 路由或异常捕获器里统一打一条：

1. API 层记录请求进入和返回，不复制请求正文。
2. Application Service 在快照解析、上下文冻结、门禁、审批和失效决策后记录业务事件。
3. Worker 在 claim/start/heartbeat/complete/fail 的 compare-and-set 成功后记录租约事件；CAS 失败单独记录 `pipeline.fencing.rejected`。
4. Provider Adapter 围绕 submit/query/download 记录外部操作状态，禁止记录密钥、完整 Prompt 和签名 URL。
5. Artifact Store 在原子写入和哈希校验成功后记录 `artifact.persisted`。
6. Evaluator/Critic 在结构化结果通过 Schema 校验并落库后记录漂移摘要，不记录原始人脸 embedding。
7. Approval Service 在审批请求落库、决定提交和恢复入队三个边界分别记录事件。

`INFO` 事件不得在高层和底层对同一状态重复记录。若确需分别记录运行细节与业务状态，应使用不同事件名并共享业务记录 ID；检查器按 `event_id` 和状态机键去重。

### 16.4 日志检查与输出方案

一期提供离线 `log-check` 检查器，输入 `run_id`，可选 `character_id`、时间窗口和严格模式；数据源包括 JSON 日志、业务数据库、Artifact Store 元数据和当前版本化规则集。检查器不解析完整 Prompt 或正文，也不依赖模型判定，主要执行确定性关联、顺序、数量、哈希和状态机检查。

建议命令接口：

```text
novel-character-generator log-check \
  --run-id <uuid> \
  [--character-id <uuid>] \
  --format human|json \
  --ruleset log-check-v1 \
  [--strict]
```

核心检查规则：

| 检查组 | PASS 条件 | 典型失败码 |
|---|---|---|
| 链路闭合 | Run 有唯一入口和终态，每个已开始 Step 有完成、失败、取消或等待审批状态 | `RUN_TERMINAL_MISSING`、`STEP_ORPHANED` |
| 关联完整 | 关键事件携带可回查的 run/step/attempt/业务记录 ID，父子关系可连接 | `CORRELATION_ID_MISSING` |
| 租约与幂等 | 写入 attempt 使用当前 `lease_generation`；同一幂等键没有多个收费提交或重复产物 | `STALE_LEASE_WRITE`、`DUPLICATE_PROVIDER_SUBMIT` |
| 费用顺序 | 每个收费 submit 前存在通过的 budget check；Provider usage 与 Run 汇总可对账 | `BUDGET_CHECK_MISSING`、`COST_RECONCILIATION_FAILED` |
| 快照一致 | snapshot、context、Provider 请求、artifact、audit 和 baseline 全链使用相同 `context_hash` | `CONTEXT_HASH_MISMATCH` |
| 漂移门禁 | 每个候选图都有审计和 gate；hard fail 不能锁定，除非存在明确人工覆盖且规则允许 | `AUDIT_MISSING`、`HARD_FAIL_LOCKED` |
| 有界重生成 | 每次重生成引用上一 attempt 和 finding，次数/费用/截止时间未超限 | `REGEN_PARENT_MISSING`、`REGEN_LIMIT_EXCEEDED` |
| 审批恢复 | waiting_approval 有请求记录；恢复事件引用已决定且未过期的 approval | `APPROVAL_RECORD_MISSING`、`INVALID_APPROVAL_RESUME` |
| 产物完整 | 数据库 artifact 哈希、文件哈希和 GeneratedImage 引用一致 | `ARTIFACT_HASH_MISMATCH`、`ARTIFACT_MISSING` |
| 失效传播 | Profile/快照变化后旧产物为 stale 或重新确认，不能继续作为未标记基准图 | `STALE_BASELINE_ACTIVE` |
| 安全脱敏 | 日志中没有正文、完整 Prompt、密钥、Authorization、签名 URL 或人脸 embedding | `SENSITIVE_LOG_FIELD` |
| 事件规范 | event name/version 合法，必填字段齐全，未知字段不破坏解析 | `EVENT_SCHEMA_INVALID` |

检查结果分三级：

- `PASS`：证据充分且规则满足；
- `WARN`：业务状态正确但日志缺失、采样或非关键字段不完整，需要补插桩；
- `FAIL`：可能产生错误事实、错误图像、重复费用、越权放行或不可追溯结果。

人读输出必须先给结论，再给可定位证据：

```text
LOG CHECK  run=<run_id>  ruleset=log-check-v1  result=FAIL
Summary    PASS=18  WARN=2  FAIL=1  checked_events=47

[FAIL] Drift gate       HARD_FAIL_LOCKED
       character=<id> stage=adult baseline_image=<id>
       audit=<id> decision=hard_fail locked_event=<event_id>
       expected: reject or valid override approval

[WARN] Telemetry        LOG_MISSING
       business record exists for artifact=<id>, but artifact.persisted was not exported

Timeline
  10:03:11 pipeline.run.accepted
  10:03:13 generation.context.frozen context_hash=8f3a…
  10:03:14 budget.check.completed decision=pass
  10:03:15 provider.operation.submit_succeeded
  10:04:02 generation.drift_audit.completed decision=hard_fail
  10:04:07 generation.imageset.locked  <-- violation
```

机器输出使用稳定 Schema，供 CI、发布门禁和故障诊断消费：

```json
{
  "schema_version": "log-check-output-v1",
  "ruleset_version": "log-check-v1",
  "run_id": "...",
  "result": "fail",
  "summary": {"pass": 18, "warn": 2, "fail": 1, "checked_events": 47},
  "findings": [
    {
      "severity": "fail",
      "check_group": "drift_gate",
      "code": "HARD_FAIL_LOCKED",
      "message": "hard-failed candidate was locked without an allowed override",
      "entity_refs": {"audit_id": "...", "baseline_image_id": "..."},
      "event_ids": ["..."],
      "remediation": "unlock the image set and require regeneration or approval"
    }
  ]
}
```

退出码约定为：`0` 表示没有 FAIL（可含 WARN），`1` 表示发现 FAIL，`2` 表示关键数据源不完整而无法得出结论，`3` 表示参数或检查器内部错误。CI 严格模式可以把指定 WARN（例如关键日志缺失或脱敏扫描未执行）提升为 FAIL。

检查器本身也要可测试：使用固定 JSON 日志夹具覆盖正常链路、重复提交、陈旧租约、上下文哈希漂移、hard fail 被锁定、审批恢复、产物损坏和敏感字段泄漏；规则升级时同时保存旧规则结果和新规则 diff，禁止静默改变历史报告。

### 16.5 指标体系

所有指标标签必须低基数。允许的常用标签包括 `service`、`environment`、`operation`、`provider`、`model_family`、`workflow_profile`、`status` 和稳定错误类别；`run_id`、`novel_id`、`character_id`、`request_id`、Prompt 文本和外部 job ID 禁止作为 Metrics 标签，只存在于 Trace 或日志中。

| 类别 | 指标 |
|---|---|
| API | 请求量、状态码、P50/P95/P99 延迟、SSE 活跃连接与断开数 |
| Worker | 队列深度、等待时间、执行时间、领取失败、心跳延迟、租约过期、fencing 拒绝写入数 |
| 任务恢复 | 重试数、恢复成功率、`submission_unknown` 数量与停留时间、重复回调/产物去重数 |
| LLM | 输入/输出/cache tokens、调用延迟、限流、超时、Schema 校验失败与修复率 |
| Agent | 成功率、平均轮次、工具调用数、无效/重复调用率、人工升级率、达到限制次数 |
| 图像 | 每阶段候选数、生成时延、失败率、重生成率、阶段基准图接受率 |
| 审批 | 待审批数量、等待时间、过期率、修改率、重复消费阻止数 |
| 数据库 | 事务时长、写锁/忙超时、连接池等待、迁移版本 |
| 成本 | 每小说、角色、阶段、成功产物和 Agent 任务成本；预算预测与实际偏差 |
| 质量 | 有效事实数、实体待审比例、证据定位率、工作流版本质量与成本对比 |

一期 `/metrics` 只允许内网访问或经过管理权限保护。业务报表可以查询数据库中的高基数字段，不通过 Metrics 系统承载。

### 16.6 采样与保留

- 本地开发和 PoC 默认 100% Trace；生产默认采用父级继承的比例采样，初始建议 10%，上线后按吞吐和成本调整；
- 错误、超预算、`submission_unknown`、租约冲突、审批、数据不一致和安全事件需要完整保留。若后端不支持尾部采样，则通过独立审计事件和业务记录保证不丢失；
- 成功任务可降低 Trace 采样，但业务 Run、Step、费用、审批和产物记录不得采样丢弃；
- 日志、Trace、Metrics、Agent 轨迹和业务审计分别配置保留周期；具体天数由部署环境、用户协议和合规要求配置，不在代码中硬编码；
- 删除小说时，按数据治理策略删除或匿名化关联日志索引、Trace 属性和业务记录；聚合且不可反查个人或小说的 Metrics 可继续保留；
- 观测后端不可成为主流程硬依赖。Collector 或后端不可用时使用有界内存队列和批量导出，队列满后丢弃普通遥测并递增 `telemetry_dropped_total`，不得阻塞生成任务。

### 16.7 告警与诊断

一期至少配置以下告警类别，阈值先由 PoC 基线标定，再保存为版本化配置：

| 告警 | 触发信号 | 处理方向 |
|---|---|---|
| 任务卡死 | Step 长时间无心跳或无进度事件 | 检查 Worker、租约和外部任务状态 |
| 租约异常 | 租约频繁过期或 fencing 拒绝写入增加 | 检查 Worker 停顿、数据库锁和时钟 |
| 外部提交不确定 | `submission_unknown` 数量或停留时间超限 | 停止自动重提，查询 Provider 或人工对账 |
| Provider 异常 | 超时、429、5xx 或延迟持续升高 | 降低并发、退避或暂停对应工作流 |
| 费用异常 | 实际费用超过预测区间或预算消耗突增 | 暂停新收费步骤并请求确认 |
| Agent 异常 | 循环、重复工具调用、Schema 修复或人工升级率突增 | 回滚 AgentSpec/Prompt/模型版本 |
| 质量回归 | 证据定位、实体链接或阶段图接受率低于基线 | 阻止相关版本发布并运行黄金集 |
| 遥测失效 | 导出失败、队列积压或遥测丢弃持续增加 | 检查 Collector；业务任务继续运行 |
| 安全风险 | 脱敏过滤命中密钥、正文或签名 URL | 阻断对应日志事件并触发安全审计 |

每条告警必须附带可查询的 `service`、时间窗口、错误类别及示例 `trace_id` 或 `run_id`，但通知内容不得包含小说正文、Prompt 或签名 URL。

### 16.8 成本公式

不在文档中长期固定价格。运行时从平台价格 API 或配置快照读取：

```text
LLM成本 = Σ(input_tokens × input_unit_price
          + cache_hit_tokens × cache_hit_price
          + cache_write_tokens × cache_write_price
          + output_tokens × output_unit_price)

Agent成本 = Σ(Agent各轮模型成本
             + 工具调用成本
             + 多模态输入成本
             + 反思/修订成本)

图像成本 = Σ(成功输出数量 × 输出单价)
         或 Σ(GPU运行秒数 × GPU秒单价)

单角色成本 = 分摊文本提取成本
           + Agent审计与规划成本
           + 候选图成本
           + 设定图成本
           + 自动评测成本
           + 重试与重生成成本
```

预算检查在提交外部任务前执行：

- 用户可设置 `max_run_cost`；
- 预测超限时暂停等待确认；
- 实际费用来自 Provider usage，而不是只靠本地估算；
- fal 自部署 Serverless 与 Marketplace Model API 计费方式不同，必须分开计算。

---

[← 上一篇](12-evaluation-and-acceptance.md) · [文档索引](README.md) · [下一篇 →](14-roadmap.md)
