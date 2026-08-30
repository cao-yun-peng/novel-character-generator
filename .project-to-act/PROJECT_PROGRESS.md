# 项目进度

## 当前任务

| 任务 | 状态 | 结果 |
|---|---|---|
| PIPELINE-V2-DESIGN-012 | completed | V2 总契约与 Schema 完成 |
| PIPELINE-V2-M1-013 | completed | 工程完成，模型质量 5/6 |
| PIPELINE-V2-N2-014 | completed | grounding/context 工程 Gate 通过 |
| PIPELINE-V2-M2-015 | completed | legacy v1 离线工程 Gate 通过；draft1 审核已被 v2 重标任务取代 |
| CLEANUP-V2-016 | completed | 仓库和项目账本精简为 V2 单一路线 |
| ENV-ISOLATION-017 | completed | 当前仓库可独立导入、测试和静态检查；旧项目目录已删除 |
| REPO-PUBLISH-018 | completed | 独立历史分支 `v2-semantic-pipeline` 已推送并跟踪 GitHub remote |
| PIPELINE-V2-BOUNDARY-019 | completed | M1/N2/M2 v2 职责、目标 Schema、评测和迁移 Gate 已更新 |
| PIPELINE-V2-M1V2-020 | completed | M1 v2 Prompt、Schema、Provider、不可变 Artifact、15 条 draft 评测与离线评分完成 |
| PIPELINE-V2-OWNER-021 | completed | owner 双向索引与 M4 单人物组包契约完成 |
| PIPELINE-V2-M1-EVAL-022 | completed | Prompt/Dataset/Rubric v2.2、三态 owner、确定性真实运行器与 10 个 source-backed Chunk 完成 |
| PIPELINE-V2-M1-SHORT-GATE-023 | completed | 用户批准 16 条短金标；Prompt v2.2 真实诊断 14/16，2 条失败已分类 |
| PIPELINE-V2-M1-PROMPT-024 | completed | Prompt v2.3–v2.5 受控迭代；v2.5 在 approved 短集真实诊断 16/16 |
| PIPELINE-V2-M1-REAL-OWNER-025 | completed | 真实集 v2.3-draft 将青衫管家与月白衣袍客人拆为独立 owner，并新增青衫老者金标 |
| PIPELINE-V2-M1-REAL-GATE-026 | completed | 用户批准真实集 v2.3；Prompt v2.5 真实诊断 0 pass / 1 review / 9 fail，Gate 未通过且发现测量有效性问题 |
| PIPELINE-V2-M1-EVAL-V24-027 | completed | Dataset/Rubric v2.4-draft 修复测量有效性；同一 outputs 离线重评分为 0 pass / 5 review / 5 fail |
| PIPELINE-V2-M1-BOUNDARY-028 | completed | 按人工复核修正 004/005/008/010 边界并升级 Prompt v2.6；同一 outputs 离线重评分为 1 pass / 5 review / 4 fail |
| PIPELINE-V2-M1-V26-GATE-029 | completed | Source Match Policy v2 与 Rubric v2.5 完成；Prompt v2.6 短集 15/16，真实集 2 pass / 3 review / 5 fail，发现新测量缺口 |
| PIPELINE-V2-M1-DATASET-030 | completed | 短集 v2.3-draft、真实集 v2.5-draft 完成；现有 outputs 离线重评分为 16/0/0 与 2/6/2 |
| PIPELINE-V2-M1-PROMPT-031 | completed | 归因 005/008 并升级 Prompt v2.7；工程回归通过，尚未调用 Provider |
| PIPELINE-V2-M1-V27-GATE-032 | completed | Prompt v2.7 双集回归完成：短集 16/0/0，真实集 2/6/2；008 修复、005 未完全修复、009 回归 |
| PIPELINE-V2-M1-PROMPT-033 | completed | Prompt v2.8 修正跨 owner 混绑与同 owner 连续外观原子化；工程验证通过，尚未调用 Provider |
| PIPELINE-V2-M1-V28-GATE-034 | completed | Prompt v2.8 双集回归完成：短集 16/0/0，真实集 2/5/3；009 transformation 改善，005 仍有非唯一引文，006/009 暴露 alias/跨度缺口 |
| PIPELINE-V2-M1-PROMPT-035 | completed | Prompt v2.9 泛化修正重复裸描述唯一定位与同载体视觉 cue 覆盖；工程验证通过，尚未调用 Provider |
| PIPELINE-V2-M1-V29-GATE-036 | completed | Prompt v2.9 双集 Provider 检查完成：短集 16/0/0，真实集 1/6/3；005 仍复现非唯一引文，007 有 Provider finish_length，006/009 按用户审查不构成问题 |
| PIPELINE-V2-M1-CONDITIONAL-GATE-037 | completed | 主 Prompt 回退 v2.8；005 由用户接受为残余风险，历史分数保持原样；96 项回归与静态检查通过 |
| PIPELINE-V2-N2V2-038 | completed | N2 v2 GroundedEvidencePacket、span/hash/context 与 rejected/deferred 分流工程 Gate 通过 |

