# 项目进度

> 记录当前执行状态与有效工作节点；普通查看、搜索和无状态变化的命令不写入。

## 当前任务

| 任务 | 状态 | 负责人 | 完成条件 | 证据 ID | 最后更新 |
|---|---|---|---|---|---|
| PIPELINE-V2-M1-013 | 真实开发基线完成；模型质量 Gate 不通过，draft2 待用户审核 | Codex / 用户 Gate | M1 age/signal、presentation、unresolved 真缺陷修复；新 held-out 验收通过后才可开始 M2 | E-20260828-PIPELINE-V2-M1-013-REAL1 | 2026-08-28 |
| PIPELINE-V2-DESIGN-012 | v1.1 修订完成，待 P0 建项 | Codex | 复核缺口修补、输入/输出条件 Schema、Stage 4 条件 Gate 与治理验证通过；不代表实现/质量通过 | E-20260828-PIPELINE-V2-DESIGN-012-R1 | 2026-08-28 |
| R1-GOLD-FIX-011 | 已完成；进入 adapter/Prompt 修复 | Codex | v1.1 黄金/评分修正、74 份候选离线重评、完整回归与归因留证 | E-20260828-R1-GOLD-FIX-011 | 2026-08-28 |
| R1-GOLD-RUN-010 | 已完成；测量层需修正后离线重评 | Codex | 74 次同链路调用、v1 seed/真实汇总、黄金/Prompt/适配/评分逐层归因和报告留证完成 | E-20260828-R1-GOLD-RUN-010 | 2026-08-28 |
| R1-GOLD-008 | v1 工程完成；真实硬 Gate 暂不通过 | Codex | v0 保留、31-case v1、6 个真实切片与评分器完成；真实 A/B 发现测量问题，待修正和离线重评分 | E-20260828-R1-GOLD-008、E-20260828-R1-GOLD-RUN-010 | 2026-08-28 |
| R6-ALIYUN-009 | DashScope 与 timicc/image2 首图完成，待用户审批与漂移 Gate | Codex | 通用同步/异步 Provider、自然 Prompt/provenance 和两模型真实 PNG 通过；timicc 返回尺寸与请求不符，不能锁 baseline | E-20260828-R6-ALIYUN-009 | 2026-08-28 |
| R1-PROMPT-AB-007 | 已完成；v2.6 不切换 | Codex | 冻结 v2.5、同链路真实 A/B、v3.4 安全门禁、回滚点、完整回归和切换判定均留证 | E-20260827-R1-PROMPT-AB-007 | 2026-08-27 |
| R6-IMAGE-SPEC-008 | 已完成 Mock 规格切片，待真实字段接线 | Codex | typed expected-field adapter、strict brief/readiness/spec、Mock-only provider boundary、submit unknown 失败关闭与完整回归通过 | E-20260827-R6-IMAGE-SPEC-008 | 2026-08-27 |
| R1-DATA-006 | 已完成，待真实 Run 复核 | Codex | 四类 mention、age/clothing 门禁、分级证据定位、修复审计、兼容与完整回归通过 | E-20260827-R1-DATA-006 | 2026-08-27 |
| R1-BASELINE-005 | 已完成，7/7 已转绿 | Codex | R1 独立 fixture、历史 5 项红灯均转普通通过、证据安全边界保持通过 | E-20260827-R1-BASELINE-005、E-20260827-R1-DATA-006 | 2026-08-27 |
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
| 无 approved/locked 角色档案及图片漂移 Gate | 首图只能作为 expected-field 候选，不能成为可信 baseline 或开启批量 | 用户审批角色字段与候选图；实现 DriftAudit/Gate/BaselineSelection | 待下一增量 |

## 下一步

1. 用户审阅测量修正后的 `m1-local-observation-v1.1-draft2`，确认四处修正与 15 个 case 边界。
2. 最小修复 M1 的 age fact/signal 关系、presentation 分类和 unresolved 非视觉误报，并用当前 15 case 做回归。
3. 新建并由用户审核一组未被本轮输出影响的 held-out case；真实验收通过后才开始 M2，期间 V1 生产与回滚路径保持不变。
4. 后续端到端 P0 冻结 safe-fact recall、promotion coverage、Profile 完整率和 review 容量阈值；R6 批量生成继续关闭。

## 进度历史

- 2026-08-28：完成 `PIPELINE-V2-M1-013` 首次真实开发基线。DeepSeek `deepseek-v4-flash` 对 v1 的 15/15 调用一次成功，0 Schema/契约失败，共 31,697 tokens；人工复核修正四处测量边界并对保存输出零调用重评为 `v1.1-draft2`：11 pass / 0 review / 4 fail，事实召回 86.7%、事实精度 100%、时间信号召回/精度 25%。真实缺陷集中在 age fact/signal、presentation 分类和非视觉 unresolved；模型质量 Gate 不通过，M2 关闭。证据 `E-20260828-PIPELINE-V2-M1-013-REAL1`；确认来源：用户要求验证 M1 效果。

