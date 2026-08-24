# 代码导航：一个功能应该去哪里找

> [← 当前实现状态](00-current-status.md) · [文档索引](README.md) · [架构蓝图 →](02-architecture-and-tech-stack.md)
>
> 文档版本：2.9 · 修订日期：2026-08-24

## 先记住这条调用链

```text
HTTP 请求
  → api/routes：解析协议、权限和返回码
  → application/services：执行业务用例和事务边界
  → domain：实体、值对象和确定性规则
  → infrastructure：数据库、文件、LLM 和外部 Provider
  → workers：异步领取并推进 PipelineStep
  → tests：验证业务结果、幂等、恢复和安全边界
```

路由不应直接实现复杂业务规则；Agent 不应直接拿数据库 Session；Worker 不应绕过 Step 状态机写入终态。

## 目录地图

| 目录 | 负责什么 | 不应该放什么 |
|---|---|---|
| [`api/`](../src/novel_character_generator/api) | FastAPI 装配、认证、错误格式、Metrics 和路由 | 长事务、复杂聚合、Provider 细节 |
| [`web/`](../src/novel_character_generator/web) | 无框架工作台 HTML/CSS/JS；只调用公开 API | 业务真值、密钥持久化、绕过 capability 的假功能 |
| [`application/services/`](../src/novel_character_generator/application/services) | 业务用例、事务、权限后的确定性编排 | HTTP 对象、模型厂商 SDK |
| [`application/ports/`](../src/novel_character_generator/application/ports) | Artifact、Extraction、AgentRuntime 等抽象协议 | 具体 Provider 配置 |
| [`domain/entities/`](../src/novel_character_generator/domain/entities) | Pydantic 领域模型和状态约束 | SQLAlchemy 查询、网络调用 |
| [`domain/policies/`](../src/novel_character_generator/domain/policies) | 文本处理、证据校验等纯规则 | Session 和副作用 |
| [`domain/value_objects/`](../src/novel_character_generator/domain/value_objects) | 时间作用域等不可变值对象 | API 路由逻辑 |
| [`infrastructure/db/`](../src/novel_character_generator/infrastructure/db) | ORM、Session、Repository、数据库持久化 | 用户流程编排 |
| [`infrastructure/llm/`](../src/novel_character_generator/infrastructure/llm) | Mock 与 OpenAI-compatible 抽取 Provider | 角色合并、审批等业务决策 |
| [`infrastructure/storage/`](../src/novel_character_generator/infrastructure/storage) | 本地产物存储 | 业务状态机 |
| [`agents/`](../src/novel_character_generator/agents) | 有界 AgentRuntime、工具执行与结构化结果 | 无限制循环或直接数据库写入 |
| [`workers/`](../src/novel_character_generator/workers) | 长任务领取、租约、checkpoint、重试和步骤处理 | 新的业务真值体系 |
| [`tests/`](../tests) | 单元、集成、恢复、安全和契约验证 | 只验证 happy path 的脆弱脚本 |
| [`migrations/`](../migrations) | Alembic Schema 历史 | 运行时自动建表逻辑 |

## 功能到代码的映射

