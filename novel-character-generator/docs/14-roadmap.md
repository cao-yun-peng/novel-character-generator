# 一期与二期开发路线图

> [← 上一篇](13-observability-logging-and-cost.md) · [文档索引](README.md) · [下一篇 →](15-risks-decisions-and-references.md)
>
> 文档版本：3.0 · 源章节：17. 开发计划、18. 二期开发规划 · 修订日期：2026-08-24
>
> 当前状态：本页是目标路线和退出条件，不是完成进度。实际完成度见[当前实现状态](00-current-status.md)和[追踪矩阵](19-feature-traceability-matrix.md)。

## 17. 开发计划

以下按 1 名熟悉 Python/LLM 的工程师、另有至少 1 名兼职标注/审核人员估算。加入专项 Agent、双时态/状态叠加、图像工作流、可执行评测和安全恢复后，一期内部 Alpha 预计 13–16 周；若只有一人同时承担标注，或同时建设完整前端，应另计工期。

### 17.1 第 0 阶段：技术 PoC（2–3 周）

以下内容均为 **PoC 决策项**。PoC 结束时必须把结论、原始样本、指标、成本和选择理由写入决策记录；在此之前不得将候选方案描述为生产默认值。

| ID | 待决定问题 | 对照方案 | 决策输出 |
|---|---|---|---|
| `POC-TEXT-01` | 中文小说分块参数 | 场景 1K–3K、段落 2K–4K、大块 6K–12K、小块双 pass、邻块上下文 | 分块策略、重叠、最大上下文和每正确字段成本 |
| `POC-RETRIEVAL-01` | 角色视觉精提取检索 | 全文重跑、SQLite FTS5/BM25-only、Embedding API + Qdrant Local vector-only、两路 + RRF 混合召回；候选 embedding profile 至少两种 | 中文词典/分词器、embedding profile、各路 top-K、RRF、邻居数、字段召回、误归属率、API 成本/延迟和每正确字段成本 |
| `POC-AGENT-01` | Extraction Agent 是否值得保留 | 单次结构化调用 vs Agent + 只读工具 | 是否启用 Agent、最大轮次、质量与成本门槛 |
| `POC-ENTITY-01` | 实体链接策略 | 规则优先、候选召回 + LLM 提案等至少两种方案 | 候选召回、自动链接阈值和强制人工条件 |
| `POC-TIME-01` | 一期时间线自动化边界 | 主线、回忆、梦境/传闻及复杂分支样本 | 自动支持集、`defer` 条件和污染率上限 |
| `POC-IMAGE-01` | 固定图像工作流 | SDXL + InstantID vs FLUX + PuLID-FLUX 完整组合 | 唯一一期 WorkflowProfile、资产清单和许可证结论 |
| `POC-IMAGE-02` | 单角色输出多少阶段 | 单一代表形象 vs 2–4 个关键阶段形象集 | 默认阶段数、阶段差异阈值、预算和人工审核上限 |
| `POC-WORKFLOW-01` | 是否为局部复杂 Agent 引入 LangGraph | 默认 StructuredCallAgentRuntime vs 单 Agent 内部 LangGraphAgentRuntime；主流程始终使用 Application Orchestrator | 仅当多轮语义分支产生明确净收益并通过恢复测试时，批准指定 Agent 局部启用；一期业务审批仍以新 attempt 恢复 |
| `POC-EVAL-01` | 评测协议是否可执行 | 文本/实体/时间/Agent/图像 case、确定性 Grader、模型 Grader、人工盲评 | EvalCase Schema、标注手册、split、基线、门禁和报告模板 |

`POC-WORKFLOW-01` 的 LangGraph 采用门槛：

| 条件 | 采用要求 |
|---|---|
| 流程复杂度 | 单个 Agent 至少存在 3 个由运行时语义判断决定的分支 |
| 多轮收益 | 相比 StructuredCall 基线，在同一黄金集上有稳定质量或人工审核效率收益 |
| 成本收益 | 质量收益能够覆盖额外模型调用、checkpoint 和维护成本 |
| 业务审批边界 | 一期 Agent 遇到审批必须结束 attempt；LangGraph 不得绕过业务 `ApprovalRequest` 与新 attempt 规则 |
| 恢复可靠性 | 崩溃、中断、重复恢复、子图和版本升级测试通过，副作用不重复 |
| 状态边界 | Graph State 不保存任务真值、审批授权、费用、外部提交或完整业务对象 |
| 可替换性 | 关闭 LangGraph 后主流程、领域模型和历史业务记录仍可正常使用 |

