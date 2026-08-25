# 技术文档索引

> 文档版本：3.1 · 修订日期：2026-08-24
>
> 本目录是技术设计的唯一正文来源。第一次接触项目请先读“开始这里”，不要直接从数据模型或 Agent 架构开始。

## 第一次阅读

| 文档 | 先回答什么问题 |
|---|---|
| [开始这里：项目到底做什么](00-start-here.md) | 用户输入什么、系统处理什么、最终交付什么 |
| [当前实现状态](00-current-status.md) | 哪些功能已经能用，哪些部分实现，哪些仍是设计 |
| [代码导航](00-code-navigation.md) | 一个功能对应哪个 API、Service、模型、Worker 和测试 |

## 主题文档

| 文档 | 内容 |
|---|---|
| [项目目标与设计原则](01-project-overview-and-principles.md) | 项目目标、一期/二期范围、证据优先与防漂移基本原则 |
| [架构蓝图与技术栈](02-architecture-and-tech-stack.md) | 逻辑架构、运行拓扑、技术选型和代码骨架 |
| [领域模型与数据库设计](03-domain-data-model.md) | 核心表、证据模型、时间线、神情、外观状态和任务状态机 |
| [文本理解流水线](04-text-understanding-pipeline.md) | 导入分块、原子视觉字段、人生阶段、结构化提取与版本替换 |
| [角色渲染档案](05-character-render-profile.md) | 聚合优先级、冲突处理、目标时点快照、阶段形象集与身份原型 |
| [图像生成与视觉防漂移](06-image-generation-and-drift-control.md) | 工作流、质量评测、生成上下文、漂移审计、门禁与失效传播 |
| [Agent 增强架构](07-agent-architecture.md) | Agent 边界、Runtime、专项 Agent、工具契约、上下文与有界反思 |
| [任务系统与断点恢复](08-task-recovery.md) | 数据库任务队列、幂等重试、租约、并发与恢复策略 |
| [API 规范](09-api-specification.md) | 统一 API 规则、当前已注册端点、尚未注册的一期目标接口和二期边界 |
| [Provider 与工作流版本](10-provider-and-workflow-versioning.md) | LLM/Image Provider、Prompt、AgentSpec、缓存和版本治理 |
| [配置、安全与数据治理](11-security-and-data-governance.md) | 配置校验、文件安全、数据治理、认证与权限 |
| [评测系统与验收门禁](12-evaluation-and-acceptance.md) | 测试分层、数据集、指标、图像盲评、发布门禁和失败回流 |
| [可观测性、日志检查与成本](13-observability-logging-and-cost.md) | Trace、关键日志事件、log-check 输出、指标、告警与成本控制 |
| [一期与二期开发路线图](14-roadmap.md) | PoC、一期实施阶段和二期能力规划 |
| [风险、关键决策与参考资料](15-risks-decisions-and-references.md) | 风险降级矩阵、架构决策记录和参考资料 |

## 实施与交付文档

| 文档 | 内容 |
|---|---|
| [本地开发、部署与运维手册](16-local-development-and-runbook.md) | 安装、迁移、API/Worker 启动、烟雾测试、备份恢复和故障排查 |
| [外观状态聚合实现契约](17-appearance-aggregation-contract.md) | Observation → AppearanceState → RenderProfile 的规则、幂等、事务、日志和验收 |
| [图像生成端到端实现契约](18-image-generation-implementation-contract.md) | Image Run、Step 图、Provider、ExternalOperation、漂移门禁和完成定义 |
| [功能—代码—测试追踪矩阵](19-feature-traceability-matrix.md) | 功能到 API、Service、数据、Worker、日志、测试与状态的映射 |
| [API 调用手册与错误目录](20-api-cookbook-and-error-catalog.md) | 当前真实接口的认证、请求响应、SSE、并发更新和错误码示例 |
| [检索增强的角色视觉精提取实现设计](21-retrieval-augmented-visual-enrichment.md) | 上传后细粒度文本库、SQLite FTS5 + Embedding API + Qdrant Local 混合召回、邻居上下文、视觉精提取与证据回映 |

## 推荐读取路径

- 第一次了解项目：开始这里 → 当前实现状态 → 代码导航。
- 快速理解设计：开始这里 → 01 → 02 → 03 → 06。
- 文本与角色事实：开始这里 → 当前实现状态 → 03 → 04 → 05 → 12。
- 图像生成与防漂移：当前实现状态 → 03 → 05 → 06 → 10 → 12 → 13。
- Agent 与任务恢复：当前实现状态 → 02 → 07 → 08 → 11 → 13。
- API 开发：代码导航 → 02 → 03 → 08 → 09 → 11。
- API 联调：16 → 20 → 09 → 19。
- 角色视觉精提取：04 → 21 → 03 → 05 → 12 → 19。
- 外观聚合实现：当前实现状态 → 17 → 03 → 04 → 05 → 08 → 13 → 19。
- 图像生成实现：当前实现状态 → 18 → 05 → 06 → 08 → 10 → 12 → 13 → 19。
- 运维与排障：16 → 08 → 10 → 11 → 13 → 15。

## 阅读与维护约定

1. 新读者先读三个入口文档；后续优先通过索引选择任务相关主题，不默认全量读取。
2. 每个主题文件保留原技术文档的章节编号，方便历史链接、评审意见和 Git diff 对照。
3. 跨主题设计变更只修改对应主题文件；若职责或文件名发生变化，同时更新本索引。
4. 数据模型、API、评测、日志事件等跨文档契约必须使用稳定名称和版本，并在相关文档间使用相对链接。
5. 发布前检查 Markdown 链接、代码块闭合、章节覆盖和 `git diff --check`。
6. 主题文档描述目标架构时必须显式写“当前状态”；部署实例能力以 `/api/v1/capabilities` 和 OpenAPI 为准。
7. 功能状态变化同时更新当前实现状态、API 规范、追踪矩阵和相应实现契约，不能只改其中一处。
