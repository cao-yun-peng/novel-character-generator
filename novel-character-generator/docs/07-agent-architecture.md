# Agent 增强架构

> [← 上一篇](06-image-generation-and-drift-control.md) · [文档索引](README.md) · [下一篇 →](08-task-recovery.md)
>
> 文档版本：2.8 · 源章节：10. Agent 增强架构 · 修订日期：2026-08-22

## 10. Agent 增强架构

### 10.1 定位与边界

本项目采用“确定性应用编排 + 可插拔 AgentRuntime”，而不是全自主多 Agent 系统或全流程图编排：

```text
Application Orchestrator
  ├── StructuredCallAgentRuntime     一期默认
  │   ├── Extraction Agent           块级事实提取
  │   ├── Entity Resolution Agent    实体、别名和共指提案
  │   ├── Visual Director Agent      生成视觉方案
  │   ├── Multimodal Critic Agent    审核候选图
  │   └── Review Agent               复杂证据与冲突审计
  └── LangGraphAgentRuntime          仅局部 PoC，默认关闭
```

Application Orchestrator 决定何时调用哪个 Agent、是否重试、何时停止以及是否转人工。专项 Agent 不互相自由对话，也不能绕过应用服务调用另一个 Agent。跨 Agent 传递的是经过 Schema 校验的结构化产物和证据 ID，而不是完整聊天历史。

职责边界：

| 由 Agent 负责 | 由确定性代码负责 |
|---|---|
| 理解文本语义和歧义 | 数据库事务和状态转换 |
| 提出实体链接或合并建议 | 权限、预算、并发和重试 |
| 生成视觉创作方案 | 外部任务提交与幂等 |
| 根据图像判断属性与问题 | Schema 校验和产物保存 |
| 给出带证据的审计意见 | 最终锁定、发布和删除 |

### 10.2 Agent 注册与版本

每个 Agent 通过 `AgentSpec` 注册：

```python
class AgentSpec(BaseModel):
    agent_id: str
    version: str
    objective: str
    model_policy: str
    prompt_version: str
    allowed_tools: list[str]
    output_schema: str
    max_turns: int
    max_tool_calls: int
    max_cost: Decimal
    deadline_seconds: int
    approval_policy: str
    enabled: bool = True
```

运行时将 Agent、Prompt、工具集合、Schema、模型策略和评测版本一起固定到 `agent_runs`。升级任一组成部分都创建新版本，历史运行不得被新配置静默解释。

### 10.3 Extraction Agent

Extraction Agent 负责单个文本块的批量事实提取：

- 找出块中的人物提及、视觉描述、可见神情和明确内心情绪；
- 提出场景边界、叙事模式和时间线候选，但不直接决定复杂时间归属；
- 查询当前块相关角色的最小摘要；
- 生成别名假设和字段级 ObservationDraft；
- 为每条观察返回原文区间、引用和置信度；
- 区分外显神情与内在情绪，不把推测出的心理状态伪装成原文事实；
- 将无法确定的指代放入待解决列表。

允许的典型工具：

```text
get_chunk_context          获取当前块及偏移信息，只读
search_related_characters  查询可能相关角色，只读
get_character_summary      获取精简角色摘要，只读
validate_observation       本地Schema和证据区间校验，只读
submit_observation_drafts  提交候选，不直接写正式事实
```

Extraction Agent 保持“每块一次主任务”的成本边界。工具调用不能演变为逐角色再次发送完整文本；当上下文不足时返回 `needs_followup`，由 Orchestrator 决定是否追加一次受限补充调用。

### 10.4 Entity Resolution Agent

Entity Resolution Agent 仅在规则和历史索引无法确定时启动，输出提案而不是直接合并：

```python
class EntityResolutionProposal(BaseModel):
    action: Literal["link", "merge", "split", "create", "defer"]
    source_entity_ids: list[UUID]
    target_character_id: UUID | None
    supporting_evidence_ids: list[UUID]
    confidence: float
    explanation: str
    requires_human_review: bool
```

以下情况必须人工确认：

- 合并两个已经拥有多条事实或图片的角色；
- 拆分会改变已批准 RenderProfile 的角色；
- 同名角色、跨时间身份变化或证据互相矛盾；
- 置信度低于评测集标定阈值；
- 操作会触发大量事实重绑定或重新生成。

批准通过后由 Application Service 在事务内执行合并/拆分，并写入 `decision_records` 与 `human_approvals`。

### 10.5 Visual Director Agent

Visual Director Agent 只读取经过确定性解析并已批准的 `ResolvedCharacterSnapshot`，不得自行选择角色处于哪个年龄、时间线或现实层级，也不得从身份标签编造新的角色事实。它负责：