- 2026-08-28：完成 `PIPELINE-V2-M1-013` 工程切片。实现 M1 严格 DTO、局部引用/引文/排他门禁、不可变 shadow artifact、独立 OpenAI-compatible adapter、15-case draft 测试集、三态评分器和离线 CLI；删除重复 docs Prompt，R1/R2/M1 统一结构化 Provider 底层并删去重复循环/无用连接字段。251 Pytest、Ruff、125 source Mypy、治理验证通过，0 Provider/迁移/路由切换。旧 V1 代码与评测经引用审计仍用于生产/回滚，未误删。模型效果 Gate 等待用户审核；证据 `E-20260828-PIPELINE-V2-M1-013`；确认来源：用户要求继续并整理删除冗余。
- 2026-08-28：按用户复核修补 `PIPELINE-V2-DESIGN-012` 为 `semantic-pipeline-v2-design-v1.1`。M1 改为全有效 Chunk 默认覆盖；M2 增加载体语义单元；M3 增加组件完整性、旧绑定 supersede 与依赖失效；M4 增加 scene/event boundary 和结束条件；M5 改为人物+作用域一致性复核组。Schema 扩为 5 输入+5 输出并加入条件约束，补充联合 precision/coverage Gate、重复运行、数据保留、人工容量和最小运维表。生命周期 Stage 5→4 复审后 Stage 4 条件通过、Stage 5 ready；0 Provider、0 生产代码。证据 `E-20260828-PIPELINE-V2-DESIGN-012-R1`；确认来源：用户要求修补项目文件。
- 2026-08-28：完成 `PIPELINE-V2-DESIGN-012` 设计评审稿。流程改为 M1 局部命题、M2 全量字段语义、M3 全量相关身份组件、M4 全量时间/持续性、M5 downgrade-only 联合复核；N0/N2/N4/N6/N8/N9 仅做证据、组包、硬约束和状态。新增节点级输入输出、五份系统提示词、机器可读 Schema、状态漏斗、质量优先 Gate、离线/shadow/灰度/回滚计划；0 Provider 调用、0 生产代码修改。证据 `E-20260828-PIPELINE-V2-DESIGN-012`，待用户评审。
按时间倒序追加：日期、完成事项、证据 ID、遗留问题、下一步和确认来源。不要覆盖旧记录。

