# 风险、关键决策与参考资料

> [← 上一篇](14-roadmap.md) · [文档索引](README.md)
>
> 文档版本：2.8 · 源章节：19. 风险与降级策略、附录 A：关键设计决策、附录 B：参考资料 · 修订日期：2026-08-22

## 19. 风险与降级策略

| 风险 | 表现 | 降级/缓解 |
|---|---|---|
| LLM 幻觉 | 无原文证据的外貌字段 | 证据必填、precision 优先、人工审核 |
| 别名误合并 | 两个角色被当成一人 | 保留假设、置信度、支持拆分和重算 |
| 时间线误绑定 | 少年、老年、梦境或分支状态相互覆盖 | 叙事顺序与故事顺序分离、作用域候选、复杂案例转人工 |
| 状态组合爆炸 | 年龄、伤势、伪装、服装组合生成大量完整状态 | AppearanceState 保存部分覆盖层，目标时点按类型/优先级合并并保存扁平快照 |
| 神情语义误读 | 把内心狂喜画成微笑，或让瞬时表情永久化 | 内外情绪分字段、可见线索证据、场景级默认有效期 |
| 长文本成本失控 | 调用数随角色数倍增 | 块级批量提取、相关记忆注入、预算门槛 |
| 工作流不兼容 | 模型或节点无法组合 | 固定兼容矩阵、commit 与契约测试 |
| 单指标误判 | 背景相似导致高 CLIP-I | 主体裁剪、多指标与人工终审 |
| Worker 崩溃 | 重复提交或任务卡死 | 租约、幂等、远程 request ID、恢复测试 |
| 外部提交状态未知 | Provider 已收费但本地未保存 job ID | ExternalOperation 提交状态、request fingerprint、reconcile 和人工对账，禁止盲目重提 |
| 图像冷启动 | 首次请求下载模型/节点导致分钟级等待或超时 | 固定镜像、预热、区分冷/热 P95、启动探针和更长外部等待状态 |
| SQLite 写锁 | 并发更新失败 | 单写 Worker、短事务；二期 PostgreSQL |
| Provider 价格变化 | 预算不准确 | 动态价格快照、运行前估价和硬预算 |
| 遥测后端故障 | Trace/Metrics 无法导出或队列积压 | 有界异步队列、批量导出、普通遥测可丢弃并计数，业务主流程继续 |
| Metrics 高基数 | 时序数量和存储成本失控 | 禁止业务 ID 和自由文本作为标签，明细通过 Trace/日志/业务库查询 |
| 观测数据泄露 | 正文、Prompt、密钥或签名 URL 出现在日志/Trace/告警 | 统一脱敏过滤、属性白名单、泄漏测试和受控保留周期 |
| 云端数据风险 | 正文或图像泄漏 | 最小发送、明确告知、删除策略、日志脱敏 |
| 局部 LangGraph 升级 | PoC Agent 的旧 checkpoint 无法读取 | Graph State schema version、兼容迁移或显式终止旧 Agent attempt；不影响业务 Run 真值 |
| Agent 越权 | 自行提交收费/写入/删除动作 | 工具白名单、权限交集、审批门槛和运行时守卫 |
| Prompt 注入 | 小说文本或工具结果包含恶意指令 | 数据与指令分层、内容标记、工具结果不可信处理 |
| Agent 循环 | 重复查询、反思或重新生成 | 最大轮次/工具数/费用/时间和结构化停止 |
| 上下文污染 | 摘要错误逐轮放大 | 原始证据优先、来源 ID、上下文哈希和定期重建 |
| 多 Agent 分歧 | 多个建议互相冲突 | Orchestrator 按规则聚合，高风险转人工，不自由辩论 |
| Provider 特性锁定 | 高级 Agent 能力无法迁移 | Capabilities 探测、普通 Tool Calling/Structured Output 降级 |
| 评测泄漏或过拟合 | 同一小说角色同时出现在开发集和测试集 | 按小说划分、冻结 test、版本化 EvalCase、失败样本先进入 quarantine |
| 轨迹泄露 | 保存敏感输入或隐藏推理 | 仅保存可见输出、摘要、哈希和工具事件，严格脱敏 |

---

## 附录 A：关键设计决策

