# 架构蓝图与技术栈

> [← 上一篇](01-project-overview-and-principles.md) · [文档索引](README.md) · [下一篇 →](03-domain-data-model.md)
>
> 文档版本：2.7 · 源章节：3. 系统架构、4. 技术选型、5. 项目代码骨架 · 修订日期：2026-08-22

## 3. 系统架构

### 3.1 逻辑架构

```text
┌────────────────────────────────────────────────────────────┐
│ API 层                                                     │
│ FastAPI / 参数校验 / 认证 / 202任务提交 / SSE进度          │
└──────────────────────────┬─────────────────────────────────┘
                           │ 创建或查询 Run
┌──────────────────────────▼─────────────────────────────────┐
│ 应用层                                                     │
│ 用例服务 / 事务边界 / 幂等控制 / 人工审核命令              │
└───────────────┬──────────────────────────┬─────────────────┘
                │                          │
┌───────────────▼──────────────┐  ┌────────▼─────────────────┐
│ Application Orchestrator     │  │ Domain                   │
│ Run/Step 确定性状态机        │  │ Observation/Profile      │
│ DB任务领取、重试、恢复       │  │ 聚合规则、冲突、状态机   │
│ 可插拔 AgentRuntime          │  │                          │
└───────────────┬──────────────┘  └────────┬─────────────────┘
                │                          │
┌───────────────▼──────────────────────────▼─────────────────┐
│ Infrastructure                                             │
│ LLM Provider / Image Provider / SQLAlchemy / 文件存储      │
│ AgentRuntime Adapter / OpenTelemetry / 日志与指标          │
└────────────────────────────────────────────────────────────┘
```

依赖方向为 `API → Application → Domain`；Infrastructure 实现 Domain/Application 声明的端口。Domain 不依赖 FastAPI、SQLAlchemy、fal、LangGraph 或具体 Agent 框架。`pipeline_runs`、`pipeline_steps` 和业务审批表是主流程唯一状态真值。

### 3.2 运行时拓扑

```text
Client
  │
  ▼
FastAPI Process ───────► SQLite / PostgreSQL
  │                           ▲
  │ 创建任务                  │ 原子领取、进度、结果
  ▼                           │
Task Table ◄──────────── Worker Process
                              ├──► LLM API
                              ├──► fal / Image API
                              └──► Artifact Storage
```

一期允许 API 和单 Worker 部署在同一台机器，但必须是两个独立进程。SQLite 模式限制单个写 Worker；二期迁移 PostgreSQL 和分布式队列后再提高并发。

### 3.3 核心处理流程

```text
导入文本
  → 章节识别与文本规范化
  → 稳定分块与内容哈希
  → 块级角色/事实批量提取
  → 当前块实体链接与共指消解
  → 别名归并及人工纠错
  → 写入事实观察
  → 聚合角色渲染档案
  → 人工审核并锁定角色档案
  → 从全部 AppearanceState 中选择 2–4 个关键历史阶段
  → 为每个阶段解析不可变快照并生成候选图
  → 多指标评测
  → 人工选择阶段基准图
  → 选定默认代表形象并形成角色阶段形象集
```

---

## 4. 技术选型

### 4.1 一期技术栈

