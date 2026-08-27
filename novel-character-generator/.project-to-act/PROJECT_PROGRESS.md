# 项目进度

> 记录当前执行状态与有效工作节点；普通查看、搜索和无状态变化的命令不写入。

## 当前任务

| 任务 | 状态 | 负责人 | 完成条件 | 证据 ID | 最后更新 |
|---|---|---|---|---|---|
| R2-SHARD-004 | 已完成校准，待新 Run 复核 | Codex | frontier 四重预算分片、失败数据默认值、遗漏有限 repair、Trace/Inspector 可见、完整回归通过 | E-20260827-R2-SHARD-004-CAL1 | 2026-08-27 |
| R2-FRONTIER-003 | 已完成，待新 Run 复核 | Codex | 收敛只处理 dirty non-stable、旧 unresolved 保留不重跑、frontier/覆盖率 trace 可见、完整回归通过 | E-20260827-R2-FRONTIER-003 | 2026-08-27 |
| R2-MEMORY-002 | 已完成，待新 Run 复核 | Codex | 逐 Chunk 相关 memory 有界、完整 memory 不丢失、RunEvent/Inspector 展示裁剪变化、定向回归通过 | E-20260827-R2-MEMORY-002 | 2026-08-27 |
| DEV-RAW-001 | 已完成，待新 Run 复核 | Codex | 开发开关、R1/R2 raw 持久化、管理员页签、生产门禁、迁移和完整回归完成 | E-20260827-DEV-RAW-001 | 2026-08-27 |
| OBS-RUN-001 | 已完成，待产品复核 | Codex | R1/R2/R3 摘要、可读 trace/产出详情、工作台三阶段视图和浏览器验证完成 | E-20260827-OBS-RUN-001 | 2026-08-27 |
| R123-REAL-001 | 待二次干净复测 | Codex | 首次干净 run 核心 Gate 通过；run 后 6 类通用修复需新 run 验证 | E-20260827-R123-REAL-001 | 2026-08-27 |
| R3-PHASE-001 | 待复核 | Codex | 时间信号、阶段/作用域解析、pending/final 门禁、审核修订 API、迁移和全量回归完成 | E-20260827-R3-PHASE-001 | 2026-08-27 |
| R2-ENTITY-001 | 待复核 | Codex | 逐章模型判断、累计记忆、十章/尾批收敛、final-only 写入、恢复和自动测试完成 | E-20260827-R2-ENTITY-001 | 2026-08-27 |
| R1-EVAL-004 | 待复核 | Codex | 三态评分、局部等价值、证据包含边界和全量回归完成 | E-20260826-R1-EVAL-004 | 2026-08-26 |
| R1-PROMPT-003 | 待复核 | Codex | 通用语义 Prompt、契约测试、七类 case 独立 v3 真实验证完成并记录 | E-20260826-R1-PROMPT-003 | 2026-08-26 |
| R1-EVAL-002 | 待复核 | Codex | 两部新增小说完成有界 v3 采样；差异被抽象为通用 case；回归通过并记录成本 | E-20260826-R1-EVAL-002 | 2026-08-26 |

## 阻塞项

| 阻塞 | 影响 | 解除条件 | 状态 |
|---|---|---|---|
| 无已知阻塞 | 无 | 不适用 | 无 |

## 下一步

1. 重启 API/Worker 后创建全新 run，复核 R2 memory/frontier/shard/repair trace 和真实 token/调用变化。
2. 收敛 stable context 改为按 frontier 检索候选，避免稳定人物上下文成为下一容量瓶颈。
3. 设计有界 final sweep，分片回收长期 deferred unresolved，仍遗漏时保持质量警告。
4. 继续 OTel/Langfuse 运行关联与真实跨作品质量评测。

## 进度历史

按时间倒序追加：日期、完成事项、证据 ID、遗留问题、下一步和确认来源。不要覆盖旧记录。