- 2026-08-28：完成 R1 黄金/评分测量修正；默认 seed 升级为 v1.1 / rubric v3.1，支持受控 owner/surface alias、optional safe deferred、raw mention、temporal 窄包含/去重，并将 asserted/deferred 双写提升为硬失败。74 份历史 candidates 离线重评后，A seed 13/7/11→20/1/10，B 12/7/12→22/1/8，真实 mention failure 均归零；236 项完整 Pytest、Ruff、121 source Mypy 通过，0 Provider 调用。v2.6 仍因成本与双写不切换。证据 `E-20260828-R1-GOLD-FIX-011`；确认来源：用户要求先修黄金集和评分器。
- 2026-08-28：通过 timicc 成功调用一次 `gpt-image-2`，medium、单候选、单图，32.364 秒；PNG 2,384,403 bytes，主要人物/服装/动作/环境/光照字段命中且未见文字水印。请求尺寸 1328×1328，实际返回 1024×1536，已作为 Provider 输出漂移写入 sidecar，候选保留但尺寸 Gate 不通过，未自动重试。证据 `E-20260828-R6-ALIYUN-009`；确认来源：用户本地保存 TIMICC_API_KEY 并要求立即测试。
- 2026-08-28：新增通用 `OpenAICompatibleImageProvider` 并注册 `timicc`，按 `POST /v1/images/generations` 请求 `gpt-image-2`；GPT Image base64 PNG 在同步提交返回前原子暂存为可恢复 hash 引用，不把大段图片写入数据库。Base URL/host/TLS、Prompt/尺寸、base64/PNG/hash、错误脱敏和凭据缺失均失败关闭；23 项定向、230 项完整 Pytest、Ruff、修改范围 Mypy 通过。TIMI CC 公开文档未列 Key 分组模型清单，且当前项目/进程尚未读到 `TIMICC_API_KEY`，故尚未发起付费 image2 调用。证据 `E-20260828-R6-ALIYUN-009`；确认来源：用户要求用 timicc 测试 image2 且 Provider 保持可插拔。
- 2026-08-28：完成 R1 v1 首轮真实 A/B；DeepSeek `deepseek-v4-flash` 在 31 seed + 6 real 上完成 74/74 调用、242,288 tokens。v2.5 seed 13/7/11，v2.6 12/7/12；v2.6 recall 略高但 tokens +27.9%、deferred 6→21、asserted/deferred 双写 3→6，不切换。归因确认黄金/评分至少影响 7 seed 与 5 real，同时模糊 owner、估龄绕过、coverage、earring alias、排他双写和手持物污染为独立系统缺陷。v1 暂不能作为发布硬 Gate，下一步先修测量层并离线重评。证据 `E-20260828-R1-GOLD-RUN-010`；确认来源：用户要求跑一次判断错误来源。
- 2026-08-28：新增 `canonical-zh:canonical-zh-character-v1` 可插拔 PromptRenderer，将六类字段确定性翻译为自然中文并保存 24 条逐短句 provenance；修复官方共享 DashScope `/api/v1` 重复拼接和域名白名单。225 项完整 Pytest、Ruff、7 个修改源文件 Mypy 通过；用 `qwen-image-plus` 成功生成 1328×1328 单图并完成人工视觉初检。数据库 approved/locked Profile 为 0，故产物只标记 `Baseline Candidate v1`，批量与 baseline 锁定继续关闭。证据 `E-20260828-R6-ALIYUN-009`。
- 2026-08-28：完成 R1 黄金集 v1；旧 25-case v0 原样保留，新默认 31-case/40 required/3 allowed/17 forbidden，6 个真实 Chunk 增加 15 required/11 forbidden 的 source-backed 非穷尽审计标注；mention/deferred/temporal、重复和 asserted/deferred 双写进入评分。21 项定向、225 项完整 Pytest、Ruff、Mypy src 通过；v0 旧报告重放成功，0 真实调用。历史 v0 指标不可与 v1 横比，下一步用 v1 重建真实 A/B 基线。证据 `E-20260828-R1-GOLD-008`；确认来源：用户明确要求更新黄金测评集。
- 2026-08-28：可插拔 Provider 契约补齐同步与异步两种市场接口；同步 `artifact_refs` 和异步 `task_id` 均先进入 ExternalOperation 再推进统一状态机，新增 `c4b8a7d219e1` 并通过 upgrade/downgrade/upgrade、20 项定向和 211 项完整回归。真实首图仍待阿里云凭据。证据 `E-20260827-R6-ALIYUN-009`。
- 2026-08-28：本地应用数据库已实际升级到 `c4b8a7d219e1 (head)`；首张候选图运行条件只剩 `DASHSCOPE_API_KEY` 与地域 Workspace URL，仍未发起收费调用。证据 `E-20260827-R6-ALIYUN-009`。
- 2026-08-27：R6 生图 Provider 升级为注册表式可插拔架构；Worker 移除供应商分支，Provider ID/模型版本进入图片评测元数据，新增适配器不改业务状态机；未知/重复/身份不一致均失败关闭。20 项定向、211 项完整 Pytest、Ruff、Mypy 通过。真实阿里云首图仍待 Key/Workspace URL。证据 `E-20260827-R6-ALIYUN-009`。
- 2026-08-27：完成 R1 Prompt v2.5/v2.6 三轮真实 DeepSeek A/B；130 次调用、426,190 recorded tokens、0 Schema 失败。最终轮两组 TP/FP/FN 同为 16/4/1，B 的 pass/review/fail 由 3/5/3 改善为 5/3/3、年龄信号由 1/5 改善为 3/3，但 token 52,683→67,407，deferred 4→22、warning 32→54、拒绝 27→31，并在多人样例重复/双写，因此默认保留 v2.5；v3.4 确定性安全门禁保留。49 项定向、203 项完整 Pytest、Ruff、Mypy 通过。证据 `E-20260827-R1-PROMPT-AB-007`；确认来源：用户明确授权发送指定 Chunk 给 DeepSeek。
- 2026-08-27：并行完成 R6 生图规格 Mock 纵向切片；目标字段适配为带 block/provenance 的 `ResolvedCharacterRenderFields`，draft 场景简报、三档 readiness、Provider 中立 spec/hash 和 Mock 提交恢复进入主链；普通请求不能自批一致性场景，提交未知禁止盲重提。6 项定向、202 项完整 Pytest、Ruff、Mypy 通过；未接真实字段、收费 Provider、审计/gate/baseline，不改变批量生图禁令。证据 `E-20260827-R6-IMAGE-SPEC-008`。
- 2026-08-27：完成 R1 基础数据生产修复；四类 mention 与旧标签兼容、`age.age`/未知 age 子路径、全 clothing 语义门禁、精确/软规范/唯一单字漏写定位及结构化审计进入主链。R1 基线 7/7 转绿，154 项单元与 193 项完整 Pytest、Ruff、Mypy 通过；未运行真实 Provider，下一步新 Run 复核。证据 `E-20260827-R1-DATA-006`。
- 2026-08-27：将短文本质量回归拆为 R1/R2 两个任务；当前任务冻结 R1 v1 基线，7 个通用 case 中 3 passed / 5 strict-xfailed，相关 R1 回归 28 passed / 5 xfailed，完整回归 175 passed / 5 xfailed，Ruff 通过。完整回归首次受系统临时目录权限阻断，改用项目专用 basetemp 后通过。生产修复和真实 Provider 复测未开始；R2 基线已交由从当前 working-tree 快照创建的独立 Codex 任务。证据 `E-20260827-R1-BASELINE-005`。
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