| 类别 | 选择 | 说明 |
|---|---|---|
| 语言 | Python 3.12 | 类型注解、生态成熟 |
| Web | FastAPI | API、依赖注入、OpenAPI、SSE |
| 数据校验 | Pydantic 2 + pydantic-settings | API 与领域 DTO |
| ORM | SQLAlchemy 2 Async | 全部 Repository 使用 `AsyncSession`，不混用同步 API |
| SQLite 驱动 | aiosqlite | 一期单机存储 |
| 迁移 | Alembic | 禁止以 `create_all()` 或 `init.sql` 代替版本迁移 |
| 主流程编排 | Application Orchestrator + PipelineRun/PipelineStep | 确定性应用服务和数据库状态机是一期默认实现 |
| Agent Runtime | 自定义 `AgentRuntime` 端口；默认 StructuredCall 实现 | 支持单次结构化调用、一次受限修复和有限工具循环 |
| LangGraph | 仅作为局部 AgentRuntime PoC 候选 | 不参与主任务领取、审批授权、收费提交和业务恢复；PoC 达标后才局部启用 |
| HTTP | httpx | LLM 与 Provider 请求，统一超时和连接池 |
| LLM | DeepSeek 或兼容 Provider | 通过能力声明而非仅凭 OpenAI 格式切换 |
| 图像执行 | fal 自部署固定 ComfyUI endpoint，或经验证的模型 API | 工作流和依赖必须固定版本 |
| 图像处理 | Pillow / OpenCV | 读取、裁剪、质量检测；重型模型使用独立执行适配器 |
| 测试 | pytest / pytest-asyncio / respx | 单元、异步、HTTP mock |
| 包管理 | `pyproject.toml` + `uv.lock` | 固定依赖，保证可复现 |
| 日志 | structlog 或标准 logging JSON formatter | 结构化日志，关联 trace_id 与业务运行 ID |
| Trace | OpenTelemetry API/SDK + OTLP | 统一 HTTP、Worker、数据库、Provider 与 Agent Span；业务代码不绑定具体后端 |
| Metrics | OpenTelemetry Metrics 或 Prometheus client | 暴露低基数运行指标与业务指标；一期提供 `/metrics` |
| 本地观测后端 | OpenTelemetry Collector + Jaeger/Tempo + Prometheus/Grafana 中任选可替换组合 | 仅用于开发与 PoC，生产后端由部署环境决定 |

### 4.2 编排与 AgentRuntime 决策

一期默认使用普通应用服务和数据库状态机，不把 LangGraph 作为主流程依赖：

```text
Application Orchestrator
├── PipelineRun / PipelineStep       任务状态与恢复真值
├── HumanApproval                    审批授权与审计真值
├── ExternalOperation               外部提交、查询与对账真值
├── StructuredCallAgentRuntime      默认 Agent 实现
└── LangGraphAgentRuntime            局部 PoC 候选
```

默认 `StructuredCallAgentRuntime` 支持单次结构化调用、Schema 校验、一次受限修复和显式停止原因。小说导入、分块、事实保存、时间线解析、档案聚合、图像任务、费用、审批和恢复均由 Application Orchestrator 控制。

LangGraph 只允许封装在单个复杂 Agent 内部，用于已经证明需要多轮工具调用或运行时语义分支的场景。业务审批不在一期使用 Graph interrupt 恢复：Agent 返回 `ApprovalRequest` 后结束本次 attempt，审批完成后启动新 attempt。即使局部启用，也必须满足：

- Graph State 只保存 JSON 可序列化的临时语义状态和业务 ID；
- 不保存任务状态、审批授权、费用事实、完整正文、ORM/Provider 对象或业务真值；
- 外部副作用仍通过应用服务和幂等业务工具执行；
- checkpoint 不能作为任务恢复、审批审计或外部提交对账的唯一依据；
- LangGraph 版本、图版本和 checkpoint 迁移必须纳入回归测试；
- 关闭 `LangGraphAgentRuntime` 后，主流程和领域模型仍能正常工作。

PoC 未达到采用门槛时，不安装生产 LangGraph 依赖，不创建生产 checkpoint 表，也不为适应 replay 重构确定性业务流程。

### 4.3 Provider 抽象边界

“OpenAI 兼容”只代表请求外形相似，不代表能力完全相同。Provider 必须声明：

```python
class LLMCapabilities(BaseModel):
    structured_output: bool
    json_object_mode: bool
    agent: "AgentCapabilities"
    max_context_tokens: int
    max_output_tokens: int
    supports_seed: bool = False
    supports_idempotency_key: bool = False
```

业务层按能力选择策略，例如优先使用结构化输出，缺失时走 JSON 提取与一次修复流程。禁止把上下文窗口、价格和模型版本硬编码到 Provider 类。

---

## 5. 项目代码骨架