## 阻塞项

- M2 v2 目标协议尚未实现；legacy M1/N2/M2 v1 仍供旧链回放。N2 v2 工程 Gate 已通过，但尚未接入默认主链。
- 短集 v2.3-draft 与真实集 v2.5-draft 已修正审计确认的 alias/跨度，均因金标变更等待用户复审。
- Rubric v2.4 按人工复核允许逐字长候选覆盖相邻多个金标，并移除真实案例 010 的兵器/坐骑混入 forbidden；同一 v2.3 outputs 离线重评分为 1 pass / 5 review / 4 fail，004/005/006/008 仍为 fail，M1 完整 evidence Gate 未通过。
- v2.4 Rubric 回放 approved 短集仍为 16/16，未破坏短基线。
- Prompt v2.7 新运行短集保持 16/0/0；真实集仍为 2/6/2。005 不再有非唯一引文且月白衣袍完整跨度已命中，但少年脸貌与青衫管家服饰仍漏；008 已修复为 review；009 因复合 transformation 被拆成多个小候选而回归为 fail。
- Prompt v2.8 已按上述 005/009 根因完成候选颗粒度修正并完成授权双集运行；不能将 v2.7 outputs 当作 v2.8 结果，当前真实集仍有 005、006、009 缺口。
- Prompt v2.8 已完成授权后的双集运行：短集 16/0/0，真实集 2/5/3。009 的连续 transformation 已改善；用户复审确认 006/009 不构成问题，当前仅 005 仍有非唯一引文与少年脸貌召回缺口，M1 Gate 仍未通过。
- Prompt v2.9 历史检查仍记录短集 16/0/0、真实集 1/6/3；用户已决定回退主 Prompt v2.8，并以条件 Gate 接受 005 残余风险。该决定只解除 N2 开发前置，不改变历史评分，也不授权 active 写入。
- M3–M5 尚未实现，端到端 Promotion Gate 不具备执行条件。
- `.project-to-act/AGENT_LIFECYCLE.json` 为既有无效 revision 1（早期阶段状态、产物路径与转换历史不符合当前 Skill Schema）；本轮未手改 revision，因此不能记录新的生命周期阶段转换，但不影响已保存的 Stage 5 工程任务证据。

## 下一步

1. 设计并实现 M2 v2，使其只消费 N2 `grounded_candidates`；`deferred_items` 不进入语义解析或 active 状态。
2. 保持 Dataset 金标、Rubric v2.5 与 Source Match Policy v2 固定；Prompt 主版本保持 v2.8，不再为 005 追加规则。
3. 建立一次性 M1→N2→M2 shadow 集成 Gate，验证 rejected/deferred 不越权进入下游。
4. 007 的 Provider finish_length 作为独立稳定性风险保留，下一次真实 Provider Gate 单独处理。

## 进度历史

- 2026-08-29：用户决定主 Prompt 回退 v2.8，并将 005 非唯一逐字引文与少年脸貌漏召回作为已接受残余风险；历史 v2.8/v2.9 分数保持原样，M1 以条件 Gate 解除 N2 开发前置。N2 v2 已实现唯一引文 span/hash/context 固化、重复引文 deferred 和非逐字引文 rejected；尚未完成全量 Gate。

