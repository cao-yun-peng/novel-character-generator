# 项目验收

> 执行测试、交付或声明完成前必须读取本文件。没有新鲜证据时不得写成通过。
> 不粘贴密钥、完整个人信息、原始顾客对话或未脱敏工具输出。

## 当前验收结论

- 结论：真实全链路工程运行通过；R2/R3 与最终画像语义质量 Gate 不通过，不能进入批量生图
- 验收范围：《斗罗大陆》前 20 章 19 Chunk 的 R1/R2/R3/聚合真实 Provider 运行；保留既有基础主链验收
- 最后检查：2026-08-27
- 遗留问题：R2 显式姓名可跨人物污染；R3 不会由年龄/转生形成阶段且未识别武魂附体暂态；R1 有等级伪年龄和字段错配；同 run 多 resolver 版本可产生重复事实；干净成本/延迟基线与跨作品黄金集仍未完成。

## 验收标准

| 标准 ID | 标准 | 状态 | 验证方法 | 证据 ID |
|---|---|---|---|---|
| A-R2-SHARD-001 | Dirty frontier 按完整 record 在 record、mention、完整请求预计输入和预计输出预算内确定性分片；原子记录超预算失败关闭 | 通过 | 四重预算/超预算单元测试与多 shard 集成测试 | E-20260827-R2-SHARD-004-CAL1 |
| A-R2-SHARD-002 | Provider 未安全覆盖记录最多两轮 repair；次数或调用预算耗尽后 100% 保守补全并显式 warning | 通过 | repair 成功、次数耗尽和调用预算耗尽集成反例 | E-20260827-R2-SHARD-004-CAL1 |
| A-R2-SHARD-003 | RunEvent/Inspector/UI 显示四重 shard 预算、估算策略、调用、repair、fallback 且 completed_with_warnings 可恢复不重跑 | 通过 | R2 pipeline、Inspector API/UI 契约和恢复测试 | E-20260827-R2-SHARD-004-CAL1 |
| A-R2-FRONTIER-001 | 十章收敛只处理当前批次 dirty non-stable，未变化历史 unresolved 保留但不重复提交 | 通过 | frontier 服务单元测试与两批次集成测试 | E-20260827-R2-FRONTIER-003 |
| A-R2-FRONTIER-002 | 收敛 RunEvent/Inspector 显示 frontier/deferred、Provider 原始覆盖、omission 与收敛后状态且不含原文 | 通过 | 事件与 Inspector API/UI 契约测试 | E-20260827-R2-FRONTIER-003 |
| A-R2-MEM-001 | 逐 Chunk 人物解析只携带有界相关 memory，且未入选历史 memory 在应用结果后不丢失 | 通过 | 服务单元测试与 R2 流水线集成测试 | E-20260827-R2-MEMORY-002 |
| A-R2-MEM-002 | RunEvent 与 Run Inspector 可查看 memory 裁剪前后数量、入选原因和状态构成，且不含正文或证据原文 | 通过 | 事件 payload 与 Inspector API/UI 契约测试 | E-20260827-R2-MEMORY-002 |
| A-001 | v3 候选与证据定位在跨题材样本上可运行 | 通过 | 有界真实 Provider 诊断 | E-20260826-R1-EVAL-002 |
| A-002 | 新 case 不包含作品专名或世界观特例规则 | 通过 | 数据集和 Prompt 静态扫描 + 人工审核 | E-20260826-R1-EVAL-002、E-20260826-R1-PROMPT-003 |
| A-003 | 项目约定的测试全部通过 | 通过 | Ruff、Mypy、Pytest | E-20260826-R1-EVAL-004 |
| A-004 | 成本、失败和未覆盖项被如实记录 | 通过 | 检查诊断 metadata 与任务证据 | E-20260826-R1-EVAL-002、E-20260826-R1-PROMPT-003 |
| A-005 | 字段混淆规则使用跨作品语义边界且逐 case 独立验证 | 通过 | Prompt 静态检查、真实 v3 独立调用、字段集合人工复核 | E-20260826-R1-PROMPT-003 |
| A-006 | 评测器对结构错误、未知措辞和已确认等价值给出确定性三态结果 | 通过 | 单元测试、保存结果离线重评分、全量回归 | E-20260826-R1-EVAL-004 |
| A-R2-001 | 第 3 Chunk 输入包含前两 Chunk 累计记忆；同泛称不会由代码自动绑定 | 通过 | 单元与端到端反例测试 | E-20260827-R2-ENTITY-001 |
| A-R2-002 | 每 10 Chunk 固定收敛，文末余数执行尾批 | 通过 | 11 章集成测试检查 0–9 与 10–10 批次 | E-20260827-R2-ENTITY-001 |
| A-R2-003 | 只有 final 绑定生成 Observation，失败和 unresolved 均失败关闭 | 通过 | 失败替换与“另一男孩”隔离集成测试 | E-20260827-R2-ENTITY-001 |
| A-R2-004 | 迁移、幂等、静态检查和项目回归通过 | 通过 | Alembic/Ruff/Mypy/Pytest | E-20260827-R2-ENTITY-001 |
| A-R3-001 | 显式时间信号完整定位持久化，事实级信号不扩散到同 mention 的其他事实 | 通过 | Adapter 单元测试与 R3 集成反例 | E-20260827-R3-PHASE-001 |
| A-R3-002 | R2 观察保持 pending；R3 final 才激活，needs_review 不进入聚合 | 通过 | 阶段流水线集成测试 | E-20260827-R3-PHASE-001 |
| A-R3-003 | 阶段/呈现/现实/形态解析及审核、查询、revision 修订接口可运行 | 通过 | 纯服务单元测试与 API 集成测试 | E-20260827-R3-PHASE-001 |
| A-R3-004 | 唯一迁移 head、静态检查和全量回归通过 | 通过 | Alembic/Ruff/Mypy/Pytest | E-20260827-R3-PHASE-001 |
| A-REAL-001 | 真实长文本可从 checkpoint 完成 R1/R2/R3/聚合并保存可复核证据 | 通过 | 19 Chunk 隔离 DeepSeek run + summary/DB 审核 | E-20260827-R123-REAL-001 |
| A-REAL-002 | R2 最终记忆不跨显式姓名污染且 stable 覆盖正式人物 | 不通过 | final convergence memory 人工/SQL 审核 | E-20260827-R123-REAL-001 |
| A-REAL-003 | R3 分离转生前后人生阶段和暂态 transformation | 不通过 | life phases、scope bindings、appearance states 审核 | E-20260827-R123-REAL-001 |
| A-REAL-004 | 聚合画像的默认锚点可直接用于人物定妆 | 不通过 | render profile/identity anchor/conflict 审核 | E-20260827-R123-REAL-001 |
| A-REAL-005 | 本轮工程修复的静态与完整回归通过 | 通过 | Ruff/Mypy/Pytest 144 tests | E-20260827-R123-REAL-001 |
| A-OBS-001 | R1/R2/R3 独立阶段摘要可查询且不复制正文 payload | 通过 | API 集成测试与响应边界断言 | E-20260827-OBS-RUN-001 |
| A-OBS-002 | 四类结构化产出详情受 Run 归属和 kind/id 校验保护 | 通过 | R1/R2/R3 详情与 404 反例测试 | E-20260827-OBS-RUN-001 |
| A-OBS-003 | 工作台可查看阶段卡片并下钻，桌面与窄屏可读 | 通过 | UI 静态契约、JS 语法和浏览器视觉检查 | E-20260827-OBS-RUN-001 |
| A-OBS-004 | Inspector 增量静态检查和全量回归通过 | 通过 | Ruff/Mypy/Pytest | E-20260827-OBS-RUN-001 |
| A-RAW-001 | R1/R2 成功 Provider 调用保存消息、完整响应与哈希，普通 Inspector 不复制 raw | 通过 | Provider 单元、R1/R2 API 集成与边界断言 | E-20260827-DEV-RAW-001 |
| A-RAW-002 | 原始响应接口仅 development + 显式开关 + 管理员可读，生产失败关闭 | 通过 | Settings 与 403/200 API 反例 | E-20260827-DEV-RAW-001 |
| A-RAW-003 | 工作台页签、旧 Run 提示与 R3 隐藏行为可读且无控制台错误 | 通过 | Node 与本地浏览器检查 | E-20260827-DEV-RAW-001 |
| A-RAW-004 | 唯一迁移 head、静态检查和完整回归通过 | 通过 | Alembic/Ruff/Mypy/Node/159 Pytest | E-20260827-DEV-RAW-001 |