- 2026-08-27：依据历史收敛 35/35、15/46、6/48 mention 覆盖样本完成 R2 预算校准；默认值改为 16 records、32 mentions、12,000 完整请求预计输入、4,500 预计输出，真实 Provider Prompt/Schema 开销进入估算，Trace/Inspector/UI 显示 record 与估算策略。39 项定向、172 项完整 Pytest、Ruff、Mypy、Node 通过。未运行新真实 Provider，下一步复核新 Run 覆盖率和预计/实际 token 偏差。证据 `E-20260827-R2-SHARD-004-CAL1`。
- 2026-08-27：完成 R2 frontier 三重预算原子分片和 omission repair；主请求只按完整 memory record 分片，遗漏记录最多两轮 repair，次数/调用预算耗尽后确定性 unresolved 并标记 `completed_with_warnings`；RunEvent/Inspector/UI 显示预算、shard、repair 和 fallback。171 项完整回归、Ruff、Mypy、Node 通过。未运行真实 Provider，新 Run 与 stable context 检索仍待后续。证据 `E-20260827-R2-SHARD-004`。
- 2026-08-27：完成 R2 十章收敛 dirty memory frontier；旧 unresolved 无新证据时不再跨批重复提交，新 mention 可重新激活对应记录；Provider 原始覆盖/omission 与保守补全结果在 RunEvent/Inspector 分开展示。18 项定向测试、全量 Pytest、Ruff、Mypy、Node 通过。未做分片与 repair，待新真实 Run 复核。证据 `E-20260827-R2-FRONTIER-003`。
- 2026-08-27：完成 R2 逐 Chunk 相关 memory 裁剪；完整 memory 保留，模型视图默认限制 64/16，RunEvent/Inspector 展示裁剪前、入选、处理后及状态构成；26 项定向测试、全量 Pytest、Ruff、Mypy 和 Node 通过。未改变十章收敛，待新真实 Run 复核。证据 `E-20260827-R2-MEMORY-002`。
- 2026-08-27：完成开发环境模型原始响应查看器；R1/R2 每次成功调用可保存消息正文、完整 Provider JSON 和哈希，管理员页签可读，生产失败关闭；159 tests、Ruff、Mypy、Node、迁移和浏览器检查通过。旧 Run 不补录，下一步用新 Run 复核。证据 `E-20260827-DEV-RAW-001`。
- 2026-08-27：完成 R1–R3 Run Inspector 纵向切片；摘要、四类结构化产出下钻、工作台三阶段卡片、敏感数据边界、全量静态/测试与桌面/窄屏浏览器检查通过。未接 OpenTelemetry/Langfuse，不代表语义质量 Gate 通过。证据 `E-20260827-OBS-RUN-001`。
- 2026-08-27：用同一文本新建完全隔离的干净 run；19/19 Chunk 与四步 Pipeline 成功，唐三/唐昊姓名隔离、伪年龄清除、唐三前世/转生幼年阶段生成、精确重复为 0。真实结果继续暴露字段与 transformation 假冲突，已补通用门禁和回归；全量 157 tests、Ruff、Mypy 与浏览器检查通过。因新增修复尚未二次真实 run，总体 Gate 为 review。证据 `E-20260827-R123-REAL-001`。
- 2026-08-27：从 checkpoint 完成《斗罗大陆》前 20 章 19/19 Chunk 的真实 DeepSeek 全链路。工程恢复与四步骤执行成功，144 项完整测试通过；但 R2 唐三/唐昊实体污染、R3 零人生阶段和素云涛变身污染导致语义质量 Gate 失败。证据 `E-20260827-R123-REAL-001`。
- 2026-08-27：完成 R3 人物阶段与时间作用域基础主链；R2 后观察保持 pending，R3 final 才激活，时间跳跃歧义进入审核；新增阶段查询/修订 API，135 项全量测试通过。真实 Provider 阶段质量与复杂时间线仍待评测。证据 `E-20260827-R3-PHASE-001`。
- 2026-08-27：完成 R2 人物实体解析基础主链；逐 Chunk 使用累计记忆，每 10 Chunk 固定收敛并执行尾批，只有 final 绑定写 Observation；129 项全量测试通过。真实模型跨作品质量与成本尚未评测。证据 `E-20260827-R2-ENTITY-001`。
- 2026-08-26：完成 rubric v2 三态评分、局部等价值和离线重评分；v2.2 定向结果为 2 pass / 1 review / 0 fail，126 项测试通过。证据 `E-20260826-R1-EVAL-004`。
- 2026-08-26：完成通用语义 Prompt v2.2；17 次独立 v3 调用未复现七类字段错配，121 项本地测试通过。严格字符串评分仍受等价措辞影响；证据 `E-20260826-R1-PROMPT-003`。
- 2026-08-26：两部跨题材小说完成各 1 个分块的 v3 付费采样；18 个候选全部精确定位。人工审核形成 7 类通用差异，种子集由 18 增至 25，119 项测试通过。证据 `E-20260826-R1-EVAL-002`。新 Prompt 尚未付费复测。