- 2026-08-29：根据 v2.7 真实案例 005 的跨 owner 混绑和 009 的同 owner transformation 原子化，将 Prompt 升级为 v2.8：owner 转换作为候选硬边界，同一人物连续外观事件保持复合跨度，覆盖复扫只查漏且不得产生重复或纯动作候选。Dataset 仅更新被测 Prompt 元数据，金标/版本、Rubric 和 Source Match Policy 不变；未调用 Provider。
- 2026-08-29：用户明确确认外发授权后完成 Prompt v2.8 双集回归：短集 16/0/0，真实集 2/5/3。009 的前三段连续 transformation 已按复合跨度召回；005 仍有非唯一“青衫老者”引文，006 的相对年龄“这位”跨度与 009 的“那怪物”owner alias 暴露 Dataset 口径缺口。M1 Gate 未通过。
- 2026-08-29：根据用户要求不做案例特化，将 005 的重复裸描述与同载体不同视觉 cue 根因泛化为 Prompt v2.9 规则；Dataset 金标/版本、Rubric 和 Source Match Policy 不变，未调用 Provider。
- 2026-08-29：用户授权后完成 Prompt v2.9 双集 Provider 检查：短集 16/0/0，真实集 1/6/3。005 非唯一引文仍复现；007 发生 provider_finish_length 并由运行器记录后续续跑；006/009 按用户审查不构成问题。
- 2026-08-29：用户明确授权将 26 条小说 Chunk 发送到 `.env` 配置的外部 Provider；Prompt v2.7 短集为 16/0/0、真实集为 2/6/2，全部通过 deterministic validation。008 的虎牙已召回并转 review；005 唯一性与完整月白衣袍改善但仍漏两项；009 复合 transformation 原子化导致新 fail。总 token 56,211，完整运行 hash 与逐 case 元数据已保存。
- 2026-08-29：将 005/008 剩余失败归因为重复 evidence quote、并列/转折视觉谓语截断和动作/对话内短线索漏扫；Prompt 升级到 v2.7，以“语义边界→唯一定位边界→逐子句覆盖复扫”修正。Dataset 金标、Rubric 和 Source Match Policy 不变；89 项测试与静态检查通过，未调用 Provider。
- 2026-08-29：短集升级到 v2.3-draft，真实集升级到 v2.5-draft，补充审计确认的局部 owner alias 与语义完整跨度。复用 Prompt v2.6 已保存 outputs 离线重评分为 16/0/0 与 2/6/2，真实 fail 只剩 005/008；未调用 Provider。
- 2026-08-29：Source Match Policy v2 允许仅空白差异的候选在唯一匹配后回填 Chunk 原始切片；文字和标点改动仍失败。Rubric 升级到 v2.5，forbidden 只对未匹配有效金标的额外候选生效。用户授权 Prompt v2.6 跑两套数据：短集 16 次调用最终重评分 15/16，唯一 raw fail 是“一个红衣少女”未被 approved alias 接受；真实集 10 次调用为 2 pass / 3 review / 5 fail，006 改善为 review、007/010 pass，005 仍有非唯一引文。26 次调用均保存运行元数据；未产生 active Observation。
- 2026-08-29：按用户逐例复核修订 v2.4-draft：004 允许一条逐字唯一的长候选覆盖相邻两个金标且 precision 只计一次；005 将“老者/老人”作为月白衣袍候选局部 alias 并接受保留人物定位的逐字跨度；010 删除兵器/坐骑混入服饰引文的 forbidden。Prompt v2.6 增加脱鞋/解开穿戴物 presentation 和人物定位起点规则。同一 v2.3 outputs 离线重评分为 1/5/4，短集 Rubric 回放 16/16；未调用 Provider。
- 2026-08-29：建立真实集与 Rubric v2.4-draft：补全 001/002/003 owner alias，增加 007 的唯一逐字替代跨度；Rubric 禁止跨 owner alias 冲突、识别单候选吞并多个金标并按唯一定位计算 evidence quote fidelity。同一 v2.3 outputs 离线重评分由 0/1/9 修正为 0/5/5，未调用 Provider；短集回放仍为 16/16。
- 2026-08-29：用户批准 10 条真实 Chunk 后，以 Prompt v2.5 和 `deepseek-v4-flash` 完成真实诊断：8 条通过 deterministic validation，2 条直接失败；Rubric 为 0 pass / 1 review / 9 fail。运行器已修正为单条确定性失败落盘并继续批次；失败复核同时发现 owner alias 和金标跨度覆盖不足，完整 M1 Gate 未通过。
- 2026-08-29：修正第 3 章真实 Chunk 的多老者 owner 混淆：青衫管家与月白衣袍客人使用独立 owner，删除二者共用泛称“老者”，并新增青衫老者 required 金标；真实集升级为 v2.3-draft，未调用 Provider。
- 2026-08-29：Prompt 受控迭代至 v2.5：v2.3 修复否定与推断跨度但出现 unknown-owner 回归，v2.4 排除 body part owner 后仍误绑未知人物表达，v2.5 要求 owner 正向识别具体局部人物；最终 `deepseek-v4-flash` approved 短集 16/16、核心指标全为 100%。
- 2026-08-29：用户批准 16 条 M1 v2.2 短金标；`deepseek-v4-flash` 真实诊断 16/16 调用成功、14/16 通过，quote fidelity 100%，失败为否定外貌漏召回和推断年龄跨度不完整。短集批准不等于 M1 质量 Gate 通过。
- 2026-08-29：完成 M1 Prompt/Dataset/Rubric v2.2：修正推断年龄与明确年龄证据跨度，owner 金标改为 `required/allowed/must_be_null`，逐字且唯一定位纳入确定性失败条件；从 `tests/测试` 按生产章节切分建立 10 个真实 Chunk draft 数据集。未调用真实 Provider。
- 2026-08-28：补充 owner 数据流设计：M1/N2 保存局部 mention，M3 形成权威绑定，服务端派生 Chunk/人物双向索引，N6/M4 只按单人物组包；本次仅更新契约，未实现持久化或运行时。
- 2026-08-28：在用户明确授权后完成 M1 v2 DeepSeek 真实诊断；15/15 调用成功，修正 owner/evidence 金标对齐后 13/15 通过，否定外貌与变身外貌各漏召回 1 条；数据集仍保持 draft。
- 2026-08-28：完成 `semantic-pipeline-v2-design-v1.3` 边界调整；旧 body-fact 失败重新归类为 v1 rubric 历史结果，M2 draft1 暂停直接审核。
- 2026-08-28：当前独立历史已发布到原 GitHub 仓库的 `v2-semantic-pipeline` 分支；未修改或合并 `main`。
- 2026-08-28：当前仓库成为唯一工作区；修复包布局和虚拟环境路径，删除旧项目根目录并完成删除后复验。
- 2026-08-28：完成仓库清理，当前代码与账本统一为 V2 单一路线。