```text
novel-character-generator/
├── pyproject.toml
├── uv.lock
├── .env.example
├── alembic.ini
├── README.md
├── src/
│   └── novel_character_generator/
│       ├── api/
│       │   ├── app.py
│       │   ├── deps.py
│       │   ├── errors.py
│       │   └── routes/
│       │       ├── novels.py
│       │       ├── runs.py
│       │       ├── characters.py
│       │       ├── images.py
│       │       └── health.py
│       ├── application/
│       │   ├── orchestrator.py
│       │   ├── commands/
│       │   ├── queries/
│       │   ├── services/
│       │   │   ├── ingestion_service.py
│       │   │   ├── extraction_service.py
│       │   │   ├── profile_service.py
│       │   │   ├── generation_service.py
│       │   │   ├── external_operation_service.py
│       │   │   ├── approval_service.py
│       │   │   └── evaluation_service.py
│       │   └── ports/
│       │       ├── llm.py
│       │       ├── image_generator.py
│       │       ├── artifact_store.py
│       │       └── repositories.py
│       ├── agents/
│       │   ├── registry.py
│       │   ├── runtime.py
│       │   ├── context_builder.py
│       │   ├── model_router.py
│       │   ├── policies.py
│       │   ├── extraction_agent.py
│       │   ├── entity_resolution_agent.py
│       │   ├── visual_director_agent.py
│       │   ├── multimodal_critic_agent.py
│       │   ├── review_agent.py
│       │   └── tools/
│       │       ├── read_tools.py
│       │       ├── proposal_tools.py
│       │       └── approval_tools.py
│       ├── evaluation/
│       │   ├── schemas.py
│       │   ├── dataset_registry.py
│       │   ├── runner.py
│       │   ├── reports.py
│       │   └── graders/
│       │       ├── deterministic.py
│       │       ├── model_grader.py
│       │       └── human_review.py
│       ├── domain/
│       │   ├── entities/
│       │   ├── value_objects/
│       │   ├── policies/
│       │   │   ├── observation_merge.py
│       │   │   ├── profile_aggregation.py
│       │   │   ├── temporal_resolution.py
│       │   │   ├── conflict_detection.py
│       │   │   ├── snapshot_resolver.py
│       │   │   └── retry_policy.py
│       │   └── exceptions.py
│       ├── pipelines/
│       │   ├── text_pipeline.py
│       │   ├── image_pipeline.py
│       │   ├── states.py
│       │   └── nodes/
│       ├── workers/
│       │   ├── main.py
│       │   ├── task_claim.py
│       │   └── handlers/
│       ├── infrastructure/
│       │   ├── db/
│       │   │   ├── session.py
│       │   │   ├── orm.py
│       │   │   └── repositories/
│       │   ├── llm/
│       │   │   ├── base.py
│       │   │   ├── deepseek.py
│       │   │   └── openai_compatible.py
│       │   ├── agent_runtime/
│       │   │   ├── structured_call.py
│       │   │   └── langgraph_poc.py
│       │   ├── image/
│       │   │   ├── fal_client.py
│       │   │   ├── workflow_registry.py
│       │   │   └── evaluator.py
│       │   ├── storage/
│       │   │   ├── local.py
│       │   │   └── base.py
│       │   └── observability/
│       ├── prompts/
│       │   ├── registry.yaml
│       │   └── v1/
│       ├── agent_specs/
│       │   ├── registry.yaml
│       │   └── v1/
│       ├── image_workflows/
│       │   ├── registry.yaml
│       │   └── sdxl_instantid_v1.json
│       └── settings.py
├── migrations/
├── deploy/
│   └── fal/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   ├── golden/
│   ├── failure_recovery/
│   ├── agent_trajectories/
│   └── e2e/
└── data/
    ├── fixtures/
    └── eval_sets/
```

调整重点：

- 不再使用含义模糊的顶层 `core/` 和 `models/`；
- Pydantic DTO、领域实体和 SQLAlchemy ORM 分开；
- 外部服务全部位于 `infrastructure/`；
- Prompt 和 ComfyUI 工作流作为版本化资源，不写成大型 Python 字典；
- Worker、迁移、契约测试和故障恢复测试从一开始进入骨架。
- Agent 规格、工具契约和 Prompt 分开版本化；Agent 不直接依赖 ORM 或厂商 SDK。

---

[← 上一篇](01-project-overview-and-principles.md) · [文档索引](README.md) · [下一篇 →](03-domain-data-model.md)