- 选择兼容的 WorkflowProfile；
- 规划画面构图、镜头、灯光、背景和风格；
- 构建正面与负面 Prompt；
- 标记跨候选图必须保持的属性；
- 给出候选数量、成本预估和警告。

```python
class VisualPlan(BaseModel):
    resolved_snapshot_hash: str
    workflow_profile_id: str
    positive_prompt: str
    negative_prompt: str
    locked_attributes: list[str]
    composition: CompositionPlan
    candidate_count: int
    estimated_cost: Decimal
    warnings: list[str]
```

Agent 只生成计划。Workflow 兼容性、预算检查和收费任务提交由确定性代码完成。

### 10.6 Multimodal Critic Agent

Multimodal Critic Agent 读取候选图、ResolvedCharacterSnapshot、关键证据和生成快照，按三层一致性检查：

- 人物数量、画面完整性和明显畸形；
- 身份层：跨时间应保持的脸部身份和独特标记；
- 阶段层：目标时点的年龄、发型、服装、疤痕、伪装和配色；
- 场景层：本场景姿势、临时伤势和外显神情；
- Prompt 遵循、角色身份和主体一致性；
- 是否需要保留、重生成或人工审核；
- 重生成时应调整的明确参数，而不是笼统评价。

```python
class ImageCritique(BaseModel):
    attribute_results: list[AttributeCheck]
    identity_score: float | None
    visual_quality_score: float
    prompt_adherence_score: float
    recommendation: Literal["keep", "regenerate", "human_review"]
    regeneration_instructions: list[str]
```

Critic 输出与 ArcFace、DINO、CLIP-I 等确定性指标并列保存。Agent 不得自行选择最终基准图，也不得无限触发重新生成。

### 10.7 Review Agent

Review Agent 处理高价值、低频的复杂审计：

- 主要角色档案提交审核前的证据完整性；
- 原型建议是否覆盖了原文事实；
- 时间变化是否被错误识别为冲突；
- 回忆、梦境、传闻或平行时间线是否污染 canonical 状态；
- 神情是否跨场景错误延续，或把内心情绪错误转成外显表情；
- 是否存在没有证据的推断；
- VisualPlan 是否遗漏关键锁定属性。

它只为主要角色、异常案例或回归失败运行，不参与每个文本块，以控制费用和延迟。其意见作为 `ReviewFinding` 保存，最终修改仍由聚合规则或人工完成。

### 10.8 强类型工具契约

所有 Agent 工具通过统一元数据注册：

```python
class ToolSpec(BaseModel):
    name: str
    version: str
    description: str
    input_schema: str
    output_schema: str
    side_effect: Literal["none", "reversible", "irreversible"]
    idempotency: Literal["not_required", "supported", "required"]
    required_permission: str | None
    requires_approval: bool
    timeout_seconds: int
    estimated_cost: Decimal | None
    error_codes: list[str]
```

规则：

- 工具描述必须说明返回字段、错误行为和副作用；
- Agent 不直接获得 `AsyncSession`、文件系统路径或 API Key；
- 默认只提供只读工具，写工具提交 Proposal/Command；
- 收费、删除、发布和不可逆工具必须由策略层批准；
- 每次调用记录输入输出哈希、耗时、错误码和 `call_id`；
- 工具结果视为不可信输入，进入下一个 Prompt 前执行长度、类型和内容校验。

### 10.9 上下文工程

每次 Agent 运行构建最小上下文包：

```python
class AgentContextPacket(BaseModel):
    objective: str
    current_chunk: ChunkExcerpt | None
    related_characters: list[CharacterSummary]
    relevant_observations: list[ObservationSummary]
    unresolved_questions: list[Question]
    policy_constraints: list[str]
    available_tool_names: list[str]
    token_budget: int
    context_hash: str
```

上下文构建原则：

1. 只选取当前任务相关数据，不把完整长期记忆或对话历史全部塞入；
2. 原始证据优先于多轮摘要，摘要必须附来源 ID；
3. 静态指令、Schema、稳定工具定义放在 Prompt 前缀，便于 Provider 缓存；
4. 动态文本和用户数据放在后部，避免破坏缓存前缀；
5. 超预算时先删除低相关摘要，再缩短证据引用，最后拆分任务；
6. 保存上下文选择清单和哈希，以便复现，不保存隐藏推理内容。

### 10.10 模型路由与能力路由

模型选择由 `ModelRouter` 根据任务和 `LLMCapabilities` 决定，而不是由 Agent 自行升级：

| 任务 | 默认策略 |
|---|---|
| 常规块级提取 | 低成本、低延迟、支持 Structured Output |
| JSON/Schema 修复 | 确定性解析优先，必要时小模型一次修复 |
| 别名和共指歧义 | 中等推理能力模型 |
| 复杂证据审计 | 强推理模型，限主要角色和异常案例 |
| 候选图审核 | 支持图像输入的多模态模型 |
| 状态、预算、权限 | 普通代码，禁止调用模型 |