| 功能 | API 入口 | 核心实现 | 数据/测试 |
|---|---|---|---|
| 应用启动与路由注册 | [`api/app.py`](../src/novel_character_generator/api/app.py) | `create_app()` | [`test_health.py`](../tests/integration/test_health.py) |
| 可视化工作台 | [`routes/ui.py`](../src/novel_character_generator/api/routes/ui.py) | [`web/index.html`](../src/novel_character_generator/web/index.html)、[`web/app.js`](../src/novel_character_generator/web/app.js) | `test_ui_shell_and_static_assets_are_served_without_api_auth` |
| 配置和生产校验 | — | [`settings.py`](../src/novel_character_generator/settings.py) | [`test_settings.py`](../tests/unit/test_settings.py) |
| 小说上传与版本 | [`routes/novels.py`](../src/novel_character_generator/api/routes/novels.py) | [`IngestionService`](../src/novel_character_generator/application/services/ingestion_service.py) | [`document.py`](../src/novel_character_generator/domain/entities/document.py)、[`test_document_versions.py`](../tests/integration/test_document_versions.py) |
| 章节识别和分块 | 由 Run 触发 | [`text_processing.py`](../src/novel_character_generator/domain/policies/text_processing.py)、[`handlers/ingestion.py`](../src/novel_character_generator/workers/handlers/ingestion.py) | [`test_text_processing.py`](../tests/unit/domain/test_text_processing.py) |
| 角色提取 | 由分析 Run 触发 | [`handlers/extraction.py`](../src/novel_character_generator/workers/handlers/extraction.py)、[`repositories/extraction.py`](../src/novel_character_generator/infrastructure/db/repositories/extraction.py) | [`test_extraction_slice.py`](../tests/integration/test_extraction_slice.py) |
| LLM 抽取适配 | — | [`openai_compatible.py`](../src/novel_character_generator/infrastructure/llm/openai_compatible.py)、[`mock.py`](../src/novel_character_generator/infrastructure/llm/mock.py) | 对应 `tests/unit/test_*_extraction.py` |
| Run、SSE、取消、重试 | [`routes/runs.py`](../src/novel_character_generator/api/routes/runs.py) | [`RunService`](../src/novel_character_generator/application/services/run_service.py)、[`run_events.py`](../src/novel_character_generator/infrastructure/db/repositories/run_events.py) | [`test_run_events_and_external_operations.py`](../tests/integration/test_run_events_and_external_operations.py) |
| Worker 租约和 fencing | — | [`task_claim.py`](../src/novel_character_generator/workers/task_claim.py)、[`workers/main.py`](../src/novel_character_generator/workers/main.py) | [`test_task_recovery.py`](../tests/integration/test_task_recovery.py) |
| 时间线、事件、场景 | [`routes/story.py`](../src/novel_character_generator/api/routes/story.py) | [`StoryService`](../src/novel_character_generator/application/services/story_service.py) | [`story.py`](../src/novel_character_generator/domain/entities/story.py)、[`test_story_temporal_api.py`](../tests/integration/test_story_temporal_api.py) |
| 角色查询、合并和拆分 | [`routes/characters.py`](../src/novel_character_generator/api/routes/characters.py) | [`CharacterEntityService`](../src/novel_character_generator/application/services/character_entity_service.py) | [`test_character_entity_api.py`](../tests/integration/test_character_entity_api.py) |
| 外观冲突、档案和快照 | [`routes/characters.py`](../src/novel_character_generator/api/routes/characters.py) | [`AppearanceService`](../src/novel_character_generator/application/services/appearance_service.py) | [`character.py`](../src/novel_character_generator/domain/entities/character.py)、[`test_character_appearance_api.py`](../tests/integration/test_character_appearance_api.py) |
| 人工审批 | [`routes/approvals.py`](../src/novel_character_generator/api/routes/approvals.py) | [`ApprovalService`](../src/novel_character_generator/application/services/approval_service.py) | [`test_approval_and_agent_api.py`](../tests/integration/test_approval_and_agent_api.py) |
| AgentRuntime | [`routes/agent_runs.py`](../src/novel_character_generator/api/routes/agent_runs.py) | [`structured_runtime.py`](../src/novel_character_generator/agents/structured_runtime.py)、[`AgentExecutionService`](../src/novel_character_generator/application/services/agent_execution_service.py) | [`test_structured_agent_runtime.py`](../tests/unit/test_structured_agent_runtime.py) |
| 评测数据层 | 暂无公开执行 API | [`repositories/evaluation.py`](../src/novel_character_generator/infrastructure/db/repositories/evaluation.py) | [`evaluation.py`](../src/novel_character_generator/domain/entities/evaluation.py)、[`test_evaluation_repository.py`](../tests/integration/test_evaluation_repository.py) |
| 图像生成 | 尚无 | 只有 [`domain/entities/image.py`](../src/novel_character_generator/domain/entities/image.py) 和 ORM 预留 | 设计见 [`06-image-generation-and-drift-control.md`](06-image-generation-and-drift-control.md) |
| 日志检查 | 尚无 | 需要新增 observability 事件层和 checker | 设计见 [`13-observability-logging-and-cost.md`](13-observability-logging-and-cost.md) |

## 新开发者推荐阅读顺序

### 第一步：看应用如何启动

读 [`settings.py`](../src/novel_character_generator/settings.py) 和 [`api/app.py`](../src/novel_character_generator/api/app.py)。先知道数据库、文件存储、LLM、权限和 Agent 开关从哪里来，以及哪些 Router 被注册。

### 第二步：跟一次上传请求

从 [`routes/novels.py`](../src/novel_character_generator/api/routes/novels.py) 进入 [`IngestionService`](../src/novel_character_generator/application/services/ingestion_service.py)，观察如何保存源文件、创建版本和 PipelineRun。

### 第三步：跟 Worker 推进两个步骤

读 [`workers/main.py`](../src/novel_character_generator/workers/main.py)，再读 [`task_claim.py`](../src/novel_character_generator/workers/task_claim.py)。当前 Worker 只支持 `normalize_and_chunk` 和 `extract_characters` 两种 step key。

### 第四步：看证据如何落库

