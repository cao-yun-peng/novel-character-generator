# 小说角色插画与 3D 建模生成器——技术设计文档

> 文档版本：2.2
>
> 修订日期：2026-08-14
>
> 文档状态：一期可实施设计，P0 前置项与 PoC 决策项已标注
>
> 说明：模型名称、API 价格和平台能力变化较快，本文只固化接口与验证方法，不把临时价格或未验证的模型组合写成架构保证。

## 目录

- [1. 项目目标与阶段范围](#1-项目目标与阶段范围)
- [2. 关键设计原则](#2-关键设计原则)
- [3. 系统架构](#3-系统架构)
- [4. 技术选型](#4-技术选型)
- [5. 项目代码骨架](#5-项目代码骨架)
- [6. 数据模型](#6-数据模型)
- [7. 文本理解流水线](#7-文本理解流水线)
- [8. 角色渲染档案](#8-角色渲染档案)
- [9. 图像生成与一致性评测](#9-图像生成与一致性评测)
- [10. Agent 增强架构](#10-agent-增强架构)
- [11. 任务系统与断点恢复](#11-任务系统与断点恢复)
- [12. API 设计](#12-api-设计)
- [13. Provider 与工作流版本管理](#13-provider-与工作流版本管理)
- [14. 配置、安全与数据治理](#14-配置安全与数据治理)
- [15. 测试与验收](#15-测试与验收)
- [16. 可观测性与成本控制](#16-可观测性与成本控制)
- [17. 开发计划](#17-开发计划)
- [18. 二期开发规划](#18-二期开发规划)
- [19. 风险与降级策略](#19-风险与降级策略)
- [附录 A：关键设计决策](#附录-a关键设计决策)
- [附录 B：参考资料](#附录-b参考资料)

---

## 1. 项目目标与阶段范围

### 1.1 项目目标

系统从长篇中文小说中提取带原文证据的角色视觉事实，经人工确认形成稳定的角色渲染档案，并为同一角色按已批准的关键历史阶段生成一组可追溯形象，而不是把整本小说压缩成唯一形象。每个阶段形象对应明确的时间线、事件范围和外观状态；系统同时支持选定一个默认代表形象，供列表展示、后续设定图和二期 3D 流程使用。系统需要支持增量章节、失败恢复、生成参数追溯和成本统计，并为二期的多姿势、LoRA、3D 建模及管理界面保留清晰扩展点。

一期不追求“全自动生成整部小说所有角色”，而是先证明三个核心命题：

1. 长篇文本可以按块稳定提取角色视觉事实，并准确保留证据与时间范围。
2. 经人工确认的渲染档案可以稳定驱动一套固定图像工作流。
3. 长任务可以在进程重启、API 超时或单步失败后安全恢复，而不会重复扣费或破坏数据。

### 1.2 一期 MVP 范围

| 能力 | 一期交付标准 |
|---|---|
| 小说导入 | TXT；EPUB 作为一期后半程可选项；统一转为章节与文本块 |
| 文本理解 | 每个文本块一次批量结构化提取，而不是“每块 × 每角色”调用 |
| Agent 增强 | 专项 Agent、强类型工具、上下文包、有界反思、人工审批和轨迹记录 |
| 角色识别 | 实体、别名、称谓与当前块共指消解；支持人工合并/拆分 |
| 事实存储 | 字段级证据、来源、置信度、时间范围、提取运行版本完整保存 |
| 时态与神情 | 区分叙事/故事顺序、主线/分支/梦境；提取外显神情与明确内心情绪 |
| 渲染档案 | 稳定身份、阶段外观、场景状态分层，可人工编辑、锁定和重新计算 |
| 图像生成 | 固定一套已验证工作流；每个主要角色选择 2–4 个已批准关键阶段，每阶段生成候选肖像并锁定一张阶段基准图；生成角色阶段形象集和一张默认代表设定图 |
| 质量评测 | 身份、主体、属性、图像质量多指标组合；人工最终确认 |
| 任务执行 | 独立 Worker、进度查询、取消、幂等、有限重试、断点恢复 |
| 存储 | SQLite + 本地文件，抽象出对象存储接口 |
| 操作界面 | API 与 OpenAPI 文档；最小人工审核端点，不要求完整 Web UI |

### 1.3 二期范围

以下能力不是取消，而是明确放入二期，避免一期同时验证过多不确定技术：

- 自动切割和精修四视图、同阶段多姿势批量生成；
- 超过一期上限的全量阶段自动出图，以及每个章节、每次换装或每个瞬时神情的穷举生成；
- PuLID/InstantID 等多工作流切换和多图像 Provider；
- 角色专属 LoRA 训练与训练任务编排；
- 2D/多视图到 3D、拓扑优化、纹理、骨骼绑定和动画；
- 在线 Prompt 与身份原型管理、版本回滚、差异对比和灰度发布；
- LLM 自动生成身份原型并经过审核后入库；
- 完整人工审核 Web 界面；
- PostgreSQL、Redis 和分布式 Worker；
- 30 个以上角色并行量产；
- 关系图谱可视化和多小说批处理；
- MCP 外部资源/工具接入、A2A 外部 Agent 协作；
- Programmatic Tool Calling、动态工具搜索和并行子 Agent 等 Provider 特定优化。

---

## 2. 关键设计原则

### 2.1 证据先于结论

LLM 输出不是最终事实。每一项视觉特征都必须能够回到原文位置、引用文本、提取运行和模型版本。角色最终用于生成的配置是“渲染档案”，而不是直接把最近一次 LLM JSON 当成真值。

### 2.2 观察事实与渲染决策分离

- `FeatureObservation` 保存原文中观察到的事实，允许多条、冲突和随时间变化。
- `CharacterRenderProfile` 保存用户确认的稳定身份锚点和可用外观阶段；具体生成使用目标时间点解析出的不可变快照。
- 锁定渲染档案不会停止后续事实摄入，只会阻止系统自动改变已确认的生成形象。

### 2.3 块级批量提取

每个块只执行一次主要 LLM 提取，输出该块中所有被提及角色的增量观察。禁止默认执行“每个块 × 每个角色”调用，以免调用量随角色数成倍增长。

### 2.4 长任务与 HTTP 请求解耦

上传、分析和图像生成均创建任务并立即返回 `202 Accepted`。独立 Worker 执行任务，API 只负责提交、查询、取消和流式展示进度。

### 2.5 固定工作流优先于虚假通用化

一期只维护一套经过端到端验证的图像工作流。不同基础模型、身份保持方案和 ControlNet 的组合必须经过兼容性验证后注册为新的 `WorkflowProfile`，不能假设替换模型名即可运行。

### 2.6 可重放、可追溯、可预算

所有外部调用保存请求摘要、响应摘要、token/计费单位、Provider 请求 ID、重试次数和产物哈希。重试必须使用幂等键并区分“未提交”“已提交待查询”“确定失败”。

### 2.7 Agent 负责判断，工作流负责控制

Agent 用于实体歧义、视觉方案、图像审查等需要语义判断的环节；状态转换、预算、权限、重试、数据写入和最终锁定由确定性代码控制。不得让 Agent 自行修改数据库、无限调用工具或自行提高预算。

### 2.8 最小权限和有界自治

每个 Agent 只能看到完成当前任务所需的工具和上下文，并具有明确的最大轮次、工具调用数、费用、截止时间和停止条件。涉及合并角色、发布配置、提交收费生成、删除数据或扩大任务范围时，需要确定性策略或人工批准。

---

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
│ Workflow / Worker            │  │ Domain                   │
│ LangGraph 外层编排           │  │ Observation/Profile      │
│ DB任务领取、重试、恢复       │  │ 聚合规则、冲突、状态机   │
└───────────────┬──────────────┘  └────────┬─────────────────┘
                │                          │
┌───────────────▼──────────────────────────▼─────────────────┐
│ Infrastructure                                             │
│ LLM Provider / Image Provider / SQLAlchemy / 文件存储      │
│ LangGraph Checkpointer / 日志与指标                        │
└────────────────────────────────────────────────────────────┘
```

依赖方向为 `API → Application → Domain`；Infrastructure 实现 Domain/Application 声明的端口。Domain 不依赖 FastAPI、SQLAlchemy、fal 或 LangGraph。

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
| 工作流 | LangGraph | 只处理需要暂停、恢复和条件路由的外层流程 |
| Checkpoint | AsyncSqliteSaver | 一期实验/单机；`thread_id = pipeline_run_id` |
| HTTP | httpx | LLM 与 Provider 请求，统一超时和连接池 |
| LLM | DeepSeek 或兼容 Provider | 通过能力声明而非仅凭 OpenAI 格式切换 |
| 图像执行 | fal 自部署固定 ComfyUI endpoint，或经验证的模型 API | 工作流和依赖必须固定版本 |
| 图像处理 | Pillow / OpenCV | 读取、裁剪、质量检测；重型模型使用独立执行适配器 |
| 测试 | pytest / pytest-asyncio / respx | 单元、异步、HTTP mock |
| 包管理 | `pyproject.toml` + `uv.lock` | 固定依赖，保证可复现 |
| 日志 | structlog 或标准 logging JSON formatter | 结构化日志、run_id 贯穿 |

### 4.2 为什么保留 LangGraph

LangGraph适合人工中断、条件分支和持久化恢复，但不负责业务事实存储，也不替代任务队列。使用约束如下：

- Graph State 只保存 JSON 可序列化值和业务 ID；
- Provider、Session、Repository、Manager 等运行时对象不得进入 State；
- 编译图时必须配置 checkpointer；
- 每次运行必须提供稳定的 `thread_id`；
- 节点副作用必须幂等；
- 升级图结构时必须提供版本和迁移策略。

若验证后发现一期工作流完全线性，可用普通应用服务替代 LangGraph；领域模型与任务系统不受影响。

### 4.3 Provider 抽象边界

“OpenAI 兼容”只代表请求外形相似，不代表能力完全相同。Provider 必须声明：

```python
class LLMCapabilities(BaseModel):
    structured_output: bool
    json_object_mode: bool
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
│       │   ├── commands/
│       │   ├── queries/
│       │   ├── services/
│       │   │   ├── ingestion_service.py
│       │   │   ├── extraction_service.py
│       │   │   ├── profile_service.py
│       │   │   └── generation_service.py
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
│       ├── workflows/
│       │   ├── text_graph.py
│       │   ├── image_graph.py
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

## 6. 数据模型

### 6.1 核心表

| 表 | 作用 | 关键约束 |
|---|---|---|
| `novels` | 小说元数据与处理状态 | 原文不直接塞入状态快照 |
| `source_documents` | 上传文件、哈希、编码、存储位置 | `sha256` 唯一去重 |
| `chapters` | 章节边界和顺序 | `(novel_id, ordinal)` 唯一 |
| `text_chunks` | 稳定文本块、原文区间和内容哈希 | `(novel_id, ordinal, content_hash)` |
| `timelines` | 主时间线、分支时间线及继承关系 | 分支点以前继承父时间线状态 |
| `story_events` | 故事时间中的事件与因果顺序 | `story_order` 与叙事出场顺序分离 |
| `scenes` | 场景、视角、所在事件和叙事区间 | 每个场景绑定一个时间线 |
| `characters` | 规范角色实体 | 不直接保存完整事实 JSON |
| `character_aliases` | 别名、称谓、有效范围 | `(novel_id, normalized_alias)` 建索引 |
| `feature_observations` | 字段级观察、证据与来源 | 不覆盖旧观察 |
| `expression_observations` | 外显神情、内在情绪、对象和诱因 | 默认只在当前场景有效 |
| `character_appearance_states` | 角色在特定时间段的外观状态 | 同一时间线内有效区间可计算 |
| `character_image_sets` | 一个角色的阶段形象集合、默认代表形象和集合版本 | 每个集合关联已批准阶段，不按章节穷举 |
| `character_stage_images` | 阶段快照、候选图、阶段基准图及排序 | `(image_set_id, appearance_state_id)` 唯一 |
| `character_render_profiles` | 当前生成档案及锁定状态 | 带版本号和乐观锁 |
| `pipeline_runs` | 一次导入/提取/生成运行 | 幂等键唯一 |
| `pipeline_steps` | 步骤状态、尝试次数和游标 | `(run_id, step_key)` 唯一 |
| `run_events` | 面向进度流的追加事件 | 单调序号 |
| `model_calls` | 外部调用、token、价格快照和请求 ID | 请求摘要不得含密钥 |
| `agent_runs` | 一次 Agent 语义任务、版本、预算和最终状态 | 关联 pipeline step |
| `agent_turns` | 每轮模型输出摘要、上下文哈希和使用量 | 不保存隐藏推理内容 |
| `tool_calls` | 工具输入/输出摘要、耗时、错误和副作用 | `call_id` 唯一，写工具需幂等 |
| `decision_records` | 实体合并、档案选择等关键决策及证据 | 保留策略/人工来源 |
| `human_approvals` | 审批对象、审批结果、修改内容与审批人 | 追加写审计记录 |
| `agent_evaluations` | 最终结果、工具选择与执行轨迹评分 | 关联评测集和评分器版本 |
| `artifacts` | 图像、源文件、模型等统一产物 | 内容哈希、MIME、存储 URI |
| `generated_images` | 图像业务元数据和评测结果 | 关联 workflow/profile/run |

一期 Prompt 使用 Git 管理的文件版本；二期增加 `prompt_templates`、`identity_prototypes`、发布记录和管理 API。

### 6.2 P0 前置数据模型

以下数据模型属于 **P0 前置项**，进入一期工程开发前必须补齐。它们决定证据能否重放、角色合并能否回滚，以及后续阶段形象是否可信：

| P0 项 | 最低要求 | 未完成时的限制 |
|---|---|---|
| `MentionSpan` | 持久化每次人名、称谓、代词的原文区间、原始文本、候选角色和最终绑定 | 不允许自动执行实体合并 |
| `AliasAssertion` | 保存别名类型、说话人/视角、场景、时间线、支持与反对证据、审批状态 | 别名只能作为候选召回，不能成为确定关系 |
| 规范化偏移映射 | 版本化记录 Unicode、换行和不可见字符转换，并可逆映射回原文件 | 无法精确回到原文的观察不得批准 |
| Grounding 状态 | 区分 `exact`、`fuzzy`、`ungrounded`、`manually_grounded` | `ungrounded` 默认不得进入 RenderProfile |
| 重叠块去重 | 使用来源版本、证据区间、字段、规范值和提取器版本生成稳定指纹 | 禁止直接按出现顺序去重 |
| 事件参与者 | 保存 actor、patient、observer 等参与角色及证据 | 复杂事件不自动绑定外观变化 |
| 双时态记录 | 区分故事有效时间与系统抽取、审核、失效时间 | 不能可靠重放历史决策 |
| 审核优先级 | 综合影响范围、错误风险、不确定性和角色重要度排序 | 高影响合并与阶段选择必须人工处理 |

```python
class MentionSpan(BaseModel):
    id: UUID
    source_document_version: str
    source_chunk_id: UUID
    char_start: int
    char_end: int
    mention_text: str
    mention_kind: Literal["name", "title", "kinship", "disguise", "nickname", "pronoun"]
    candidate_character_ids: list[UUID]
    resolved_character_id: UUID | None
    grounding_status: Literal["exact", "fuzzy", "ungrounded", "manually_grounded"]
    normalization_map_version: str


class AliasAssertion(BaseModel):
    id: UUID
    alias_text: str
    normalized_alias: str
    mention_span_id: UUID
    proposed_character_id: UUID | None
    speaker_id: UUID | None
    scene_id: UUID | None
    timeline_id: UUID | None
    supporting_evidence_ids: list[UUID]
    opposing_evidence_ids: list[UUID]
    status: Literal["proposed", "approved", "rejected", "superseded"]
```

### 6.3 FeatureObservation

```python
class FeatureObservation(BaseModel):
    id: UUID
    character_id: UUID
    field_path: str                 # 例如 face.eye_color
    value: JsonValue
    source_kind: Literal["text", "prototype", "style", "manual"]
    source_chunk_id: UUID | None
    evidence_quote: str | None
    char_start: int | None
    char_end: int | None
    chapter_ordinal: int | None
    scene_id: UUID | None
    event_id: UUID | None
    temporal_scope: TemporalScope | None  # text/manual事实必填；原型建议可为空
    epistemic_status: Literal["asserted", "negated", "inferred", "uncertain"]
    confidence: float               # 0..1，仅表示抽取置信度
    extraction_run_id: UUID
    extractor_version: str
    supersedes_id: UUID | None
    created_at: datetime
```

规则：

- 原文观察永远不被身份原型覆盖；
- `inferred` 与 `text/asserted` 必须区分；
- 同一字段允许存在多条观察和冲突；
- 用户修订创建新的 `manual` 观察或档案版本，不静默改写历史；
- 原文引用应控制长度并保存精确区间，避免保存无法定位的整段文本。

### 6.4 时间线、事件与场景作用域

章节顺序是“作者何时讲到”，故事时间是“事情何时发生”，两者必须分开。回忆可能出现在第 30 章，但描述的是角色少年期；不能仅用 `chapter_ordinal` 推断角色当时的外观。

```python
class Timeline(BaseModel):
    id: UUID
    novel_id: UUID
    name: str
    parent_timeline_id: UUID | None
    branch_event_id: UUID | None
    canonicality: Literal["canonical", "alternate", "hypothetical"]


class StoryEvent(BaseModel):
    id: UUID
    timeline_id: UUID
    name: str | None
    story_order: Decimal | None       # 故事内顺序，允许后续插入
    starts_at: datetime | None        # 小说给出明确时间时才填写
    ends_at: datetime | None


class Scene(BaseModel):
    id: UUID
    novel_id: UUID
    timeline_id: UUID
    event_id: UUID | None
    chapter_ordinal: int
    narrative_order: int             # 文本中的出场顺序
    point_of_view_character_id: UUID | None


class TemporalScope(BaseModel):
    timeline_id: UUID
    start_event_id: UUID | None
    end_event_id: UUID | None
    start_scene_order: Decimal | None # 同一场景内的先后顺序
    end_scene_order: Decimal | None
    start_chapter_ordinal: int | None
    end_chapter_ordinal: int | None
    scope_type: Literal[
        "instant", "scene", "chapter", "interval", "persistent", "unknown"
    ]
    presentation_mode: Literal[
        "direct", "flashback", "flashforward", "dream",
        "illusion", "rumor", "hypothetical"
    ]
    reality_status: Literal["canonical", "subjective", "alleged", "counterfactual"]
```

规则：

- `narrative_order` 与 `story_order` 独立保存，禁止互相替代；
- 同一场景内“先微笑、后皱眉”使用 `scene_order` 区分连续瞬时状态，不误判为同时冲突；
- 新分支时间线从父时间线继承分支事件以前的角色状态，分支后独立演化；
- 无法定位时使用 `unknown`，不得强行绑定到“当前时间”；
- 梦境、幻觉、传闻和假设保留为证据，但不自动更新 canonical 角色状态；
- 时间线重绑定属于可审计决策，修改后只重算受影响角色的状态和快照。

### 6.5 神情与内外情绪观察

神情可以提取，但必须区分“可见表情”和“角色内心”。例如“嘴角带笑，眼神却冰冷”不能被压缩成单一的 `happy`。

```python
class ExpressionObservation(BaseModel):
    id: UUID
    character_id: UUID
    source_chunk_id: UUID
    char_start: int
    char_end: int
    outward_emotion: Literal[
        "joy", "sadness", "anger", "fear", "surprise",
        "disgust", "calm", "mixed", "unknown"
    ]
    expression_text: str | None       # 受控枚举无法完整表达时的短语
    visible_cues: list[str]           # 皱眉、抿嘴、瞳孔收缩等可见证据
    intensity: float | None           # 0..1
    valence: float | None             # -1..1
    arousal: float | None             # 0..1
    is_masked: bool | None            # 是否刻意隐藏真实情绪
    internal_emotion: str | None      # 仅在原文明确或可靠叙述时填写
    target_character_id: UUID | None
    cause_event_id: UUID | None
    scene_id: UUID | None
    temporal_scope: TemporalScope
    evidence_quote: str
    epistemic_status: Literal["asserted", "inferred", "uncertain"]
    confidence: float
    extraction_run_id: UUID
    extractor_version: str
```

神情默认是 `instant` 或 `scene` 级瞬时状态，不写入永久脸部特征。“常年冷着脸”只有在文本明确表达持续性时，才可形成 `persistent` 的习惯神态观察。内心情绪不得由面部表情反推为事实；模型推断必须标记为 `inferred` 并降低置信度。反过来，内心写着“狂喜”但原文明说“不动声色”时，视觉快照采用外显神情而不是内心情绪。

### 6.6 稳定身份、阶段外观与场景状态

角色描述采用三层模型，避免把少年、成年、受伤后或伪装状态互相覆盖：

```text
IdentityAnchor（跨时间稳定）
  + CharacterAppearanceState（某一阶段有效）
  + SceneCharacterState（当前场景瞬时）
  + RenderOverrides（本次用户明确覆盖）
  = ResolvedCharacterSnapshot（本次生成的不可变快照）
```

```python
class CharacterAppearanceState(BaseModel):
    id: UUID
    character_id: UUID
    temporal_scope: TemporalScope
    label: str | None                 # 少年期、受伤后、宴会伪装等
    age_stage: str | None
    face: FaceBlock | None
    body: BodyBlock | None
    hair: HairBlock | None
    clothing: ClothingBlock | None
    injuries: list[MarkItem]
    distinctive_marks: list[MarkItem]
    cleanliness: str | None
    disguise: str | None
    field_sources: dict[str, list[UUID]]
    status: Literal["draft", "needs_review", "approved"]


class SceneCharacterState(BaseModel):
    character_id: UUID
    scene_id: UUID
    expression_observation_ids: list[UUID]
    pose: str | None
    action: str | None
    temporary_condition: list[str]


class ResolvedCharacterSnapshot(BaseModel):
    character_id: UUID
    timeline_id: UUID
    target_event_id: UUID | None
    target_scene_id: UUID | None
    identity: IdentityBlock
    appearance: CharacterAppearanceState
    scene_state: SceneCharacterState | None
    field_sources: dict[str, list[UUID]]
    unresolved_conflicts: list[ConflictItem]
    resolver_version: str
```

### 6.7 CharacterRenderProfile

```python
class CharacterRenderProfile(BaseModel):
    character_id: UUID
    version: int
    status: Literal["draft", "needs_review", "approved", "locked"]
    identity_anchor: IdentityBlock
    default_appearance_state_id: UUID | None
    appearance_state_ids: list[UUID]
    palette: ColorPaletteBlock
    field_sources: dict[str, list[UUID]]  # observation IDs
    unresolved_conflicts: list[ConflictItem]
    style_preset: str
    approved_by: str | None
    approved_at: datetime | None
    revision: int                      # 乐观并发控制
```

`CharacterRenderProfile` 是用户确认过的角色规则与可用状态集合，不再代表唯一的“当前外观”。每次生成前必须解析出 `ResolvedCharacterSnapshot`。所有 Block 使用 Enum 或受约束字符串，未知值为 `None`。不要使用无法区分缺失、空列表和明确“无”的字段定义。

### 6.8 任务状态机

```text
queued → claimed → running → waiting_external → succeeded
                   │              │
                   ├──────────────┴→ retry_scheduled
                   ├────────────────→ paused_for_review
                   ├────────────────→ cancelled
                   └────────────────→ failed
```

状态变化使用显式允许列表，不能由任意路由直接写字符串。

---

## 7. 文本理解流水线

### 7.1 导入与分块

1. 检测文件类型、编码、大小和恶意内容；计算 SHA-256。
2. 规范换行和不可见字符，但保留原文字符偏移映射。
3. 识别卷、章、节边界；无法识别时按段落回退。
4. 使用目标 token 上限而非固定字符数；字符数只作为快速预估。
5. 大章节在段落/句子边界切分；重叠区保留来源映射。
6. 每块保存内容哈希，使追加章节只创建新块或重算受影响块。

默认候选范围为 1K–12K tokens，不预设单一最优值。**[PoC 决策项 POC-TEXT-01]** 第 0 阶段必须在同一中文小说黄金集上比较场景优先 1K–3K、段落递归 2K–4K、当前大块 6K–12K、小块双 pass 和邻块上下文方案，并按字段 precision/recall、span 准确率、实体链接、重复率、延迟、总成本及“每个正确字段成本”冻结一期参数。PoC 通过前，6K–12K 只能作为对照组，不能写入生产默认配置。

### 7.2 块级提取

每个块一次调用，结构化输出：

```python
class ChunkExtractionResult(BaseModel):
    mentions: list[CharacterMention]
    alias_hypotheses: list[AliasHypothesis]
    observations: list[ObservationDraft]
    expression_observations: list[ExpressionObservationDraft]
    scene_hypotheses: list[SceneHypothesis]
    timeline_hypotheses: list[TimelineHypothesis]
    relations: list[RelationDraft]
    unresolved_references: list[ReferenceDraft]
    warnings: list[str]
```

Prompt 只注入：

- 当前块文本；
- 在当前块出现或可能相关的角色摘要；
- 必需的 Schema；
- 少量跨块待解决问题。

禁止注入全书完整记忆快照。上下文预算在调用前计算，超限时先裁剪低相关记忆，再拆块。

### 7.3 实体链接与共指顺序

正确顺序为：

```text
候选提及检测
  → 当前块称谓/代词共指
  → 与已有角色实体匹配
  → 别名假设聚类
  → 低置信度项进入人工审核
  → 事实绑定到规范 character_id
```

不再先提取角色事实、后做共指。低频实体不能直接丢弃：出现一次但包含外貌描写、对话姓名或关键身份的候选仍需保留。

### 7.4 时间定位与状态解析

角色事实绑定完成后，再执行时间定位，避免“他少年时”中的“他”尚未解析就建立错误状态：

```text
场景边界识别
  → 叙事模式识别（当前/回忆/预叙/梦境/传闻/假设）
  → 故事事件与时间线候选匹配
  → TemporalScope 规范化
  → 观察绑定角色与作用域
  → 按目标时间解析 CharacterAppearanceState
  → 产生 ResolvedCharacterSnapshot 或待审核项
```

时间定位优先使用原文明确时间、事件因果和年龄阶段；章节位置只作为弱证据。复杂倒叙、重生、时间循环和平行世界无法唯一确定时，保留多个候选作用域并进入人工审核，不得让 LLM 静默选择一个版本。

神情提取与外观事实同时进行，但保存为独立 Observation。只有可见线索进入图像渲染；内心独白用于语义理解，不直接转为笑容、哭泣等视觉指令。

### 7.5 增量处理

增量输入基于文档哈希和块哈希，而不是只记录 `chunk_count`：

- 纯追加章节：只处理新增块；
- 中部编辑：从首个变化块开始重提取受影响窗口；
- 删除章节：将相关观察标记为失效，不物理删除审计记录；
- Prompt、模型或 Schema 升级：创建新的 extraction run，可与旧结果对比；
- 聚合档案重新计算不需要再次调用 LLM。
- 场景或事件被重新绑定时间线时，只失效受影响作用域的状态快照，不重跑无关章节；
- `ResolvedCharacterSnapshot` 是派生产物，可按 resolver 版本重建，不作为唯一事实源。

### 7.6 LangGraph 状态

```python
class TextWorkflowState(TypedDict):
    schema_version: str
    run_id: str
    novel_id: str
    chunk_ids: list[str]
    current_chunk_ordinal: int
    completed_step_keys: list[str]
    pending_review_ids: list[str]
    error_codes: list[str]
    status: str
```

State 中不保存原文全文、数据库 Session、Provider Client、MemoryManager 或 Pydantic 大对象。节点使用 `run_id` 从 Repository 加载所需数据。

---

## 8. 角色渲染档案

### 8.1 聚合优先级

```text
用户已确认值
  > 有明确原文证据的有效观察
  > 多证据一致的高置信度推断
  > 经审核的身份原型建议
  > 画风默认值
```

身份原型只提供建议，默认优先补充服装、道具和时代风格。对于脸型、肤色、体型等敏感或个体差异大的特征，不应仅凭职业或身份自动写入确定值。

### 8.2 冲突处理

两条观察只有同时满足以下条件，才进入“真实冲突”候选：

```text
same_character
AND same_field
AND same_timeline
AND temporal_scopes_overlap
AND compatible_reality_status
AND values_are_incompatible
```

冲突不采用简单“新值覆盖旧值”，按以下类别处理：

- 时间变化：少年黑发、老年白发，分别进入不同 `CharacterAppearanceState`，不冲突；
- 场景变化：换装、临时伤势和一次性神情默认不冲突；
- 分支变化：平行时间线中的不同状态分别保存，不互相覆盖；
- 伪装/梦境/传闻：保留但不进入 canonical 默认状态；
- 细化描述：更具体值可替代宽泛值，但保留来源链；
- 持久转变：新增疤痕、伤愈、染发等以事件为边界结束旧状态并开始新状态；
- 真矛盾：同一场景、同一现实层级中“蓝眼睛”和“黑眼睛”等不兼容值标记 `needs_review`；
- 用户选择：形成新档案版本并记录审核人。

“后文没有再提到疤痕”不等于疤痕消失。持久字段延续到明确终止事件；瞬时神情则不得跨场景延续。解析器应维护字段级持续性策略，而不是对所有字段使用同一过期规则。

| 描述组合 | 是否冲突 | 处理 |
|---|---|---|
| 少年黑发；老年白发 | 否 | 两个阶段外观状态 |
| 主线无伤；梦中胸口有伤 | 否 | 不同现实层级 |
| 主时间线蓝衣；分支时间线黑衣 | 否 | 分别绑定时间线 |
| 同一场景先微笑、后皱眉 | 否 | 按场景内顺序保存两个瞬时状态 |
| 内心狂喜；表面不动声色 | 否 | 内外情绪分字段 |
| 同一角色同一场景被明确写为蓝眼和黑眼 | 是 | 标记审核，不自动覆盖 |
| 角色甲黑发；角色乙白发 | 否 | `character_id` 不同 |

### 8.3 目标时点快照解析

图像生成不得只传 `character_id`，必须给出目标语境：

```python
class CharacterRenderRequest(BaseModel):
    character_id: UUID
    timeline_id: UUID
    target_event_id: UUID | None
    target_scene_id: UUID | None
    target_chapter_ordinal: int | None
    expression_override: str | None
    render_overrides: dict[str, JsonValue]
```

解析顺序为：用户本次覆盖 > 场景瞬时状态 > 目标时点有效的阶段外观 > 稳定身份锚点 > 画风默认值。若目标时间缺失且角色存在多个已批准阶段，API 返回 `ambiguous_appearance_state`，由用户选择，不擅自使用最新章节状态。

### 8.4 角色阶段形象集

一本小说中的主角通常存在少年、成年、受伤后、身份揭露、阵营变化或重要换装等可视差异。既然系统已保存这些 `CharacterAppearanceState`，一期不再把输出限制为一个形象，而是将已批准且差异足够大的状态组织为 `CharacterImageSet`。

阶段选择遵循以下规则：

- 一期每个主要角色默认生成 2–4 个关键阶段，数量上限由预算和 PoC 结果冻结；
- 阶段必须来自已批准的 `CharacterAppearanceState`，并绑定明确时间线与事件范围；
- 少年期、成年期、长期伤势、长期伪装或身份转折可成为独立阶段；
- 同一阶段内的短暂表情、单次动作、一次性污渍和普通换装通常只作为场景状态，不自动新增阶段；
- 相邻状态若视觉差异不足，则合并展示，避免为每章或每次描述重复出图；
- 每个阶段独立解析 `ResolvedCharacterSnapshot`、生成候选图并锁定阶段基准图；
- 用户可从阶段基准图中指定一个 `default_representative_image_id`，但该默认图不覆盖其他历史形象；
- 后续新增章节出现新的重要阶段时，新建集合版本，只生成新增或受影响阶段，不重跑全部历史阶段。

```python
class CharacterImageSet(BaseModel):
    id: UUID
    character_id: UUID
    render_profile_version: int
    version: int
    default_representative_image_id: UUID | None
    stage_image_ids: list[UUID]
    selection_policy_version: str
    status: Literal["draft", "partially_approved", "approved"]


class CharacterStageImage(BaseModel):
    id: UUID
    image_set_id: UUID
    appearance_state_id: UUID
    resolved_snapshot_hash: str
    stage_label: str
    representative_event_id: UUID | None
    candidate_image_ids: list[UUID]
    baseline_image_id: UUID | None
    display_order: int
    selection_reason_codes: list[str]
```

**[PoC 决策项 POC-IMAGE-02]** 第 0 阶段必须比较“单一代表形象”和“2–4 个关键阶段形象集”两种产品输出，记录阶段覆盖率、重复形象率、人工选择耗时、单角色成本和用户对角色历程表达的评价。PoC 只决定默认阶段数、差异阈值和预算上限，不改变底层保存全部历史观察与阶段状态的原则。

### 8.5 身份原型

一期原型为只读、版本化、人工审核的 JSON 资源。原型字段必须带：

```json
{
  "value": "monk robe",
  "confidence": 0.7,
  "allowed_fields": ["clothing.style", "clothing.accessories"],
  "rationale": "visual convention, not textual fact"
}
```

二期实现在线编辑、LLM 生成、灰度发布与回滚。自动生成的原型必须先处于 `draft`，不能直接成为活跃版本。

---

## 9. 图像生成与一致性评测

### 9.1 一期工作流策略

一期先完成技术 PoC，再选择并冻结一套组合。优先验证：

```text
SDXL-compatible checkpoint
  + InstantID（锁定基准图后）
  + 对应 SDXL 的姿态/结构控制节点
  + 固定 ComfyUI 与 custom node commits
```

**[PoC 决策项 POC-IMAGE-01]** 一期只会冻结其中一套完整组合。PoC 使用同一批角色、阶段和场景，比较身份、阶段属性、Prompt 遵循、失败率、时延、显存或费用，并同时审查完整资产许可证。若 FLUX + PuLID-FLUX 更合适，可以整体替换 SDXL + InstantID；不得跨模型族随意拼接节点。

一期生成顺序：

1. 从已批准的全部 `CharacterAppearanceState` 中提出关键阶段候选，人工确认一期需要生成的 2–4 个阶段；
2. 为每个阶段用 `CharacterRenderRequest` 在目标时间线、事件或场景解析独立的 `ResolvedCharacterSnapshot`；
3. 每个阶段从已批准快照生成 4–8 张候选正面肖像；
4. 自动质量筛选后由用户为每个阶段选择阶段基准图；
5. 将所有阶段基准图组织为 `CharacterImageSet`，并选定一个默认代表形象；
6. 默认只基于代表形象生成一张角色设定图；其他阶段设定图按用户选择和预算生成；
7. 保存工作流、模型、Prompt、seed、输入快照、阶段归属和远程请求 ID 的完整快照。

一期支持“一个角色多个历史阶段形象”，但不做每章节、每次换装、每个表情的穷举生成。自动四格切分、同阶段跨姿势量产和 LoRA 进入二期。

### 9.2 WorkflowProfile

```python
class WorkflowProfile(BaseModel):
    id: str
    version: str
    base_model_family: Literal["sdxl", "flux", "other"]
    ui_workflow_file: str
    ui_workflow_sha256: str
    api_workflow_file: str
    api_workflow_sha256: str
    parameter_binding_schema_version: str
    comfyui_commit: str
    comfyui_frontend_version: str
    custom_nodes: list[CustomNodeAsset]
    python_lock_sha256: str
    container_image_digest: str
    model_assets: list[ModelAsset]
    supported_modes: set[str]
    input_schema_version: str
    output_schema_version: str
    evaluator_bundle_version: str
```

工作流注册时运行契约测试，校验 UI JSON 与实际提交的 API JSON、参数绑定、节点、输入端口、模型文件、容器环境和输出结构。运行时禁止直接修改原始模板，必须深拷贝后填参。**[P0]** 每个模型、身份权重、基础 checkpoint、VAE 和 custom node 必须保存来源 URL、版本/commit、SHA-256 与许可证标识；许可证不明确的资产只能用于隔离 PoC，不能进入生产 Profile。

### 9.3 多指标质量评测

CLIP-I 只作为辅助主体相似度，不能单独决定“锁定角色”。建议组合：

| 维度 | 指标示例 | 作用 |
|---|---|---|
| 人脸身份 | ArcFace/InsightFace cosine | 有清晰人脸时评估身份保持 |
| 主体相似 | DINO/CLIP-I，先做主体裁剪 | 非写实或全身场景的辅助指标 |
| 属性一致 | 视觉问答/分类器/人工规则 | 发色、服装、疤痕、配色等 |
| 状态一致 | VLM + 规则 | 年龄阶段、伤势、伪装和目标神情 |
| 图像质量 | 人脸检测、模糊、畸变、重复人物 | 排除明显坏图 |
| Prompt 遵循 | 图文相似或 VLM 审核 | 确认目标描述被体现 |
| 人工确认 | 用户选择 | 最终锁定依据 |

所有阈值必须在项目自己的评测集上标定。配置中保存评测器版本和阈值集版本，不直接把 `0.85` 当作跨模型通用标准。

### 9.4 图像产物

每个生成结果至少保存：

- `artifact_id`、存储 URI、SHA-256、MIME、尺寸；
- `character_id`、RenderProfile 版本、CharacterImageSet 版本、ResolvedCharacterSnapshot 哈希；
- `appearance_state_id`、阶段标签、阶段显示顺序、是否为阶段基准图及是否为默认代表形象；哈希；
- `timeline_id`、目标 event/scene ID、外观状态和神情观察 IDs；
- WorkflowProfile、Prompt 和模型版本；
- seed、完整生成参数、参考图 artifact IDs；
- Provider request ID、耗时和费用快照；
- 各评测分数、评测器版本和人工决策。

---

## 10. Agent 增强架构

### 10.1 定位与边界

本项目采用“Agent 增强的可恢复工作流”，而不是全自主多 Agent 系统：

```text
确定性 Workflow Orchestrator
  ├── Extraction Agent              块级事实提取
  ├── Entity Resolution Agent       实体、别名和共指裁决
  ├── Visual Director Agent         生成视觉方案
  ├── Multimodal Critic Agent       审核候选图
  └── Review Agent                  复杂证据与冲突审计
```

Orchestrator 决定何时调用哪个 Agent、是否并行、何时停止以及是否转人工。专项 Agent 不互相自由对话，也不能绕过 Orchestrator 调用另一个 Agent。跨 Agent 传递的是经过 Schema 校验的结构化产物和证据 ID，而不是完整聊天历史。

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
max_image_regenerations = 2
deadline_seconds = 180
```

每个 AgentSpec 可以更严格，但不能在运行时自行放宽。达到轮次、费用、时间或重试上限时返回结构化 `AgentLimitReached`，不得用“继续思考”绕过限制。

### 10.12 人工审批与可恢复中断

Agent 需要审批时返回序列化的 `ApprovalRequest`，LangGraph 使用 `interrupt()` 暂停。审批内容包括：

- 建议执行的动作及影响范围；
- 支撑和反对证据；
- 预计额外费用；
- 可选操作：批准、拒绝、修改、延后；
- 审批过期时间和恢复令牌。

恢复时节点会从开头重新执行，因此 `interrupt()` 前的所有副作用必须幂等，最好将中断放在副作用之前。审批结果写入业务数据库，LangGraph checkpoint 只保存审批 ID。

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
- 强类型工具、ContextPacket、ModelRouter 和有界反思；
- LangGraph 人工中断、Agent 轨迹记录和离线轨迹评测；
- Provider 不支持工具调用时的结构化输出降级。

二期实现：

- 动态 Tool Search 和更细粒度 Agent/工具版本灰度；
- Programmatic Tool Calling，用于只读的过滤、聚合、去重和批量查询；
- 可独立拆分任务的并行子 Agent 与交叉审查；
- MCP 客户端接入外部设定库、素材库和知识库；
- A2A 与独立世界观、3D 或游戏资产 Agent 协作；
- 在线 Agent Prompt、工具权限和轨迹评测管理。

Programmatic Tool Calling 和多 Agent 属于 Provider 特定或仍在演进的能力，必须通过 `LLMCapabilities` 探测并提供普通 Tool Calling/工作流降级路径。MCP 只用于跨进程或第三方扩展，不把内部 Repository 无意义地协议化；A2A 只在真正存在独立 Agent 系统时引入。

---

## 11. 任务系统与断点恢复

### 11.1 一期数据库任务队列

一期使用 `pipeline_runs` 和 `pipeline_steps` 作为 durable queue，由单 Worker 原子领取任务：

1. API 在事务内创建 Run 和初始 Step，返回 run ID；
2. Worker 使用条件更新领取 `queued/retry_scheduled` 任务；
3. 设置 `lease_owner`、`lease_expires_at` 和心跳；
4. 每个步骤开始前检查是否已有成功结果；
5. 外部请求提交前保存幂等记录，提交后立即保存 request ID；
6. Worker 崩溃后，租约过期任务可被重新领取；
7. 已提交的外部任务优先查询状态，不盲目再次提交。

### 11.2 重试策略

| 错误 | 策略 |
|---|---|
| 网络超时且未知是否提交 | 先按幂等键或 request ID 查询 |
| 429/限流 | 指数退避 + jitter，尊重 Retry-After |
| Provider 5xx | 有上限重试，记录每次尝试 |
| JSON 校验失败 | 一次本地提取/修复，再一次受限模型修复 |
| 内容安全拒绝 | 不自动重试，进入人工处理 |
| 参数/工作流错误 | 立即失败，不消耗重复费用 |
| 取消请求 | 在安全检查点停止；已提交远程任务尽量取消或等待回收 |

### 11.3 并发和 Session

- 每个 Worker 任务拥有独立 `AsyncSession`；
- `asyncio.gather()` 中每个并发分支创建自己的 Session；
- 不在网络等待期间保持数据库事务；
- SQLite 一期只允许单写 Worker，并设置 WAL 和 busy timeout；
- 图像候选可以由 Provider 端并发，但本地状态更新串行提交。

### 11.4 二期升级

当需要多 Worker、优先级、定时任务或高吞吐时，迁移至 PostgreSQL + Redis 队列，并选用 Dramatiq/Celery 等成熟执行器。应用层只依赖 `TaskDispatcher` 端口，不改领域逻辑。

---

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
GET    /api/v1/agent-runs/{agent_run_id}        查询轨迹摘要和工具调用
POST   /api/v1/approvals/{approval_id}/resolve  批准、拒绝或修改待审批动作

GET    /api/v1/novels/{novel_id}/characters
GET    /api/v1/characters/{character_id}/observations
GET    /api/v1/characters/{character_id}/expressions
GET    /api/v1/characters/{character_id}/appearance-states
GET    /api/v1/characters/{character_id}/snapshot  按timeline/event/scene解析
GET    /api/v1/characters/{character_id}/render-profile
PUT    /api/v1/characters/{character_id}/render-profile
POST   /api/v1/characters/{character_id}/approve
POST   /api/v1/characters/merge
POST   /api/v1/characters/{character_id}/split

POST   /api/v1/characters/{character_id}/image-runs
GET    /api/v1/characters/{character_id}/images
POST   /api/v1/images/{image_id}/select-reference

GET    /health/live
GET    /health/ready
```

### 12.3 二期端点

二期增加 `/prompts`、`/agents`、`/tools`、`/prototypes`、`/loras`、`/models3d`、批量生成、关系图谱与管理审计端点。未启用的二期模块不在一期注册返回空列表的假接口；通过 `/capabilities` 明确告知当前已启用能力及 Agent/Tool Calling/MCP/A2A 支持情况。

---

## 13. Provider 与工作流版本管理

### 13.1 LLM Provider 接口

```python
class LLMProvider(Protocol):
    async def generate_structured(
        self,
        *,
        messages: Sequence[Message],
        output_schema: type[BaseModel],
        request_options: LLMRequestOptions,
    ) -> StructuredLLMResult: ...

    async def count_tokens(self, messages: Sequence[Message]) -> int: ...
    async def get_capabilities(self) -> LLMCapabilities: ...
    async def get_pricing(self) -> PricingSnapshot | None: ...

    async def run_agent(
        self,
        *,
        agent_spec: AgentSpec,
        context: AgentContextPacket,
        tools: Sequence[BoundTool],
    ) -> AgentProviderResult: ...
```

返回值必须包含 usage、model revision、request ID、finish reason、工具调用关联信息和原始响应哈希。业务层不直接接触厂商 SDK 对象。Provider 的 Agent Runtime 只负责适配厂商响应循环，权限、预算、审批和最终写入仍由项目自己的 Agent Runtime 控制。

### 13.2 图像 Provider 接口

```python
class ImageGenerator(Protocol):
    async def submit(self, request: ImageGenerationRequest) -> ExternalJob: ...
    async def get_status(self, external_job_id: str) -> ExternalJobStatus: ...
    async def cancel(self, external_job_id: str) -> bool: ...
    async def fetch_result(self, external_job_id: str) -> ImageGenerationResult: ...
    async def estimate_cost(self, request: ImageGenerationRequest) -> CostEstimate | None: ...
```

提交与查询分开，才能在 Worker 重启后恢复远程任务。

### 13.3 Prompt 与 Agent 规格管理

一期：

- Prompt 存放在 `prompts/v1/`；
- `registry.yaml` 保存名称、版本、输入变量和内容哈希；
- 启动时校验占位符与 Schema；
- 每次调用保存实际 Prompt 版本和内容哈希。
- AgentSpec 存放在 `agent_specs/v1/`，工具白名单引用 ToolSpec 版本；
- AgentSpec 必须通过静态校验：输出 Schema 存在、工具权限闭合、预算和轮次上限有效。

二期：

- 文件作为种子，数据库保存草稿/已发布版本；
- 发布操作是事务性的，不只依赖 `is_active` 布尔值；
- 支持草稿、审核、发布、回滚和灰度；
- 缓存使用版本号失效，支持多进程同步；
- `max(version)+1` 由数据库锁或序列保障；
- 管理操作写入审计日志。
- Agent、Prompt 和工具权限作为一个可发布配置包灰度和回滚，避免只回滚 Prompt 却保留不兼容工具集合。

### 13.4 Prompt 缓存与高级调用能力

静态系统指令、输出 Schema 和稳定工具定义适合作为可缓存前缀。`model_calls` 记录 `cache_read_tokens`、`cache_write_tokens`、缓存键和 TTL 快照，用实际命中率判断收益。

Provider 能力声明可增加：

```python
class AgentCapabilities(BaseModel):
    direct_tool_calling: bool
    parallel_tool_calling: bool
    programmatic_tool_calling: bool
    tool_search: bool
    prompt_caching: bool
    explicit_prompt_caching: bool
    persisted_reasoning: bool
    multimodal_input: bool
    remote_mcp: bool
```

一期只要求 Direct Tool Calling 或单次 Structured Output。Programmatic Tool Calling 只允许调用只读、低风险、返回结构稳定的工具，用于过滤、连接、排序、去重和聚合；需要人工批准、保留原始引用或每个结果都会改变下一步判断时，继续使用普通工具调用。不得把特定 Provider 的 beta 能力写成业务正确性的前提。

---

## 14. 配置、安全与数据治理

### 14.1 配置示例

```ini
APP_ENV=development
LOG_LEVEL=INFO

DATABASE_URL=sqlite+aiosqlite:///./data/app.db
ARTIFACT_STORE=local
ARTIFACT_LOCAL_ROOT=./data/artifacts

LLM_PROVIDER=deepseek
LLM_API_KEY=
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=

IMAGE_PROVIDER=fal
FAL_KEY=
IMAGE_WORKFLOW_PROFILE=sdxl_instantid_v1

MAX_CHUNK_INPUT_TOKENS=10000
MAX_CONCURRENT_LLM_CALLS=3
MAX_TASK_ATTEMPTS=3
WORKER_LEASE_SECONDS=120

AGENT_RUNTIME_ENABLED=true
AGENT_MAX_TURNS_DEFAULT=3
AGENT_MAX_TOOL_CALLS_DEFAULT=12
AGENT_MAX_REFLECTION_ROUNDS=1
AGENT_MAX_COST_DEFAULT=
AGENT_TOOL_WRITE_POLICY=approval_required

AUTH_MODE=api_key
ADMIN_API_KEY=
```

敏感值只通过环境变量或 secret manager 注入，不写入日志、数据库快照或 `.env.example`。

### 14.2 文件与路径安全

- 上传限制大小和文件类型；文件名不参与真实存储路径；
- 产物使用 UUID/哈希路径，防止目录穿越；
- 下载远程文件时限制协议、域名、大小、超时和 MIME；
- 校验图像解码，拒绝解压炸弹；
- 本地存储接口与 S3 兼容对象存储接口保持一致。

### 14.3 数据治理

小说正文可能受版权保护，且可能包含个人或敏感信息。产品必须明确：

- 用户确认拥有处理权限；
- 哪些内容会发送到哪个云端 Provider；
- Provider 的数据保留和训练使用政策；
- 本地与云端产物保留周期；
- 删除小说时如何级联删除或匿名化观察、调用日志和产物；
- 日志只保存必要摘要，不记录完整正文和密钥。
- Agent 轨迹不保存隐藏思维链，只保存输入上下文清单、可见输出、工具调用、决策依据和使用量。

### 14.4 认证与权限

一期至少使用 API Key 区分普通调用与管理操作。二期增加用户、项目、RBAC、审计事件和配额。Prompt、原型、Provider、删除和批量生成均属于管理权限。

Agent 工具权限按 `read/propose/execute/admin` 分级。模型永远不能通过 Prompt 自行获得更高权限；运行时只绑定 AgentSpec 白名单和当前用户权限的交集。外部 MCP/A2A 返回内容视为不可信数据，不能把其中的指令提升为系统指令。

---

## 15. 测试与验收

### 15.1 测试分层

| 层级 | 内容 |
|---|---|
| 单元测试 | 分块、偏移映射、时间作用域、快照解析、聚合、冲突、状态机、成本公式 |
| 集成测试 | AsyncSession、Alembic、Repository、任务领取与租约 |
| Provider 契约测试 | mock 响应、超时、429、5xx、异步远程任务恢复 |
| Prompt 黄金测试 | 固定片段与期望结构；允许语义容差但不允许证据错位 |
| Agent 工具契约 | 工具选择、参数、权限、错误处理、幂等和审批行为 |
| Agent 轨迹评测 | 结果正确性、证据、重复调用、越权、停止条件和成本 |
| Agent 对抗测试 | Prompt 注入、恶意工具输出、上下文污染和权限提升尝试 |
| 图像工作流契约 | 节点、模型资产、输入输出 Schema、最小生成 smoke test |
| 故障恢复 | Worker 在提交前/后、保存前/后崩溃，确保不重复收费 |
| E2E | 上传→提取→审核→生成→选择基准图 |

### 15.2 黄金评测集

一期建立 3–5 部合法可用小说片段的评测集，覆盖：

- 古风、现代、玄幻等不同文本风格；
- 别名、绰号、称谓、同名角色；
- 性别不明确或代词省略；
- 外貌随时间变化、伪装、倒叙、梦境、幻觉和传闻；
- 重生、时间循环和平行时间线中同一角色的不同状态；
- 同一场景中的外显神情、内心情绪、强装镇定和转瞬表情；
- 持久伤疤的出现/痊愈与临时伤势，验证字段级持续性；
- 只出现一次但有关键描写的角色；
- “干净的乞丐”“长发和尚”等反差设定；
- 文本中没有外貌描写的留白角色。

### 15.3 一期验收门槛

门槛由验证集基线校准，第一版建议：

- 章节和文本块可稳定重现，偏移映射正确率 100%；
- 字段证据定位准确率 ≥ 95%；
- 主要角色实体链接 F1 ≥ 0.90；
- 外貌事实字段 precision ≥ 0.90，recall 作为次要指标；
- 神情可见线索的证据定位准确率 ≥ 90%，内外情绪混淆率单独报告；
- 黄金集中的跨时间非冲突案例不得被合并覆盖，目标快照必须绑定正确时间线和阶段；
- 任务故障恢复测试不产生重复外部提交；
- 所有生成图均能追溯到档案、Prompt、模型、工作流和 seed；
- 角色一致性阈值由至少 100 对内部样本标定；
- 最终锁定仍由人工完成，不以单一自动分数替代。
- Agent 工具调用权限违规数为 0，收费/合并/发布动作未经审批执行数为 0；
- Agent 达到轮次、费用或时间上限时能结构化停止，不进入无限循环；
- 轨迹评测集上的工具选择、人工升级和最终输出均达到各 AgentSpec 的发布门槛。

### 15.4 测试预算

测试不以“约 250 行”估算。建议至少将 30%–40% 的一期工程量用于自动测试、评测集、故障注入和脚本。AI 系统的主要风险来自数据与外部服务行为，不是代码能否运行。

---

## 16. 可观测性与成本控制

### 16.1 日志关联字段

每条结构化日志至少包含：

```text
request_id, run_id, step_id, agent_run_id, agent_id, tool_call_id,
novel_id, character_id, provider, model, workflow_profile,
attempt, duration_ms, error_code
```

不记录完整正文、完整 Prompt、API Key 和带签名下载 URL。

### 16.2 关键指标

- 每块输入/输出 token 与有效事实数；
- JSON 校验失败率、修复率、Provider 错误率；
- 实体待人工审核比例；
- 每角色候选图数量、重生成率、人工接受率；
- Worker 队列等待时间、执行时间、租约超时数；
- 每小说、每角色、每成功产物成本；
- 工作流版本的质量与成本对比。
- 每个 Agent 的任务成功率、平均轮次、工具调用数和人工升级率；
- 无效/重复工具调用率、Schema 修复率和达到限制次数；
- Agent 版本的轨迹评分、回归失败数和单位成功任务成本；
- Prompt cache read/write tokens、命中率和净成本收益。

### 16.3 成本公式

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

## 17. 开发计划

以下按 1 名熟悉 Python/LLM 的工程师估算。加入专项 Agent、时态/神情状态模型、轨迹评测和安全测试后，一期预计 10–12 周（含第 0 阶段 PoC 与缓冲）；若同时建设完整前端，应另计 UI 工期。

### 17.1 第 0 阶段：技术 PoC（1 周）

以下内容均为 **PoC 决策项**。PoC 结束时必须把结论、原始样本、指标、成本和选择理由写入决策记录；在此之前不得将候选方案描述为生产默认值。

| ID | 待决定问题 | 对照方案 | 决策输出 |
|---|---|---|---|
| `POC-TEXT-01` | 中文小说分块参数 | 场景 1K–3K、段落 2K–4K、大块 6K–12K、小块双 pass、邻块上下文 | 分块策略、重叠、最大上下文和每正确字段成本 |
| `POC-AGENT-01` | Extraction Agent 是否值得保留 | 单次结构化调用 vs Agent + 只读工具 | 是否启用 Agent、最大轮次、质量与成本门槛 |
| `POC-ENTITY-01` | 实体链接策略 | 规则优先、候选召回 + LLM 提案等至少两种方案 | 候选召回、自动链接阈值和强制人工条件 |
| `POC-TIME-01` | 一期时间线自动化边界 | 主线、回忆、梦境/传闻及复杂分支样本 | 自动支持集、`defer` 条件和污染率上限 |
| `POC-IMAGE-01` | 固定图像工作流 | SDXL + InstantID vs FLUX + PuLID-FLUX 完整组合 | 唯一一期 WorkflowProfile、资产清单和许可证结论 |
| `POC-IMAGE-02` | 单角色输出多少阶段 | 单一代表形象 vs 2–4 个关键阶段形象集 | 默认阶段数、阶段差异阈值、预算和人工审核上限 |
| `POC-WORKFLOW-01` | LangGraph 是否保留 | 普通应用服务 vs LangGraph 外层编排 | 只有人工中断、恢复或条件路由带来明确收益时保留 |
| `POC-EVAL-01` | 图像阈值与评测组合 | 身份、阶段、场景三层指标 + 人工盲评 | 评测器组合、失败样本口径和阈值集版本 |

PoC 样本至少覆盖 3 个代表角色及其 2 个以上可视阶段，并完成以下验证：

- 用代表性文本片段验证块级结构化提取和精确证据对齐；
- 对比至少两种实体链接/别名策略；
- 跑通两套图像候选工作流或对无法运行的候选给出明确阻断原因；
- 比较单一代表形象与阶段形象集的价值、重复率和成本；
- 对比单次结构化调用和 Extraction Agent 的质量、延迟与成本；
- 验证工具调用、ContextPacket、有限轮次、人工中断和外部提交未知状态；
- 输出兼容矩阵、许可证结论、质量基线和真实成本样本。

**退出条件：** P0 数据结构与安全约束已有实现方案，所有 PoC 决策项均形成结论；三个核心命题达到可接受基线。任一生产依赖资产许可证不明确、外部提交无法安全恢复或阶段形象成本超过冻结预算时，不进入对应功能的工程开发。

### 17.2 第 1–2 周：工程基础与任务系统

- `src` 骨架、配置、结构化日志；
- Async SQLAlchemy 与 Alembic；
- novels/documents/chapters/chunks/runs/steps/artifacts 表；
- timelines/story_events/scenes 表与最小时间作用域模型；
- 数据库任务领取、`lease_generation`、取消、重试和 `submission_unknown`；
- 上传、Run 和 SSE API；
- 故障恢复测试骨架。
- AgentSpec、ToolSpec、Agent Runtime、权限和预算守卫骨架；
- agent_runs/turns/tool_calls/decisions/approvals 表及迁移。

### 17.3 第 3–5 周：文本 Agent 与证据模型

- 章节识别、动态分块、偏移映射；
- Extraction Agent 与结构化输出降级；
- Entity Resolution Agent、别名、共指和审批中断；
- `MentionSpan`、`AliasAssertion`、规范化偏移映射和 Grounding 校验；
- FeatureObservation 持久化；
- ExpressionObservation、AppearanceState 与场景/时间线候选提取；
- RenderProfile 聚合、目标时点快照解析、冲突和人工编辑；
- ContextPacket、ModelRouter 和工具契约；
- 黄金集、Agent 轨迹集与精度报告。

### 17.4 第 6–7 周：图像 Agent 与评测

- WorkflowProfile 注册与契约测试；
- fal 提交/查询/下载/恢复；
- 候选肖像、阶段形象集、阶段基准图、默认代表形象和设定图选择；
- Visual Director 与 Multimodal Critic；
- 多指标质量评测和最多一次受控修订；
- 身份层、阶段层、场景神情层的一致性评测；
- 生成快照、费用记录和预算限制。

### 17.5 第 8–10 周：Agent 安全、加固与验收

- 端到端、重试、取消和崩溃恢复；
- 文件安全、认证、数据删除；
- Prompt 注入、恶意工具输出、权限提升和无限循环测试；
- 工具轨迹、人工升级、缓存与模型路由回归评测；
- 3–5 部测试材料跑批；
- 指标阈值标定；
- 部署文档、运维手册和二期接口评审。

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

## 19. 风险与降级策略

| 风险 | 表现 | 降级/缓解 |
|---|---|---|
| LLM 幻觉 | 无原文证据的外貌字段 | 证据必填、precision 优先、人工审核 |
| 别名误合并 | 两个角色被当成一人 | 保留假设、置信度、支持拆分和重算 |
| 时间线误绑定 | 少年、老年、梦境或分支状态相互覆盖 | 叙事顺序与故事顺序分离、作用域候选、复杂案例转人工 |
| 神情语义误读 | 把内心狂喜画成微笑，或让瞬时表情永久化 | 内外情绪分字段、可见线索证据、场景级默认有效期 |
| 长文本成本失控 | 调用数随角色数倍增 | 块级批量提取、相关记忆注入、预算门槛 |
| 工作流不兼容 | 模型或节点无法组合 | 固定兼容矩阵、commit 与契约测试 |
| 单指标误判 | 背景相似导致高 CLIP-I | 主体裁剪、多指标与人工终审 |
| Worker 崩溃 | 重复提交或任务卡死 | 租约、幂等、远程 request ID、恢复测试 |
| SQLite 写锁 | 并发更新失败 | 单写 Worker、短事务；二期 PostgreSQL |
| Provider 价格变化 | 预算不准确 | 动态价格快照、运行前估价和硬预算 |
| 云端数据风险 | 正文或图像泄漏 | 最小发送、明确告知、删除策略、日志脱敏 |
| 图结构升级 | 旧 checkpoint 无法恢复 | State schema version、兼容迁移或显式终止旧 Run |
| Agent 越权 | 自行提交收费/写入/删除动作 | 工具白名单、权限交集、审批门槛和运行时守卫 |
| Prompt 注入 | 小说文本或工具结果包含恶意指令 | 数据与指令分层、内容标记、工具结果不可信处理 |
| Agent 循环 | 重复查询、反思或重新生成 | 最大轮次/工具数/费用/时间和结构化停止 |
| 上下文污染 | 摘要错误逐轮放大 | 原始证据优先、来源 ID、上下文哈希和定期重建 |
| 多 Agent 分歧 | 多个建议互相冲突 | Orchestrator 按规则聚合，高风险转人工，不自由辩论 |
| Provider 特性锁定 | 高级 Agent 能力无法迁移 | Capabilities 探测、普通 Tool Calling/Structured Output 降级 |
| 轨迹泄露 | 保存敏感输入或隐藏推理 | 仅保存可见输出、摘要、哈希和工具事件，严格脱敏 |

---

## 附录 A：关键设计决策

| 决策 | 选择 | 原因 |
|---|---|---|
| 一期目标 | 识别全书候选角色，精细处理 3–5 个主要角色；每个主要角色默认输出 2–4 个关键阶段形象 | 控制角色数量与生成成本，同时保留主角历史形象价值 |
| 文本调用粒度 | 每块一次批量提取 | 避免 `块数 × 角色数` 爆炸 |
| 事实模型 | Observation + Identity/Appearance/Scene 三层状态 + RenderProfile | 支持证据、多时间线、瞬时神情和人工选择 |
| 渲染输入 | 目标时点 ResolvedCharacterSnapshot | 防止默认使用错误年龄、服装、伤势或神情 |
| 冲突判定 | 同角色/字段/时间线/重叠区间/现实层级联合判断 | 时间变化和叙事视角差异不应误报为事实矛盾 |
| 编排 | LangGraph 只做外层可恢复工作流 | 不侵入领域与任务系统 |
| 长任务 | 独立 Worker + durable Run/Step | HTTP 解耦、可恢复、可取消 |
| ORM | 全异步 SQLAlchemy | 与 FastAPI/外部异步调用保持一致，不混用 Session |
| 数据库 | 一期 SQLite，二期 PostgreSQL | 一期低运维，明确并发边界 |
| 图像方案 | 一期固定一套兼容工作流；一个角色形成多个阶段基准图和一个默认代表形象 | 先保证可复现，并避免把完整角色历程压缩成单一形象 |
| 质量评测 | 多指标 + 人工终审 | CLIP-I 不足以判断身份一致性 |
| Prompt | 一期 Git 文件，二期在线发布 | 避免过早建设管理平台 |
| 3D/LoRA | 二期正式实现 | 保留完整路线但不阻塞一期验证 |
| 价格 | 动态快照，不在文档硬编码 | 模型和平台价格会变化 |
| Agent 定位 | 专项 Agent + 确定性 Orchestrator | 保留语义能力，同时控制副作用和成本 |
| Agent 通信 | Schema 产物 + 证据 ID | 不共享完整聊天历史，不自由群聊 |
| Agent 工具 | 强类型、最小权限、默认只读 | 降低越权、注入和不可恢复副作用 |
| Agent 循环 | 有界反思，失败转人工 | 防止无限调用和费用失控 |
| 高级 Agent 能力 | 二期按能力探测启用 | PTC、Tool Search、MCP、A2A 不作为一期硬依赖 |

## 附录 B：参考资料

- [OpenAI Model Guidance：Tool Calling、Prompt Caching 与 Multi-agent](https://developers.openai.com/api/docs/guides/latest-model)
- [LangGraph Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [LangGraph Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
- [LangGraph Fault Tolerance](https://docs.langchain.com/oss/python/langgraph/fault-tolerance)
- [SQLAlchemy AsyncIO](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [SQLAlchemy Session 并发模型](https://docs.sqlalchemy.org/en/20/orm/session_basics.html)
- [FastAPI Background Tasks Caveat](https://fastapi.tiangolo.com/tutorial/background-tasks/)
- [DeepSeek Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing)
- [fal Model API Pricing](https://fal.ai/docs/documentation/model-apis/pricing)
- [fal Serverless Pricing](https://fal.ai/docs/documentation/serverless/pricing)
- [fal ComfyUI Deployment](https://fal.ai/docs/examples/image-generation/deploy-comfyui-server)
- [InstantID](https://github.com/InstantID/InstantID)
- [PuLID](https://github.com/ToTheBeginning/PuLID)
- [Model Context Protocol Specification](https://modelcontextprotocol.io/specification/2025-06-18/server/index)
- [Agent2Agent Protocol Specification](https://a2a-protocol.org/v0.3.0/specification/)