## 证据索引

| 证据 ID | 时间 | 方法或命令 | 退出状态 | 版本或文件哈希 | 结果摘要 | 证据位置 | 有效期 |
|---|---|---|---|---|---|---|---|
| E-20260827-R2-SHARD-004-CAL1 | 2026-08-27 | 历史覆盖计数校准 + 四重预算/Provider/Inspector 回归 + Ruff/Mypy/Node/完整 Pytest | 0 | 见任务 evidence | 172 tests；默认值 16 records/32 mentions/12k input/4.5k output；0 新真实 API calls | `.project-to-act/tasks/R2-SHARD-004/evidence/E-20260827-R2-SHARD-004-CAL1.md` | 分片策略、Prompt/Schema、Provider、估算器或配置变化前 |
| E-20260827-R2-SHARD-004 | 2026-08-27 | shard/repair/警告/恢复/Inspector 反例 + Ruff/Mypy/Node/完整 Pytest | 0 | 见任务 evidence | 171 tests；三重预算分片、有限 repair、耗尽 warning 与恢复通过；0 真实 API calls | `.project-to-act/tasks/R2-SHARD-004/evidence/E-20260827-R2-SHARD-004.md` | 分片/repair、R2 Schema、事件/Inspector 或配置变化前 |
| E-20260827-R2-FRONTIER-003 | 2026-08-27 | frontier/跨批 unresolved/trace 反例 + Ruff/Mypy/Node/定向与全量 Pytest | 0 | 见任务 evidence | 18 项定向测试与全量回归通过；旧 unresolved 不重复提交且完整 memory 保留 | `.project-to-act/tasks/R2-FRONTIER-003/evidence/E-20260827-R2-FRONTIER-003.md` | frontier、R2 收敛事件或 Inspector 变化前 |
| E-20260827-R2-MEMORY-002 | 2026-08-27 | memory 选择/保留/trace 反例 + Ruff/Mypy/Node/定向与全量 Pytest | 0 | 见任务 evidence | 26 项定向测试与全量回归通过；逐 Chunk 模型视图有界且完整 memory 不丢失 | `.project-to-act/tasks/R2-MEMORY-002/evidence/E-20260827-R2-MEMORY-002.md` | memory 选择、R2 事件或 Inspector 变化前 |
| E-20260826-R1-PROMPT-003 | 2026-08-26 | 17 次独立 v3 调用 + 字段/原子结构审核 + Ruff/Mypy/Pytest | 0 | 见任务 evidence | v2.1 字段结构 7/7；v2.2 定向 3/3；121 tests；32,280 tokens | `.project-to-act/tasks/R1-PROMPT-003/evidence/E-20260826-R1-PROMPT-003.md` | Prompt、模型或评测变化前 |
| E-20260826-R1-EVAL-004 | 2026-08-26 | rubric v2 边界测试 + 保存结果离线重评分 + Ruff/Mypy/Pytest | 0 | 见任务 evidence | v2.2：2 pass / 1 review / 0 fail；126 tests；0 API calls | `.project-to-act/tasks/R1-EVAL-004/evidence/E-20260826-R1-EVAL-004.md` | 评测器、rubric 或种子数据变化前 |
| E-20260826-R1-EVAL-002 | 2026-08-26 | 两次真实 v3 诊断 + 人工差异审核 + Ruff/Mypy/Pytest | 0 | 见任务 evidence | 25 case；119 tests；7,535 tokens | `.project-to-act/tasks/R1-EVAL-002/evidence/E-20260826-R1-EVAL-002.md` | 配置变化前 |
| E-20260827-R2-ENTITY-001 | 2026-08-27 | R2 单元/集成反例 + Ruff/Mypy/Alembic/Pytest | 0 | 见任务 evidence | 129 tests；实体定向 2 tests；0 真实 API calls | `.project-to-act/tasks/R2-ENTITY-001/evidence/E-20260827-R2-ENTITY-001.md` | R2 Schema/Prompt/收敛/迁移变化前 |
| E-20260827-R3-PHASE-001 | 2026-08-27 | R3 单元/流水线/API 反例 + Ruff/Mypy/Alembic/Pytest | 0 | 见任务 evidence | 135 tests；114 source files；唯一 head a3e8c1d4f620；0 真实 API calls | `.project-to-act/tasks/R3-PHASE-001/evidence/E-20260827-R3-PHASE-001.md` | R3 Schema/解析/门禁/迁移变化前 |
| E-20260827-R123-REAL-001 | 2026-08-27 | 19 Chunk 隔离 DeepSeek 全链路 + DB/summary 人工审核 + Ruff/Mypy/Pytest | 工程 0；质量 Gate 失败 | source SHA256 `8bcb7305...9741`，其余见任务 evidence | 工程 succeeded；R2 人物污染、R3 零阶段、聚合默认锚点污染；144 tests 通过；246,633 recorded tokens | `.project-to-act/tasks/R123-REAL-001/evidence/E-20260827-R123-REAL-001.md` | R1/R2/R3/模型配置变化前 |
| E-20260827-OBS-RUN-001 | 2026-08-27 | Inspector API/UI 反例 + Ruff/Mypy/Pytest + Node + 浏览器桌面/720px | 0 | 见任务 evidence | 三阶段摘要与四类下钻通过；115 source files；146 tests；0 真实 API calls | `.project-to-act/tasks/OBS-RUN-001/evidence/E-20260827-OBS-RUN-001.md` | Inspector Schema、业务表、RunEvent usage 或 UI 变化前 |
| E-20260827-DEV-RAW-001 | 2026-08-27 | raw Provider/Settings/API/迁移反例 + Ruff/Mypy/Node/159 Pytest + 浏览器 | 0 | 见任务 evidence | R1/R2 raw、管理员门禁、生产失败关闭、UI 页签通过；0 真实 API calls | `.project-to-act/tasks/DEV-RAW-001/evidence/E-20260827-DEV-RAW-001.md` | raw Schema、Provider、表、权限或 UI 变化前 |

