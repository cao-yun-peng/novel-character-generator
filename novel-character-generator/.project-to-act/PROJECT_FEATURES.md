# 项目功能

> 功能范围与状态的唯一清单。功能变化后同步进度；未验证的功能不得标记为已完成。

## 状态定义

- 候选：尚未批准进入范围
- 已规划：已确认但未开始
- 进行中：正在实现
- 已阻塞：等待外部条件
- 已完成：完成条件已满足且有证据
- 已取消：明确退出范围并保留原因

## 功能清单

| 功能 ID | 功能 | 优先级 | 状态 | 依赖 | 完成条件 | 证据 ID |
|---|---|---|---|---|---|---|
| F-PIPELINE-V2-001 | 质量优先的专用模型语义流水线 V2 | P0 | 进行中；M1 真实基线未过，M2 关闭 | F-R1-001、F-R1-002、F-R2-001、F-R3-001、F-OBS-001 | M1 全 Chunk、M2 载体、M3 身份重开、M4 scene/event、M5 分组复核及条件 Schema；联合质量/覆盖/人工容量 Gate；离线回放、shadow、真实跨作品 Gate 与 V1 回滚通过 | E-20260828-PIPELINE-V2-DESIGN-012-R1、E-20260828-PIPELINE-V2-M1-013-REAL1 |
| F-PIPELINE-V2-M1-001 | M1 局部观察发现 shadow/offline 纵向切片 | P0 | 工程 Gate 通过；真实模型质量 Gate 不通过 | F-PIPELINE-V2-001 | 修复 age fact/signal、presentation 与 unresolved；draft2 用户审核和新 held-out 通过；不写 Observation、不接管 V1 | E-20260828-PIPELINE-V2-M1-013、E-20260828-PIPELINE-V2-M1-013-REAL1 |
| F-R6-002 | 可插拔 PromptRenderer/真实生图 Provider 与跨模型单图 smoke | P0 | DashScope 与 timicc/image2 首图完成，待可信图片 Gate | F-R6-001、Provider/Renderer registry、各 Provider 凭据 | 新供应商/Renderer 不改状态机；自然 Prompt 逐句可追溯；同步/异步结果可恢复；每模型真实单图保存并独立评审 | E-20260828-R6-ALIYUN-009 |
| F-R6-001 | 期望字段到 Provider 中立生图规格 Mock 纵向切片 | P0 | 已完成基础，待真实字段接线 | approved Profile、Snapshot、Image Run/ExternalOperation | typed 字段/来源适配、strict brief、三档门禁、稳定 spec/context hash、Provider 只收 spec、submit unknown 失败关闭、完整回归通过 | E-20260827-R6-IMAGE-SPEC-008 |
| F-R2-004 | 收敛 record/token/mention 预算分片与 omission repair | P0 | 已完成，待真实校准复核 | F-R2-003、F-OBS-001 | 每 shard 四重预算有界、遗漏有限修复、耗尽显式警告、恢复不重跑、自动回归通过 | E-20260827-R2-SHARD-004-CAL1 |
| F-R2-003 | 十章收敛 Dirty Memory Frontier 与覆盖率 trace | P0 | 已完成 | F-R2-001、F-R2-002、F-OBS-001 | 仅 dirty 非稳定记录收敛、旧 unresolved 不重跑、完整 memory 保留、覆盖率与 omission 可见 | E-20260827-R2-FRONTIER-003 |
| F-R2-002 | 逐 Chunk 相关人物记忆裁剪与可观测性 | P0 | 已完成 | F-R2-001、F-OBS-001 | 模型上下文有界、完整 memory 保留、事件与 Inspector 可见、自动回归通过 | E-20260827-R2-MEMORY-002 |
| F-R1-001 | VisualCandidateExtractionResult v3 与服务端 evidence locator | P0 | 已完成 | 文本分块、Provider | v3 主链及失败路径自动测试通过 | 历史代码与测试 |
| F-R1-002 | 跨题材视觉抽取开发回归集 | P0 | 已完成 v1.1 测量修正，待 adapter/Prompt 修复 | F-R1-001 | 31 个通用硬黄金 case；required/allowed/forbidden、mention、deferred、temporal 确定性评分；6 个真实审计切片 | E-20260826-R1-EVAL-002、E-20260826-R1-PROMPT-003、E-20260826-R1-EVAL-004、E-20260828-R1-GOLD-008、E-20260828-R1-GOLD-FIX-011 |
| F-R1-003 | R1 提及/字段/证据质量红灯基线 | P0 | 已完成，已全部转绿 | F-R1-001、F-R1-002 | 独立版本化 fixture；历史缺失行为已转普通通过；既有安全边界保持通过；与 R2 身份基线分离 | E-20260827-R1-BASELINE-005、E-20260827-R1-DATA-006 |
| F-R1-004 | R1 基础数据规范化与证据门禁 | P0 | 已完成，待真实复核 | F-R1-003、F-R2-001 | 四类 mention、age/clothing 失败关闭、精确原文与修复审计、旧标签兼容、自动回归通过 | E-20260827-R1-DATA-006 |
| F-R1-005 | R1 Prompt 可回滚 A/B 与 v3.4 确定性视觉门禁 | P0 | 已完成；v2.6 候选不切换 | F-R1-002、F-R1-004 | 冻结 v2.5、同链路真实样例 A/B、逐样例成本/质量报告、候选切换判定、默认回滚点与安全门禁回归通过 | E-20260827-R1-PROMPT-AB-007 |
| F-R2-001 | 人物实体逐章判断与十章收敛基础主链 | P0 | 已完成 | F-R1-001、PipelineStep 恢复 | 累计记忆、硬十章/尾批、final-only 写入、泛称隔离、同名支持、预算/指纹/迁移和自动回归完成 | E-20260827-R2-ENTITY-001 |
| F-R3-001 | 人物阶段与时间作用域解析基础主链 | P0 | 已完成 | F-R1-001、F-R2-001、Timeline、外观聚合 | 时间信号持久化、阶段/作用域解析、pending/final 门禁、审核修订 API、迁移和自动回归完成 | E-20260827-R3-PHASE-001 |
| F-OBS-001 | R1-R3 Run Inspector | P0 | 已完成 | F-R1-001、F-R2-001、F-R3-001、RunEvent | 阶段摘要、按需结构化产出详情、工作台可视化和敏感数据边界测试通过 | E-20260827-OBS-RUN-001 |
| F-OBS-002 | 开发环境模型原始响应查看器 | P0 | 已完成 | F-OBS-001、R1/R2 Provider、管理员鉴权 | R1/R2 raw 持久化与页签、生产门禁、迁移、权限和完整回归通过 | E-20260827-DEV-RAW-001 |

