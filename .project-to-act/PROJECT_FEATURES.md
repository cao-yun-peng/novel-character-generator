# 项目功能

## 状态定义

- `completed`：工程与规定验证完成
- `in_progress`：正在开发或等待当前 Gate
- `planned`：仅有设计契约
- `blocked`：前置质量或用户审核未通过

## 功能清单

| ID | 功能 | 状态 | 说明 |
|---|---|---|---|
| F-V2-DESIGN-001 | N0–N11、M1–M5 总契约 | completed | 设计基线 v1.3；补充 owner 双向索引与 M4 单人物组包约束 |
| F-V2-M1-002 | M1 v1 局部观察发现 | completed | legacy 工程切片；5/6 仅保留历史诊断 |
| F-V2-N2-003 | N2 v1 本地事实定位 | completed | legacy grounding/context 工程切片 |
| F-V2-M2-004 | M2 v1 字段消歧 | completed | legacy 工程切片；draft1 暂停审核 |
| F-V2-M3-005 | M3 身份组件解析 | planned | 尚未实现 |
| F-V2-M4-006 | M4 时间与持续性解析 | planned | 尚未实现 |
| F-V2-M5-007 | M5 联合复核 | planned | 尚未实现 |
| F-CLEANUP-V2-008 | V2 仓库精简 | completed | 无关代码、文档、测试和缓存已删除 |
| F-ENV-ISOLATION-009 | 当前仓库独立运行 | completed | 包目录、editable 环境和验证均只引用唯一工作区 |
| F-V2-BOUNDARY-010 | M1/M2 v2 职责重划 | completed | M1 只召回证据；M2 统一局部语义解析 |
| F-V2-M1V2-011 | M1 v2 视觉证据发现 | completed | 主 Prompt 回退 v2.8；005 非唯一引文与少年脸貌为用户接受残余风险，条件 Gate 只授权继续开发，不授权 active 写入 |
| F-V2-N2V2-012 | N2 v2 证据固化 | completed | `GroundedEvidencePacket`、span/hash/context、stable ID/fingerprint、rejected/deferred 分流工程 Gate 通过；尚未接默认主链 |
| F-V2-M2V2-013 | M2 v2 局部视觉语义 | planned | semantic units、epistemic、signal 待实现 |

## 功能变更历史

- 2026-08-29：Prompt v2.8 将 owner 转换定义为候选硬边界，将同 owner 连续 profile/transformation/presentation 定义为复合候选，并约束覆盖复扫去重和排除纯动作；只更新 Dataset 的 Prompt 元数据，未修改金标、Rubric 或 Source Match Policy，未调用 Provider。
- 2026-08-29：经用户明确确认外发授权，Prompt v2.8 完成双集 Provider 回归：短集 16/0/0、真实集 2/5/3。009 连续 transformation 复合候选改善；用户复审确认 006/009 无问题，005 非唯一引文与少年脸貌仍待处理，未修改 Dataset/Rubric。
- 2026-08-29：按用户要求将 005 归因泛化为 Prompt v2.9：重复裸描述必须唯一性闭环，同一载体上的不同视觉谓词不得互相覆盖；未修改 Dataset/Rubric，未调用 Provider。
- 2026-08-29：用户授权完成 Prompt v2.9 双集 Provider 检查：短集 16/0/0、真实集 1/6/3。005 问题仍复现；007 为 Provider 完成长度异常，006/009 按用户审查不构成问题。
- 2026-08-29：经用户明确授权，Prompt v2.7 使用当前外部 Provider 完成 26 条双集回归；短集保持 16/0/0，真实集仍为 2/6/2。005 唯一定位与月白衣袍跨度改善但仍漏两项，008 修复为 review，009 因复合 transformation 被原子化而回归为 fail。
- 2026-08-29：将真实集 005/008 归因为 evidence 自身非唯一、并列/转折视觉谓语截断和动作/对话内短视觉线索漏扫；Prompt v2.7 固化“语义边界→定位边界→逐子句覆盖复扫”，不修改金标、Rubric 或 Source Match Policy，未调用 Provider。
- 2026-08-29：短集升级为 v2.3-draft，接受 short-003 的完整人物短语；真实集升级为 v2.5-draft，补全 003/004/008/009 的局部 owner alias 和 008 的完整年龄发辫跨度。复用 Prompt v2.6 现有 outputs 离线重评分为 16/0/0 与 2/6/2，未调用 Provider。
- 2026-08-29：Source Match Policy v2 将仅空白差异唯一映射回原始 Chunk 切片，非空白文字和标点继续严格校验；Artifact 对格式回填记录 warning 并按回填输出计算 fingerprint。Rubric v2.5 的 forbidden 只拦截未匹配有效金标的纯额外候选。
- 2026-08-29：按人工审查允许一条逐字唯一候选覆盖相邻多个金标，按实际候选而非金标数计算 precision；005 接受月白衣袍候选内的“老者/老人”局部 alias；真实案例 010 暂不因服饰引文附带兵器/坐骑而失败。Prompt v2.6 增强 presentation 召回和人物定位起点保留。
- 2026-08-29：Rubric v2.4 增加跨 owner alias 冲突校验、单候选多金标错误和 evidence quote 唯一定位 fidelity；真实集补全已观察到的有效 owner alias/跨度，回到 draft 等待审核。
- 2026-08-29：真实运行器遇到 deterministic validation failure 时改为保留失败输出、reason code、usage 与指纹并继续剩余样本；评分器仍直接判 fail，避免单条失败导致整批无工件。
- 2026-08-29：真实集 v2.3-draft 将青衫管家与月白衣袍客人拆成不同局部 owner，移除歧义泛称“老者”，新增青衫老者视觉证据样例；Prompt、Rubric 与短集不变。
- 2026-08-29：Prompt v2.5 明确否定外貌召回、语义完整优先级和 owner 正向识别约束；approved 短集真实诊断由 v2.2 的 14/16 提升到 16/16，完整 M1 Gate 仍等待真实 Chunk。
- 2026-08-29：用户批准 16 条短金标；Prompt v2.2 首次 approved 真实诊断为 14/16，工程切片保持 completed，但质量 Gate 因两条召回/跨度失败仍未通过。
- 2026-08-29：M1 v2 测量契约升级到 v2.2：引文必须最小但语义完整且可由 N2 唯一定位；owner 评测拆为 required/allowed/must_be_null；真实运行接入 deterministic validation 和可哈希 run manifest。
- 2026-08-28：确认 M1/N2 局部 owner 经 M3 物化为版本化 `OwnerBinding`；Chunk owner 元数据仅为可重建多值缓存，人物方向索引用于 N6/M4；M4 只接受单人物观察批次。
- 2026-08-28：确认 M1 只召回视觉相关证据，删除分类/原子化职责；M2 接管局部语义单元、字段、认知状态和显式信号。旧 v1 切片保留为历史实现，不作为 v2 Gate。
- 2026-08-28：修正 `src/novel_character_generator` 包布局，切断旧仓库 editable 引用并删除旧项目目录。
- 2026-08-28：移除与当前 V2 无关的运行能力，只保留 M1/N2/M2 和后续节点设计。