## Gate 记录

| Gate ID | 日期 | Gate | 对象 | 结果 | 证据 ID | 豁免与确认人 |
|---|---|---|---|---|---|---|
| G-R2-SHARD-004-CAL1 | 2026-08-27 | R2 收敛预算失败数据校准 | R2-SHARD-004 | 通过（历史样本与自动化；真实新 Run 的覆盖率、成本、延迟及 stable context 检索仍待后续） | E-20260827-R2-SHARD-004-CAL1 | 无 |
| G-R2-SHARD-004 | 2026-08-27 | R2 收敛预算分片与 omission repair 增量 | R2-SHARD-004 | 通过（自动化与 Inspector 契约；真实 token 降幅、repair 成功率、stable context 检索和 final sweep 仍待后续） | E-20260827-R2-SHARD-004 | 无 |
| G-R2-FRONTIER-003 | 2026-08-27 | R2 十章收敛 dirty frontier 增量 | R2-FRONTIER-003 | 通过（自动化与 Inspector 契约；单 frontier 分片、repair 和真实 token 降幅仍待后续） | E-20260827-R2-FRONTIER-003 | 无 |
| G-R2-MEMORY-002 | 2026-08-27 | R2 逐 Chunk memory 容量治理增量 | R2-MEMORY-002 | 通过（自动化与 Inspector 契约；真实 token 降幅和十章收敛容量仍待后续） | E-20260827-R2-MEMORY-002 | 无 |
| G-R1-PROMPT-003 | 2026-08-26 | R1 通用语义 Prompt 增量 | R1-PROMPT-003 | 通过（保留严格字符串与 v2.2 全量复测缺口；不代表 R1 阶段通过） | E-20260826-R1-PROMPT-003 | 无 |
| G-R1-EVAL-004 | 2026-08-26 | R1 评测器三态边界增量 | R1-EVAL-004 | 通过（review 写回仍为人工流程；不代表 R1 阶段通过） | E-20260826-R1-EVAL-004 | 无 |
| G-R1-EVAL-002 | 2026-08-26 | R1 跨题材差异回灌 | R1-EVAL-002 | 通过（不代表 R1 阶段通过） | E-20260826-R1-EVAL-002 | 无 |
| G-R2-ENTITY-001 | 2026-08-27 | R2 实体解析基础主链增量 | R2-ENTITY-001 | 通过（仅实现与自动回归；不代表 R2 质量 Gate、阶段 5 或生产发布通过） | E-20260827-R2-ENTITY-001 | 无 |
| G-R3-PHASE-001 | 2026-08-27 | R3 阶段与时间作用域基础主链增量 | R3-PHASE-001 | 通过（仅实现与自动回归；不代表 R3 跨作品质量 Gate、阶段 5 或生产发布通过） | E-20260827-R3-PHASE-001 | 无 |
| G-R123-REAL-001 | 2026-08-27 | R1/R2/R3 真实语义质量 | R123-REAL-001 | 不通过（工程链路通过；禁止据此进入批量生图） | E-20260827-R123-REAL-001 | 无 |
| G-OBS-RUN-001 | 2026-08-27 | R1–R3 Run Inspector 纵向切片 | OBS-RUN-001 | 通过（仅可观测性入口；不代表真实语义质量、阶段 5 或生产发布通过） | E-20260827-OBS-RUN-001 | 无 |
| G-DEV-RAW-001 | 2026-08-27 | 开发模型原始响应查看器 | DEV-RAW-001 | 通过（成功且 Schema 有效的调用；不含失败 raw、清理策略或 token streaming） | E-20260827-DEV-RAW-001 | 无 |