## 功能变更历史

按时间倒序追加：日期、功能 ID、变化、原因、影响、证据 ID 和确认来源。

- 2026-08-28：`F-PIPELINE-V2-M1-001` 完成首次真实开发基线。15/15 调用与结构契约成功，测量修正后 11 pass / 4 fail；事实召回/精度 86.7%/100%，temporal recall/precision 25%/25%。确认 age、presentation 和 unresolved 为模型/Prompt 真缺陷，M2 继续关闭；证据 `E-20260828-PIPELINE-V2-M1-013-REAL1`；确认来源：用户要求验证 M1 效果。

- 2026-08-28：新增 `F-PIPELINE-V2-M1-001`。M1 v1.1 DTO、服务端证据/引用门禁、OpenAI-compatible adapter、不可变 shadow artifact、15-case 用户审核集、三态评分器与离线 CLI 已实现；R1/R2/M1 合并重复结构化 Provider 底层并删除 docs Prompt 副本。251 项完整回归、Ruff、125 source Mypy 通过，0 Provider、0 路由/数据库变化。模型效果仍 blocked；证据 `E-20260828-PIPELINE-V2-M1-013`；确认来源：用户要求第一阶段逐节点开发、测试集人工把关并删除冗余。

- 2026-08-28：F-PIPELINE-V2-001 设计升级为 v1.1，修补入口筛选循环依赖、字段载体错绑、身份组件漏边/旧绑定重开、章内时间边界、M5 单条复核盲点、Schema 条件约束、低覆盖伪高精度、模型相关错误、数据保留与人工/运维容量。Stage 4 架构 Gate 条件通过，Stage 5 ready；未实现、未迁移、未调用 Provider。证据 `E-20260828-PIPELINE-V2-DESIGN-012-R1`；确认来源：用户要求修补项目文件。
- 2026-08-28：新增 F-PIPELINE-V2-001 设计。用户确认开放字段、身份、时间语义不应主要交给确定性规则，并把效果提升设为第一目标；因此 V2 采用五个单职责模型节点覆盖全部相关输入，增加 downgrade-only 联合复核，代码只保留证据/硬冲突/Promotion。当前仅形成设计、Prompt 和 Schema，不改变 V1 生产链；证据 `E-20260828-PIPELINE-V2-DESIGN-012`；确认来源：用户明确要求按质量优先目标重新规划。
- 2026-08-28：F-R6-002 完成 timicc `gpt-image-2` 单图真实 smoke，PNG/provenance 本地保存；内容字段整体命中，但请求 1328×1328 被返回为 1024×1536，记录为 Provider 尺寸漂移且不自动重试、不锁 baseline。证据 `E-20260828-R6-ALIYUN-009`；确认来源：用户完成本地 Key 配置后要求测试。
- 2026-08-28：F-R6-002 新增市场模型复用的 `OpenAICompatibleImageProvider` 与 `timicc/gpt-image-2` 注册项；同步 base64 结果先原子暂存后持久化引用，PromptRenderer/provenance 和 Worker 状态机保持不变。离线协议与完整回归通过，真实单图只等待本地安全环境变量生效。证据 `E-20260828-R6-ALIYUN-009`；确认来源：用户要求 Provider 可插拔并立即测试 image2。
- 2026-08-28：F-R6-002 增加版本化 PromptRenderer registry、自然中文字段翻译、逐短句 provenance 和 golden test；官方北京共享 URL 成功调用 `qwen-image-plus`，保存首张 1328×1328 PNG 与 Prompt sidecar。视觉初检命中主要字段，但具体脸部为模型补全且本地无 approved/locked Profile，因此保持候选态。证据 `E-20260828-R6-ALIYUN-009`；确认来源：用户要求实现 Renderer 并生成第一张图。
- 2026-08-28：F-R1-002 升级为 `visual-observation-seed-v3`；保留 25-case v0 历史基线，新默认 v1 为 31 个通用硬黄金 case，并给 6 个真实 Chunk 增加非穷尽审计约束。评分器独立处理 required/allowed/forbidden、mention/deferred/temporal，A/B 增加重复与 asserted/deferred 双写指标；225 项完整回归通过，0 真实调用。证据 `E-20260828-R1-GOLD-008`；确认来源：用户明确要求更新黄金测评集。
- 2026-08-28：F-R1-002 升级为 dataset v1.1 / rubric v3.1；修正首轮真实 A/B 暴露的测量假失败，并用 74 份保存 candidates 离线重评分。A/B seed pass 提升至 20/22，真实 mention failure 归零；排他双写改为硬失败。236 项完整回归通过，0 Provider 调用。证据 `E-20260828-R1-GOLD-FIX-011`；确认来源：用户要求先修黄金集和评分器。
- 2026-08-28：F-R6-002 补齐同步/异步双形态恢复；同步图片引用与异步任务 ID 都先持久化，新增 `c4b8a7d219e1` 迁移并完成往返验证，避免只适配任务型供应商。证据 `E-20260827-R6-ALIYUN-009`；确认来源：用户要求可实验市面其他模型。
- 2026-08-27：扩展 F-R6-002 为可插拔 Provider registry；Worker 移除供应商分支，Mock、DashScope 和后续市场模型共用 ImageRenderSpec/状态机/Artifact 链，结果记录 Provider 与版本，未知/重复/身份不符适配器失败关闭。211 项完整回归通过；真实首图仍待 Key/Workspace URL。证据 `E-20260827-R6-ALIYUN-009`；确认来源：用户要求 Provider 可插拔以实验市面模型。
- 2026-08-27：新增并完成 F-R1-005；Provider 可注入 Prompt/version 以复现同链路 A/B，冻结 v2.5 并保留阶段化 v2.6 候选；三轮真实实验判定 v2.6 不切换，默认仍为 v2.5，v3.4 的配饰/年龄/眼睛/肤色/面部/纹身确定性门禁与 deferred 分类保留。证据 `E-20260827-R1-PROMPT-AB-007`；确认来源：用户要求直接重构并用真实样例 A/B，随后明确授权发送指定小说 Chunk 给 DeepSeek。
- 2026-08-27：新增并完成 F-R6-001 基础；在 R1–R3 优化并行期间，以期望字段和 Mock 冻结身份/阶段/服装/表演/环境/美术/负向块及逐字段来源，保留真实输出适配缝；普通用户不能自批一致性场景，Provider 不读取原始业务上下文。证据 `E-20260827-R6-IMAGE-SPEC-008`；确认来源：用户要求并行启动生图阶段，后续接真实输出字段闭环。
- 2026-08-27：新增并完成 F-R1-004；R1 mention、age/clothing 字段与 evidence locator 的五项红灯全部进入生产链并转绿，R2 explicit_names 同步失败关闭；Schema/Prompt 升版，无迁移和额外调用。证据 `E-20260827-R1-DATA-006`；确认来源：用户要求进行开发。
- 2026-08-27：新增并完成 F-R1-003 的基线冻结；7 个通用 case 独立覆盖 descriptor、`age.age`、物品/服装语义和证据精确修复边界，5 项缺失行为以 strict xfail 固化，未修改生产链；R2 身份连续性移至独立任务。证据 `E-20260827-R1-BASELINE-005`；确认来源：用户要求拆分 R1/R2 基线并新开 R2 任务。
- 2026-08-27：校准 F-R2-004；历史覆盖退化样本驱动默认值由 128 mentions/24,000 input/6,000 output 调整为 16 records/32 mentions/12,000 完整请求 input/4,500 output，输入估算纳入 Provider Prompt/Schema 固定开销，工作台显示 record 与估算策略。证据 `E-20260827-R2-SHARD-004-CAL1`；确认来源：用户要求修改。
- 2026-08-27：完成 F-R2-004；dirty frontier 按完整 memory record 执行 mention/预计输入/预计输出预算分片，未安全覆盖记录有限 repair，耗尽后显式 warning 并安全 unresolved；RunEvent/Inspector/工作台可见全链路数量变化。证据 `E-20260827-R2-SHARD-004`；确认来源：用户确认执行并在中断后要求恢复。
- 2026-08-27：完成 F-R2-003；十章/尾批收敛只处理当前 dirty non-stable，旧 unresolved 保留但不重复提交；Provider 原始覆盖和 omission 可在 RunEvent/Inspector/工作台查看。证据 `E-20260827-R2-FRONTIER-003`；确认来源：用户要求继续下一步开发并说明完成功能与解决问题。
- 2026-08-27：完成 F-R2-002；逐 Chunk 模型上下文改为有界相关 memory 视图，运行时完整 memory 不丢失，RunEvent/Inspector/工作台可见裁剪与状态变化。证据 `E-20260827-R2-MEMORY-002`；确认来源：用户要求逐步修改并输出关键数据变化。
- 2026-08-27：完成 F-OBS-002；开发者可按 R1/R2 调用查看模型消息和完整 Provider 响应，普通接口不暴露，生产禁止启用。证据 `E-20260827-DEV-RAW-001`；确认来源：用户要求实时查看模型输出以便调整。
- 2026-08-27：完成 F-OBS-001；R1/R2/R3 运行信号与现有结构化业务产出已可通过 API 和工作台查看，保持“运行完成 ≠ 语义质量通过”的展示边界。证据 `E-20260827-OBS-RUN-001`；确认来源：用户要求按流程逐步推进开发。
- 2026-08-27：F-R1-001/F-R2-001/F-R3-001 完成一次同文本干净 run 反馈闭环：显式姓名跨人物门禁、年龄/字段语义门禁、年龄与转生阶段推导、transformation 暂态窄化、同事实去重和近义/多值冲突归一化均进入代码与自动回归。真实 run 后新增修复仍需下一干净 run 才能升总体质量 Gate。证据 `E-20260827-R123-REAL-001`；确认来源：用户要求按指定顺序开发并复测。
- 2026-08-27：新增 F-OBS-001，先复用业务审计表构建 R1-R3 Run Inspector；OpenTelemetry 与 Langfuse 延后为独立增量。原因：用户需要先直接看到阶段进度和产出效果；确认来源：用户要求逐步推进开发。
- 2026-08-27：新增并完成 F-R3-001 基础主链；R2 仅确定人物，R3 独立解析阶段/呈现/现实/形态/范围，final 才进入聚合。原因：人物身份归属无法替代时间作用域。影响：v3.1 时间信号、四张表、独立 Worker、审核 API 和聚合门禁；证据 `E-20260827-R3-PHASE-001`；确认来源：用户要求按讨论开发。
- 2026-08-27：新增并完成 F-R2-001 基础主链；身份语义全部交给逐章/收敛模型，代码只负责包构建、Schema/ID/证据校验、十章调度、预算、幂等和 final-only 物化。原因：按字符串复用 `representative_name` 会把局部泛称错误扩散到既有人物。影响：旧直接物化入口失败关闭；证据 `E-20260827-R2-ENTITY-001`；确认来源：用户要求按讨论流程开发。
- 2026-08-26：F-R1-002 的评测 rubric 升级到 v2，增加结构/value/evidence 分层与 pass/review/fail 三态；未知措辞不自动通过。证据 `E-20260826-R1-EVAL-004`，确认来源：用户要求修改评测器。
- 2026-08-26：F-R1-002 增加通用语义 Prompt v2.2 和逐 case 评测入口；不引入字段注册表。七类字段结构验证正确，保留等价字符串评分缺口。证据 `E-20260826-R1-PROMPT-003`，确认来源：用户要求按问题类别加强 Prompt。