| 决策 | 选择 | 原因 |
|---|---|---|
| 一期目标 | 识别全书候选角色，精细处理 3–5 个主要角色；每个主要角色默认输出 2–4 个关键阶段形象 | 控制角色数量与生成成本，同时保留主角历史形象价值 |
| 文本调用粒度 | 每块一次批量提取 | 避免 `块数 × 角色数` 爆炸 |
| 事实模型 | Observation + Identity/Appearance/Scene 三层状态 + RenderProfile | 支持证据、多时间线、瞬时神情和人工选择 |
| Observation 时间 | 故事有效时间 + 系统记录/失效时间 | 支持中部编辑、删除章节、重抽取和历史重放 |
| 状态合并 | AppearanceState 部分覆盖层 + 目标时点扁平快照 | 同时表达年龄、伤势、伪装和服装，避免组合爆炸 |
| 渲染输入 | 目标时点 ResolvedCharacterSnapshot | 防止默认使用错误年龄、服装、伤势或神情 |
| 冲突判定 | 同角色/字段/时间线/重叠区间/现实层级联合判断 | 时间变化和叙事视角差异不应误报为事实矛盾 |
| 编排 | Application Orchestrator + PipelineRun/PipelineStep 是主流程唯一编排；LangGraph 仅为局部 AgentRuntime PoC | 避免任务状态与 Graph checkpoint 双真值，只有证明多轮语义收益后才局部引入 |
| 长任务 | 独立 Worker + durable Run/Step | HTTP 解耦、可恢复、可取消 |
| 外部副作用 | ExternalOperation 独立状态机 | 关闭提交崩溃窗口，支持未知状态对账和 fencing |
| ORM | 全异步 SQLAlchemy | 与 FastAPI/外部异步调用保持一致，不混用 Session |
| 数据库 | 一期 SQLite，二期 PostgreSQL | 一期低运维，明确并发边界 |
| 图像方案 | 一期固定一套兼容工作流；一个角色形成多个阶段基准图和一个默认代表形象 | 先保证可复现，并避免把完整角色历程压缩成单一形象 |
| 质量评测 | 多指标 + 人工终审 | CLIP-I 不足以判断身份一致性 |
| 防漂移 | 冻结 GenerationContext + 结构化 DriftAudit + 硬门禁 + 有界重生成 + 人工锁定 | 避免只靠 Prompt 提醒、模型自审或单一总分；阻止草稿和生成图反向污染事实库 |
| 评测真值 | 版本化 EvalDataset/Case/Run/Result/Grader | 数据、配置、评分器、成本和发布结论可复现 |
| Prompt | 一期 Git 文件，二期在线发布 | 避免过早建设管理平台 |
| 3D/LoRA | 二期正式实现 | 保留完整路线但不阻塞一期验证 |
| 价格 | 动态快照，不在文档硬编码 | 模型和平台价格会变化 |
| 可观测性 | OpenTelemetry 标准 + 业务 Run/Step 双层链路 | Trace 定位运行故障，业务记录解释事实、审批、产物和费用；观测后端不成为主流程依赖 |
| 日志检查 | 稳定业务事件 + DB/Artifact 对账 + 版本化 `log-check` 规则和双格式输出 | 在 CI 和故障诊断中自动发现断链、重复收费、上下文漂移、越权锁定与敏感信息泄漏 |
| Agent 定位 | 专项 Agent + 确定性 Orchestrator | 保留语义能力，同时控制副作用和成本 |
| Agent 通信 | Schema 产物 + 证据 ID | 不共享完整聊天历史，不自由群聊 |
| Agent 工具 | 强类型、最小权限、默认只读 | 降低越权、注入和不可恢复副作用 |
| Agent 循环 | 有界反思，失败转人工 | 防止无限调用和费用失控 |
| 高级 Agent 能力 | 二期按能力探测启用 | PTC、Tool Search、MCP、A2A 不作为一期硬依赖 |

## 附录 B：参考资料

- [OpenTelemetry Documentation](https://opentelemetry.io/docs/)
- [OpenTelemetry Python](https://opentelemetry.io/docs/languages/python/)
- [Prometheus Instrumentation Practices](https://prometheus.io/docs/practices/instrumentation/)
- [OpenAI Model Guidance：Tool Calling、Prompt Caching 与 Multi-agent](https://developers.openai.com/api/docs/guides/latest-model)
- [OpenAI Evals API](https://platform.openai.com/docs/api-reference/evals)
- [OpenAI Graders API](https://platform.openai.com/docs/api-reference/graders)
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
- [fal Workflow Endpoints](https://fal.ai/docs/documentation/model-apis/workflows)
- [InstantID](https://github.com/InstantID/InstantID)
- [PuLID](https://github.com/ToTheBeginning/PuLID)
- [Model Context Protocol Specification](https://modelcontextprotocol.io/specification/2025-06-18/server/index)
- [Agent2Agent Protocol Specification](https://a2a-protocol.org/v0.3.0/specification/)

---

[← 上一篇](14-roadmap.md) · [文档索引](README.md)
