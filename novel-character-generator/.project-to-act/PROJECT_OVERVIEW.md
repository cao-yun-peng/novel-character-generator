# 项目总览

> 每次新工作会话默认只读取本文件。首次维护时补充真实信息；路线变化后立即同步。
> 本目录不得记录密钥、令牌、完整个人信息或未脱敏工具输出。

## 基本信息

- 项目名称：Novel Character Generator
- 项目 ID：novel-character-generator
- 项目负责人：用户（产品决策）/ Codex（当前实施）
- 风险等级：L1 内部开发
- 当前阶段：5. 具体功能开发（M1 shadow/offline 工程 Gate 已通过，模型效果测试集待用户审核）
- 当前状态：`PIPELINE-V2-M1-013` awaiting user review；V1 生产链不变，M2 未启动
- 最后更新：2026-08-28

## 项目目标

- 面向不同题材小说，从原文中低成本、可追溯地抽取角色视觉事实，并形成可用于人物一致性出图的结构化证据。

## 范围

### 包含

- 小说文本导入、v3 视觉候选抽取、服务端证据定位、视觉事实持久化、开发评测集及后续外观聚合。

### 非目标

- 不从单一作品推导特例规则；不在开发阶段为已淘汰的 v2 发起新付费调用；本阶段不宣称达到生产发布质量。

## 技术路线与关键约束

- 语义流水线 V2 将开放语义拆给专用模型节点：局部命题、字段语义、人物身份、时间/持续性和激活前联合复核；确定性代码只负责 evidence、Schema/ID、硬冲突、状态机、Promotion 权限与持久化。
- 模型输出视为不可信候选；非规范字段、推断事实、无法定位证据、人物未决、作用域未决和跨节点不一致均失败关闭。端到端人物档案质量优先于首轮成本下降，成本/延迟仍需硬预算和完整观测。

## 数据与安全边界

- 数据分类：本地小说测试文本与模型诊断输出；真实调用会把选定分块发送给已配置的付费 Provider。
- 敏感信息处理：只记录脱敏摘要、证据 ID 和受控位置，不粘贴原始敏感数据。

## 当前焦点

- 下一里程碑：用户审核 M1 15-case 测试集；批准并授权后运行 M1 真实模型效果评测，按逐 case 错误决定修 Prompt/模型配置/契约还是进入 M2。
- 当前工作重点：保持 M1 单职责和 V1 shadow 隔离；先冻结 M1 的 raw fact、owner、epistemic、temporal 与污染边界，不用最终字段或身份指标反向扩宽 M1。
- 主要阻塞：M1 数据集尚未获用户批准、尚无真实模型输出；promotion coverage 与人工 review capacity 仍需后续端到端 P0 数据冻结；数据库仍无 `approved/locked` 角色档案。

## 按需读取索引

| 当前任务 | 追加读取 |
|---|---|
| 规划、实施、阻塞处理 | `PROJECT_PROGRESS.md` |
| 新增、修改、删除功能 | `PROJECT_FEATURES.md`；实施时同时读进度 |
| 版本号、发布、升级、兼容性 | `PROJECT_VERSIONS.md` |
| 测试、交付、完成声明 | `PROJECT_ACCEPTANCE.md` |
| 跨领域路线变更或一致性审计 | 全部文件 |

## 路线变更记录

按时间倒序追加：决定 ID、日期、决定、原因、影响、证据 ID、确认来源和复审条件。

- 2026-08-28，`D-PIPELINE-V2-M1-013`：第一阶段从总体 P0 缩成 M1 单节点 shadow/offline 纵向切片；每个模型节点必须先建立独立测试集并经用户审核，之后才允许真实效果评测或启动下一节点。R1/R2/M1 共用结构化 Provider 传输层，删除重复 Prompt 和重复调用循环，但保留仍承担生产/回滚职责的 V1 代码与历史测试。原因：用户要求按输入输出逐步构建、效果由测试集把关并清理冗余；影响：M1 工程 Gate 通过，模型质量 Gate blocked，V1 Worker/数据库/默认 Prompt 不变；证据 `E-20260828-PIPELINE-V2-M1-013`；复审条件为用户批准 `m1-local-observation-v1-draft1`。