读 [`handlers/extraction.py`](../src/novel_character_generator/workers/handlers/extraction.py)、[`ports/extraction.py`](../src/novel_character_generator/application/ports/extraction.py)和 [`repositories/extraction.py`](../src/novel_character_generator/infrastructure/db/repositories/extraction.py)。重点理解 offset、source version、fingerprint 和幂等。

### 第五步：看人工修正如何工作

读 [`StoryService`](../src/novel_character_generator/application/services/story_service.py)、[`CharacterEntityService`](../src/novel_character_generator/application/services/character_entity_service.py)和 [`AppearanceService`](../src/novel_character_generator/application/services/appearance_service.py)。这里集中体现 revision、冲突、审计和目标时点解析。

### 第六步：最后再看 Agent

读 [`structured_runtime.py`](../src/novel_character_generator/agents/structured_runtime.py)。AgentRuntime 是可插拔执行器，不是整个系统的主状态机；Run/Step、审批和外部副作用仍由确定性应用层控制。

## 修改某类功能时通常要改哪些文件

### 增加一个 API

1. 在 `api/routes` 定义请求/响应和权限。
2. 在 `application/services` 实现用例和事务。
3. 必要时扩展 domain 模型、ORM 和 migration。
4. 在 `api/app.py` 注册新 Router。
5. 增加集成测试，并检查 OpenAPI。

### 增加一个 PipelineStep

1. 定义稳定 `step_key` 和允许状态转换。
2. 创建幂等的 Worker handler。
3. 在 `workers/main.py` 注册分发。
4. 所有写入携带 `lease_generation`。
5. 增加提交前/后、保存前/后的故障恢复测试。

### 增加一个 Provider

1. 先在 `application/ports` 定义或扩展协议。
2. 在 `infrastructure` 实现 Adapter。
3. 保存 Provider/模型/请求版本与幂等信息。
4. 补 mock、超时、限流、未知提交和契约测试。
5. 不把厂商 SDK 类型泄漏到 domain 和路由。

### 增加一个领域字段

1. 判断它是原文 Observation、阶段状态、渲染决策还是生成产物。
2. 更新领域模型和 ORM。
3. 添加 Alembic migration。
4. 更新 Repository、API Schema 和版本兼容。
5. 增加正向、冲突、失效和历史重放测试。

### 增加关键日志

1. 在状态转换成功边界输出稳定 `event_name`，不记录正文或完整 Prompt。
2. 携带 run/step/attempt、业务记录 ID、版本和哈希。
3. 对收费提交、漂移门禁、审批和锁定同时保留业务表真值。
4. 给 `log-check` 增加正常和失败夹具。

## 复杂度热点

这些文件不是入门第一站，修改前先读相关测试和技术文档：

| 文件 | 为什么复杂 |
|---|---|
| [`infrastructure/db/orm.py`](../src/novel_character_generator/infrastructure/db/orm.py) | 集中定义大量表、外键和状态字段，修改会影响迁移与多个服务 |
| [`character_entity_service.py`](../src/novel_character_generator/application/services/character_entity_service.py) | 合并/拆分会重绑大量关联记录，并处理受保护图像资产和审计 |
| [`appearance_service.py`](../src/novel_character_generator/application/services/appearance_service.py) | 同时处理时间范围、优先级、冲突、人工覆盖和快照解析 |
| [`repositories/extraction.py`](../src/novel_character_generator/infrastructure/db/repositories/extraction.py) | 负责证据落库、幂等、别名、观察和时间候选 |
| [`task_claim.py`](../src/novel_character_generator/workers/task_claim.py) | 包含租约、fencing、重试和原子推进，错误可能导致重复写入 |
| [`structured_runtime.py`](../src/novel_character_generator/agents/structured_runtime.py) | 涉及工具权限、预算、轮次、审批预检和结构化停止原因 |

## 常用验证命令

在项目目录执行：

```powershell
uv run pytest
uv run ruff check .
uv run mypy src
uv run uvicorn novel_character_generator.api.app:app --reload
uv run python -m novel_character_generator.workers.main --once
```

API 启动后访问 `http://127.0.0.1:8000/ui` 使用可视化工作台；OpenAPI 位于 `/docs`。

优先跑与修改最接近的测试，再跑全量测试。涉及 ORM 时必须跑 migration 测试；涉及 Worker 时必须跑恢复与幂等测试；涉及权限或 Agent 工具时必须跑审批和越权测试。

完整安装、迁移、双进程启动、烟雾测试、备份恢复和故障排查见[本地开发与运维手册](16-local-development-and-runbook.md)。

---

[← 当前实现状态](00-current-status.md) · [文档索引](README.md) · [架构蓝图 →](02-architecture-and-tech-stack.md)