Provider 不支持工具调用时，Extraction 退化为单次结构化输出；不支持视觉输入时，Critic 退化为确定性指标加人工审核。模型升级必须先通过同一评测集，对比正确率、证据完整性、工具轨迹、延迟和费用。

### 10.11 有界反思与停止条件

只在测量证明有效的环节启用“生成→批评→修订”，例如 Visual Director 与 Critic：

```text
生成 VisualPlan
  → 本地 Schema/兼容性检查
  → Critic 给出问题
  → 最多修订一次
  → 仍失败则转人工，不继续循环
```

建议一期默认上限：

```python
max_agent_turns = 3
max_tool_calls = 12
max_reflection_rounds = 1
max_image_regenerations = 1
deadline_seconds = 180
```

每个 AgentSpec 可以更严格，但不能在运行时自行放宽。达到轮次、费用、时间或重试上限时返回结构化 `AgentLimitReached`，不得用“继续思考”绕过限制。

### 10.12 人工审批与可恢复等待

Agent 需要审批时返回序列化的 `ApprovalRequest`。Application Service 在业务数据库中创建 `human_approvals`，将对应 `PipelineStep` 标记为 `waiting_approval`，随后释放 Worker。审批内容包括：

- 建议执行的动作及影响范围；
- 支撑和反对证据；
- 预计额外费用；
- 可选操作：批准、拒绝、修改、延后；
- 审批过期时间和恢复令牌。

审批完成后，API 通过 compare-and-set 写入决策并将 Step 重新放回队列；Worker 根据业务状态继续下一确定性步骤。等待和恢复不依赖 Graph checkpoint。一期局部 LangGraph Agent 不使用 `interrupt()` 承担业务审批；需要人工决定时必须把请求转换成业务 `ApprovalRequest` 并退出本次 Agent 运行。审批后由应用服务启动新的 Agent attempt，checkpoint 既不作为授权，也不作为业务任务游标。若二期确需恢复同一语义运行，必须单独设计 thread/checkpoint 生命周期和副作用重放测试后再开放。

### 10.13 Agent 轨迹与评测

`AgentTrajectory` 记录可观察执行过程，不记录厂商隐藏思维链：

```python
class AgentTrajectory(BaseModel):
    agent_run_id: UUID
    agent_id: str
    agent_version: str
    context_hash: str
    turn_summaries: list[AgentTurnSummary]
    tool_call_ids: list[UUID]
    decision_record_ids: list[UUID]
    final_output_hash: str
    token_usage: TokenUsage
    latency_ms: int
    cost: Decimal
```

Agent 评测必须同时检查结果和轨迹：

- 最终 Schema、事实和证据是否正确；
- 是否选择了正确工具和参数；
- 是否重复调用或读取无关上下文；
- 是否遵守权限、预算、轮次和停止条件；
- 应当转人工时是否正确升级；
- 最终结果正确但使用危险或越权路径时仍判失败。

### 10.14 一期与二期 Agent 能力边界

一期实现：

- Extraction、Entity Resolution、Visual Director、Multimodal Critic；
- Review Agent 的最小异常审计能力；
- `AgentRuntime` 端口和默认 `StructuredCallAgentRuntime`；
- 强类型工具、ContextPacket、ModelRouter 和有界反思；
- 业务数据库驱动的人工审批等待、Agent 轨迹记录和离线轨迹评测；
- Provider 不支持工具调用时的结构化输出降级；
- 一个隔离的 `LangGraphAgentRuntime` PoC，只用于 `POC-WORKFLOW-01`，默认配置关闭且不进入主流程恢复。

二期实现：

- 动态 Tool Search 和更细粒度 Agent/工具版本灰度；
- Programmatic Tool Calling，用于只读的过滤、聚合、去重和批量查询；
- 可独立拆分任务的并行子 Agent 与交叉审查；
- MCP 客户端接入外部设定库、素材库和知识库；
- A2A 与独立世界观、3D 或游戏资产 Agent 协作；
- 在线 Agent Prompt、工具权限和轨迹评测管理。

Programmatic Tool Calling 和多 Agent 属于 Provider 特定或仍在演进的能力，必须通过 `LLMCapabilities` 探测并提供普通 Tool Calling/工作流降级路径。MCP 只用于跨进程或第三方扩展，不把内部 Repository 无意义地协议化；A2A 只在真正存在独立 Agent 系统时引入。

---

[← 上一篇](06-image-generation-and-drift-control.md) · [文档索引](README.md) · [下一篇 →](08-task-recovery.md)