- 2026-08-28，`D-PIPELINE-V2-DESIGN-012-R1`：用户确认 V2 总体流程后，按复核结果升级为 `semantic-pipeline-v2-design-v1.1`；M1 默认覆盖全部有效 Chunk，M2 增加载体语义单元，M3 增加组件召回/旧绑定 supersede，M4 增加 scene/event 起止，M5 改为人物+作用域分组复核，并补齐输入/输出条件 Schema、联合 precision/coverage Gate、模型/数据/人工容量/运维边界。原因：旧稿可能在入口漏召回、逐条复核看不到全局冲突、章节粒度不足且 Schema 不能强制条件不变量；影响：生命周期从 Stage 5 回退 Stage 4 完成条件架构 Gate后，Stage 5 恢复为 ready，生产实现与 V1 均未改变；证据 `E-20260828-PIPELINE-V2-DESIGN-012-R1`；确认来源：用户要求修补项目文件；复审条件为 P0 离线数据与阈值冻结。
- 2026-08-28，`D-PIPELINE-V2-DESIGN-012`：R1-R3 后续优化从继续扩写单一 Prompt 改为质量优先的专用模型语义链；M1-M5 分别负责局部命题、全量字段语义、全量相关身份证据组件、全量稳定人物时间/持续性和 downgrade-only 联合复核，确定性代码只保留证据/硬约束/Promotion。原因：开放语义多样性不能由关键词/字符串规则主导，且既有 A/B 与真实 Run 证明宽职责模型和错误传播是主要瓶颈；影响：首轮不以 token 下降作为前置 Gate，先做 P0 零付费离线回放，再分节点 A/B 与 shadow；证据 `E-20260828-PIPELINE-V2-DESIGN-012`；确认来源：用户明确要求先把效果提升作为目标，复审条件为用户评审设计与 P0 阈值。
- 2026-08-28，`D-R1-GOLD-RUN-010`：v1 首轮真实 A/B 后，不直接根据当前 pass/fail 调 Prompt；先修黄金/评分的阶段键、temporal、safe deferred、owner alias、raw mention 和真实标注，再对同一报告离线重评分，然后修 adapter 与剩余 Prompt。原因：74 次运行同时证明测量假失败和独立系统缺陷，v2.6 还增加 27.9% tokens 与双写；影响：v1 暂不作为发布硬 Gate，生产 Prompt 保持 v2.5，不立即再次全量付费调用；证据 `E-20260828-R1-GOLD-RUN-010`；确认来源：用户要求实际运行以判断错误来源，复审条件为测量层修正后的离线重评分。
- 2026-08-28，`D-R1-GOLD-008`：保留 25-case v0 只用于历史复现，默认评测切到 31-case v1 / `visual-observation-seed-v3`；合成 case 为穷尽硬黄金，6 个真实 Chunk 使用 source-backed 非穷尽审计切片并显式计数未标注输出。原因：旧黄金与当前服装/字段契约冲突，且未评分 mention/deferred/temporal；影响：历史 A/B 指标不可与 v1 横比，生产 Prompt 不变，下一次 Prompt 决策需在 v1 上重建真实基线；证据 `E-20260828-R1-GOLD-008`；确认来源：用户明确要求更新黄金测评集。
- 2026-08-28，`D-R1-GOLD-FIX-011`：默认评测升级为 dataset v1.1 / rubric v3.1；只允许黄金逐项声明 owner/surface 同义称谓和安全 deferred，不执行自动身份绑定；temporal 重复只计量，而 asserted/deferred 双写为硬失败。原因：首轮 74 次真实 A/B 证明旧评分混入测量假失败；影响：原 candidates 可离线重评分，生产 Prompt 继续保持 v2.5，下一增量转向 adapter/Prompt 真缺陷；证据 `E-20260828-R1-GOLD-FIX-011`；确认来源：用户要求先修黄金集和评分器。
- 2026-08-27，`D-R1-PROMPT-AB-007`：冻结 v2.5 并以同链路执行 v2.6 三轮真实 DeepSeek A/B；v2.6 因成本约增加 28%、deferred/warning/拒绝增加及多人样例重复而不切换，生产/default 保持 `visual-extraction-prompt-v2.5`，向后兼容的 `visual-observation-v3.4` 确定性安全门禁保留。原因：用户允许效果好时全量重构，但要求用真实样例验证；影响：130 次调用、426,190 recorded tokens，无迁移，不改变 R2/R3 总体 Gate；证据 `E-20260827-R1-PROMPT-AB-007`；确认来源：用户明确授权发送指定小说 Chunk 给 DeepSeek，复审条件为新的候选 Prompt/模型/Schema 或评测规则变化。
- 2026-08-27，`D-R6-IMAGE-SPEC-008`：在 R1–R3 真实字段继续优化期间，并行以期望字段契约完成 Mock 生图规格链；用 `ResolvedCharacterRenderFields` 隔离上游适配，Provider 只消费冻结 `ImageRenderSpec`。原因：提前验证分层、来源、hash、门禁和恢复，不让真实字段接线阻塞生图工程；影响：仅开放 concept Mock 联调，不改变 `R123-REAL-001` 禁止批量生图结论，不接收费 Provider；证据 `E-20260827-R6-IMAGE-SPEC-008`；确认来源：用户明确要求并行启动生图阶段，待前面优化后接真实字段闭环。
- 2026-08-27，`D-R1-DATA-006`：R1 mention 类型统一为 `explicit_name/descriptor/pronoun/unknown`，旧标签仅在输入边界保守归一化；字段和证据采用确定性失败关闭门禁。原因：泛称混入显式姓名、错层 age、非衣物服装事实和不精确引文会污染后续身份与画像；影响：Schema/Prompt 升版，无数据库迁移和额外模型调用，R2 仅同步 explicit_names 边界；证据 `E-20260827-R1-DATA-006`；确认来源：用户明确要求开发第二阶段 R1 基础数据修正。
- 2026-08-27，`D-R1R2-BASELINE-005`：短文本复测回归基线拆为两个任务；当前任务只冻结 R1 提及类型、字段语义和证据定位，R2 跨 Chunk 身份解析在独立 Codex 任务中冻结。原因：候选抽取质量与身份归并属于不同责任层，混合断言会掩盖失败来源；影响：新增 R1 独立 v1 fixture 与 strict-xfail 红灯，不修改生产实现；证据 `E-20260827-R1-BASELINE-005`；确认来源：用户明确要求“一个关于 R1，新开一个关于 R2”。
- 2026-08-27，`D-R2-SHARD-004-CAL1`：R2 收敛分片由三重预算升级为 record/mention/完整请求预计输入/预计输出四重预算，默认值校准为 16/32/12,000/4,500；真实 Provider 的 Prompt/Schema 固定开销进入输入估算。原因：历史 Run 在 35 mention 时 100% 覆盖，但 46/48 mention 时仅覆盖 15/6，证明原 128 mention 默认值不安全且遗漏不等同于输出截断；影响：分片策略升为 v2，增加调用概率以换取覆盖可靠性，stable context 检索仍为后续缺口；证据 `E-20260827-R2-SHARD-004-CAL1`；确认来源：用户要求按失败教训修改。
- 2026-08-27，`D-R2-SHARD-004`：dirty frontier 增加 mention/预计输入/预计输出三重预算分片；Provider 未安全覆盖的完整 memory record 最多 repair 两轮，耗尽后保守 unresolved 并显式警告。原因：用户确认继续执行单 frontier 容量治理和 omission repair；影响：保持十章边界、dirty frontier、完整 memory 与 final-only 物化，不在本增量实现 stable context 检索或文末历史 sweep；确认来源：用户明确“可以执行”。
- 2026-08-27，`D-R2-FRONTIER-003`：十章收敛改为 dirty memory frontier；仅包含当前批次 mention 的非 stable 记录需要重新决策，未变化历史 unresolved 保留但延后。原因：真实长文本 run 中旧 unresolved 被每批重复提交，放大输入和强制输出规模；影响：保持固定批次、完整 memory 和 final-only 物化，不在本增量做分片或 omission repair；确认来源：用户要求继续下一步开发并说明解决的问题。
- 2026-08-27，`D-R2-MEMORY-002`：R2 从“逐 Chunk 输入完整累计 memory”改为“完整 memory 持久保留、模型上下文按相关性有界选择”，并把裁剪前后计数写入现有 RunEvent/Inspector。原因：《牧神纪》20 章真实 run 暴露累计 memory 与待决提及共同膨胀；影响：先修改逐 Chunk 上下文，不改变十章收敛与 final-only 物化；确认来源：用户要求逐步修改并查看关键数据变化。
- 2026-08-27，`D-DEVRAW-001`：原始模型响应采用开发环境显式开关、业务表旁路字段和独立管理员端点；覆盖 R1/R2，R3 代码阶段不伪造响应，生产配置失败关闭。原因：需要直接比较模型输出与后续 Schema/grounding/identity 门禁，同时避免扩大普通 Inspector 和日志的数据边界。影响：新增 `DEV-RAW-001`，数据库 head 升为 `f9a1e5c72d30`；确认来源：用户要求实时查看模型输出以便调整。
- 2026-08-27，`D-OBS-001`：可观测性按三步推进：先做业务 Run Inspector，再做 OpenTelemetry 运行时关联，最后接入 Langfuse LLM/eval 视图。原因：当前 R1-R3 产出已落业务库但缺统一可视化，直接先上外部 trace 后端不能解决阶段效果读取；影响：新增 `OBS-RUN-001`，暂不引入新依赖或迁移；确认来源：用户要求按讨论流程逐步开发。
- 2026-08-27，`D-R3-001`：R3 定义为独立的人物阶段与时间作用域解析层；R2 只写 pending Observation，R3 final 才激活，`needs_review` 失败关闭。原因：人物归属不能回答前世/今生、梦境、时间跳跃和形态变化的作用范围。影响：抽取 Schema 升级 v3.1，新增四张表、独立 Worker 步骤、审核/修订 API 和聚合门禁；证据 `E-20260827-R3-PHASE-001`；确认来源：用户要求按讨论开发。
- 2026-08-27，`D-R2-001`：R2 改为“每个有候选的 Chunk 一次模型身份判断 + 每 10 Chunk 固定一次收敛 + 文末尾批”；不增加重复模型复核，只有 final 绑定生成 Observation。原因：用户接受模型逐次语义判断，但要求杜绝泛称字符串规则造成跨人物污染。影响：新增实体解析契约、持久化表、迁移、调用预算和恢复门禁；证据 `E-20260827-R2-ENTITY-001`；确认来源：用户连续讨论并明确要求实施。
