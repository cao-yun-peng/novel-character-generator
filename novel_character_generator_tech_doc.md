# 小说角色插画与 3D 建模生成器——技术设计文档

> 文档版本：2.9
>
> 修订日期：2026-08-24
>
> 文档状态：已按主题拆分；正文位于 [`novel-character-generator/docs`](novel-character-generator/docs/README.md)。

为避免开发和 Agent 每次读取完整单体文档，本文件只保留兼容入口。技术设计正文以 [技术文档索引](novel-character-generator/docs/README.md) 及其主题文件为唯一来源。

| 文档 | 内容 |
|---|---|
| [开始这里：项目到底做什么](novel-character-generator/docs/00-start-here.md) | 输入、处理流程、最终产物和当前可运行主链 |
| [当前实现状态](novel-character-generator/docs/00-current-status.md) | 已实现、部分实现、仅设计和二期能力边界 |
| [代码导航](novel-character-generator/docs/00-code-navigation.md) | 功能到 API、Service、模型、Worker 和测试的映射 |
| [项目目标与设计原则](novel-character-generator/docs/01-project-overview-and-principles.md) | 项目目标、一期/二期范围、证据优先与防漂移基本原则 |
| [架构蓝图与技术栈](novel-character-generator/docs/02-architecture-and-tech-stack.md) | 逻辑架构、运行拓扑、技术选型和代码骨架 |
| [领域模型与数据库设计](novel-character-generator/docs/03-domain-data-model.md) | 核心表、证据模型、时间线、神情、外观状态和任务状态机 |
| [文本理解流水线](novel-character-generator/docs/04-text-understanding-pipeline.md) | 导入分块、结构化提取、实体链接、时间定位与增量处理 |
| [角色渲染档案](novel-character-generator/docs/05-character-render-profile.md) | 聚合优先级、冲突处理、目标时点快照、阶段形象集与身份原型 |
| [图像生成与视觉防漂移](novel-character-generator/docs/06-image-generation-and-drift-control.md) | 工作流、质量评测、生成上下文、漂移审计、门禁与失效传播 |
| [Agent 增强架构](novel-character-generator/docs/07-agent-architecture.md) | Agent 边界、Runtime、专项 Agent、工具契约、上下文与有界反思 |
| [任务系统与断点恢复](novel-character-generator/docs/08-task-recovery.md) | 数据库任务队列、幂等重试、租约、并发与恢复策略 |
| [API 规范](novel-character-generator/docs/09-api-specification.md) | 当前真实端点、尚未注册的目标接口和二期边界 |
| [Provider 与工作流版本](novel-character-generator/docs/10-provider-and-workflow-versioning.md) | LLM/Image Provider、Prompt、AgentSpec、缓存和版本治理 |
| [配置、安全与数据治理](novel-character-generator/docs/11-security-and-data-governance.md) | 配置校验、文件安全、数据治理、认证与权限 |
| [评测系统与验收门禁](novel-character-generator/docs/12-evaluation-and-acceptance.md) | 测试分层、数据集、指标、图像盲评、发布门禁和失败回流 |
| [可观测性、日志检查与成本](novel-character-generator/docs/13-observability-logging-and-cost.md) | Trace、关键日志事件、log-check 输出、指标、告警与成本控制 |
| [一期与二期开发路线图](novel-character-generator/docs/14-roadmap.md) | PoC、一期实施阶段和二期能力规划 |
| [风险、关键决策与参考资料](novel-character-generator/docs/15-risks-decisions-and-references.md) | 风险降级矩阵、架构决策记录和参考资料 |
| [本地开发、部署与运维手册](novel-character-generator/docs/16-local-development-and-runbook.md) | 安装、启动、迁移、备份恢复与故障排查 |
| [外观状态聚合实现契约](novel-character-generator/docs/17-appearance-aggregation-contract.md) | Observation 到可批准 RenderProfile 的落地规则 |
| [图像生成端到端实现契约](novel-character-generator/docs/18-image-generation-implementation-contract.md) | Image Run、Provider、恢复、漂移审计和锁定边界 |
| [功能—代码—测试追踪矩阵](novel-character-generator/docs/19-feature-traceability-matrix.md) | 功能与实现、日志、测试、状态的对应关系 |
| [API 调用手册与错误目录](novel-character-generator/docs/20-api-cookbook-and-error-catalog.md) | 真实接口调用、SSE、并发更新和稳定错误码 |