任一条件不满足，该 Agent 继续使用 `StructuredCallAgentRuntime`。不得因为流程图展示更直观、已有示例代码或框架自带 checkpoint 而采用 LangGraph。

PoC 使用 3–5 个独立合法来源、80–120 个精标 case，至少覆盖 3 个代表角色及其 2 个以上可视阶段，并完成以下验证：

- 用代表性文本片段验证块级结构化提取和精确证据对齐；
- 对比全文重跑与检索增强视觉精提取，验证名字与描述分离时的字段召回和人物归属；
- 对比至少两种实体链接/别名策略；
- 跑通两套图像候选工作流或对无法运行的候选给出明确阻断原因；
- 比较单一代表形象与阶段形象集的价值、重复率和成本；
- 对比单次结构化调用和 Extraction Agent 的质量、延迟与成本；
- 验证工具调用、ContextPacket、有限轮次、业务审批后新 attempt 和外部提交未知状态；
- 建立按小说隔离的 dev/validation/test、EvalCase Schema、初版标注手册和报告模板；
- 输出兼容矩阵、许可证结论、质量基线和真实成本样本。

**退出条件：** P0 数据结构与安全约束已有实现方案，所有 PoC 决策项均形成结论；三个核心命题达到可接受基线。任一生产依赖资产许可证不明确、外部提交无法安全恢复或阶段形象成本超过冻结预算时，不进入对应功能的工程开发。

### 17.2 第 1 阶段：工程基础与任务系统（2 周）

- `src` 骨架、配置、结构化日志；
- OpenTelemetry 初始化、OTLP 导出、Trace Context 传播、`/metrics` 与本地 Collector 配置；
- Async SQLAlchemy 与 Alembic；
- novels/source_document_versions/chapters/chunks/runs/steps/artifacts 表；
- timelines/story_events/scenes 表与最小时间作用域模型；
- 数据库任务领取、`lease_generation` fencing、`external_operations`、取消、重试、对账和 `submission_unknown`；
- 上传、Run 和 SSE API；
- 故障恢复测试骨架。
- `AgentRuntime` 端口、`StructuredCallAgentRuntime`、AgentSpec、ToolSpec、权限和预算守卫骨架；
- `LangGraphAgentRuntime` 只建立隔离 PoC，不接管 PipelineRun/PipelineStep；
- agent_runs/turns/tool_calls/decisions/approvals 以及 eval_datasets/cases/runs/results/grader_versions 表及迁移。

### 17.3 第 2 阶段：文本 Agent 与证据模型（4–5 周）

- 章节识别、动态分块、偏移映射；
- Extraction Agent 与结构化输出降级；
- Entity Resolution Agent、别名、共指和审批中断；
- `MentionSpan`、`AliasAssertion`、规范化偏移映射和 Grounding 校验；
- FeatureObservation 持久化；
- ExpressionObservation、AppearanceState 与场景/时间线候选提取；
- RenderProfile 聚合、多状态叠加、有效时间线继承、目标时点快照解析、冲突和人工编辑；
- ContextPacket、ModelRouter 和工具契约；
- 黄金集、Agent 轨迹集与精度报告。
- 上传后细粒度文本库、SQLite FTS5 中文预分词 BM25、远程 Embedding API + Qdrant Local、RRF、邻居上下文、检索审计与面向缺失字段的视觉精提取；非事实候选进入 Suggestion 审核，不写入 Observation。PoC 由单一检索组件持有 Qdrant Local；多进程并发需求出现后再迁移 Qdrant Server。

### 17.4 第 3 阶段：图像 Agent 与评测（3 周）