## 验收记录

按时间倒序追加：日期、检查范围、证据 ID、结果、遗留问题和结论。失败、跳过与过期证据也必须如实记录。

- 2026-08-27：R2-SHARD-004 失败数据校准自动化增量通过；四重预算、Provider Prompt/Schema 输入开销、Trace/Inspector/UI、39 项定向、172 项完整 Pytest、Ruff、Mypy 和 Node 均通过。没有运行新真实 Provider，32/16/12k/4.5k 仍是保守起点，不构成最终 p95/p99 容量结论。
- 2026-08-27：R2-FRONTIER-003 自动化增量通过；frontier 选择、旧 unresolved 保留不重跑、新 mention 重新激活、Provider 原始覆盖/omission trace、全量 Pytest、Ruff、Mypy 和 Node 均通过。未运行真实付费 Provider；分片、repair、stable context 检索及有界 final sweep 不在本 Gate 内。
- 2026-08-27：R2-MEMORY-002 自动化增量通过；相关 memory 选择、隐藏历史保留、事件/Inspector 数据边界、全量 Pytest、Ruff、Mypy 和 Node 均通过。未运行真实付费 Provider，新 Run 的实际 token 降幅及十章收敛输入/输出膨胀不在本 Gate 内。
- 2026-08-27：DEV-RAW-001 开发增量通过；R1/R2 raw 持久化、管理员页签、生产失败关闭、迁移、159 项完整测试和浏览器检查通过。旧 Run 不补录；失败 Schema raw、保留期限和 token streaming 明确未覆盖。
- 2026-08-27：OBS-RUN-001 纵向切片通过；R1/R2/R3 摘要、结构化下钻、404/正文边界、全量静态/测试和响应式视觉检查均通过。保留 OTel、生产采样/留存、Langfuse 与黄金集质量指标缺口；不改变 R123-REAL-001 的真实语义质量 Gate 失败结论。
- 2026-08-27：R123-REAL-001 完成 19 Chunk 真实 DeepSeek 全链路；checkpoint 与工程回归通过，但唐三/唐昊实体污染、0 life phases、变身外观污染默认锚点，故真实语义质量 Gate 明确判定不通过，不进入批量生图。
- 2026-08-27：R3-PHASE-001 基础主链增量通过；135 项全量测试、114 个源码文件类型检查、唯一 Alembic head 和迁移测试通过；“前世黑发”不会把阶段扩散到“三年后白衣”，后者保持审核态。保留真实 Provider phase/scope 质量、复杂 timeline/event 和审核后自动重聚合缺口。
- 2026-08-27：R2-ENTITY-001 基础主链增量通过；129 项全量测试、110 个源码文件类型检查和迁移升降级通过，“另一男孩”特征不进入唐三。保留真实模型跨作品质量、成本和延迟评测，不宣称 R2 完整 Gate。
- 2026-08-26：R1-EVAL-004 增量验证通过；未知 value 保守进入 review，已接受等价值自动通过，结构与无证据错误保持 fail；126 项测试通过。保留“review 写回为人工流程”和“种子集 25/30–40”两个缺口。
- 2026-08-26：R1-PROMPT-003 增量验证通过；七类语义字段错配未复现，Prompt 无作品特例，121 项本地测试通过。保留“最终 v2.2 未全量付费复测”和“严格值/证据评分过于表面化”两个缺口。
- 2026-08-26：R1-EVAL-002 增量验收通过；两次真实调用和本地回归均成功。保留“新 Prompt 未付费复测”和“尚未达到 30–40 case”两个非阻断缺口。