- WorkflowProfile 注册与契约测试；
- fal 提交/查询/下载/恢复；
- 候选肖像、阶段形象集、阶段基准图、默认代表形象和设定图选择；
- Visual Director 与 Multimodal Critic；
- 多指标质量评测和最多一次受控修订；
- `GenerationContextBuilder`、冻结上下文、正/负视觉约束与 context hash 全链绑定；
- 身份层、阶段层、场景神情层、时间线和无依据新增的一致性评测；
- hard/soft 漂移门禁、有界重生成、人工覆盖和依赖失效传播；
- 生成快照、费用记录和预算限制。

### 17.5 第 4 阶段：Agent 安全、加固与验收（2–3 周）

- 端到端、重试、取消和崩溃恢复；
- 文件安全、认证、数据删除；
- Prompt 注入、恶意工具输出、权限提升和无限循环测试；
- 工具轨迹、人工升级、缓存与模型路由回归评测；
- 关键业务日志事件插桩、`log-check` 人读/JSON 输出、严格模式和脱敏扫描；
- 6–10 个独立来源、300–500 个文本/Agent case 和 200–300 张评测图像跑批；
- 指标阈值标定；
- 按实际部署能力更新[本地开发、部署与运维手册](16-local-development-and-runbook.md)，完成生产 SLO/RPO/RTO 与二期接口评审。

---

## 18. 二期开发规划

二期不是“有时间再做”的模糊列表，而是在一期数据与任务边界上继续实现。

### 18.1 二期 A：生产化与管理能力（2–4 周）

- PostgreSQL、Redis、分布式 Worker 与优先级队列；
- 对象存储、签名下载、配额与项目隔离；
- Prompt/身份原型草稿、审核、发布、灰度、回滚；
- 完整人工审核 Web UI；
- 多租户 RBAC、操作审计和成本报表。
- 在线 AgentSpec、ToolSpec、Prompt 配置包的审核、灰度与回滚；
- Agent 轨迹浏览、自动评分和回归告警。

### 18.2 二期 B：角色图像量产（2–4 周）

- 自动四视图切割与视图分类；
- 多姿势、同一阶段内的服装变化和场景化生成；
- FLUX + PuLID-FLUX 等第二套工作流；
- 工作流 A/B 测试和按画风路由；
- 30+ 角色批量生成、并发与预算调度。

### 18.3 二期 C：LoRA（2–3 周）

- 训练数据筛选、去重、标注和授权记录；
- 训练任务、checkpoint、失败恢复和成本追踪；
- LoRA 注册表、兼容模型、版本和评测；
- 与 InstantID/PuLID 的效果和成本对比。

### 18.4 二期 D：3D 生成（3–5 周）

```text
已锁定 RenderProfile + 基准图/多视图
  → 3D Provider 提交
  → 远程任务恢复
  → GLB/OBJ 产物
  → 几何/纹理质量检查
  → 拓扑简化与纹理处理
  → 可选骨骼绑定和动画
```

3D Provider 使用与 Image Provider 相同的异步提交/查询协议。二期开始前重新评估 Tripo、Meshy、Stability 及开源方案，不在一期固化当前价格和能力。优先以 GLB 作为交换格式；FBX、STL 是否支持由具体用途决定。

### 18.5 二期 E：知识图谱与批处理（1–2 周）

- 角色关系与关键事件可视化；
- 多小说批处理和跨项目模板；
- 评测结果趋势、Prompt/模型回归告警；
- 增量章节自动触发与差异审核。

### 18.6 二期 F：Agent 互操作与高级编排（2–4 周）

- 动态 Tool Search，只暴露当前任务相关工具；
- Programmatic Tool Calling 处理只读批量查询、去重、过滤和聚合；
- 对可独立拆分的角色/图片审查启用受控并行子 Agent；
- MCP 接入外部世界观文档、素材库、对象存储和知识库；
- A2A 接入独立世界观 Agent、3D Agent 或游戏资产 Agent；
- 为所有高级能力提供 Direct Tool Calling 或普通工作流降级；
- 比较最终正确率、证据完整性、调用数、延迟和费用后再决定是否默认启用。

---

[← 上一篇](13-observability-logging-and-cost.md) · [文档索引](README.md) · [下一篇 →](15-risks-decisions-and-references.md)
