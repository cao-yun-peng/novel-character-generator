# 项目验收

## 当前验收结论

M1/N2/M2 v1 离线工程切片仍可用。M1 v2 主 Prompt 已回退 v2.8；用户批准把 005 非唯一引文与少年脸貌漏召回作为残余风险，以条件 Gate 继续 N2，但历史 v2.8/v2.9 测评分数保持原样。N2 v2 `GroundedEvidencePacket` 工程 Gate 已通过；M2 v2 尚未迁移。当前不得产生 active Observation，也不能宣称具备发布能力。

## 验收标准

| 标准 | 状态 | 证据 |
|---|---|---|
| V2 总契约和机器可读 Schema 完整 | 通过 | E-20260828-PIPELINE-V2-BOUNDARY-019 |
| M1/N2/M2 v2 职责、目标 Schema、评测和迁移边界完整 | 通过（设计） | E-20260828-PIPELINE-V2-BOUNDARY-019 |
| M1 v2 shadow Prompt、Schema、Provider、Artifact 与 15 条 draft 评测 | 通过（工程；数据待审核） | E-20260828-PIPELINE-V2-M1V2-020 |
| M1 v2 DeepSeek 真实诊断 | 13/15 pass；2 条漏召回；不作为发布 Gate | E-20260828-PIPELINE-V2-M1V2-020-REAL-RERUN |
| M1 v2.2 Prompt、评测契约与 10 条真实 Chunk | 通过（工程；短集后续已批准，真实集仍待审核） | E-20260829-PIPELINE-V2-M1-EVAL-022 |
| M1 v2.2 approved 短集真实诊断 | 14/16；否定外貌与推断跨度各失败 1 条；质量 Gate 未通过 | E-20260829-PIPELINE-V2-M1-SHORT-GATE-023 |
| M1 Prompt v2.5 approved 短集回归 | 16/16；核心指标 100%；短回归 Gate 通过，真实 Chunk Gate 待执行 | E-20260829-PIPELINE-V2-M1-PROMPT-024 |
| M1 真实集 v2.3-draft 多老者 owner 消歧 | 通过（工程；10/10 金标自评分；仍待用户审核与 Provider 运行） | E-20260829-PIPELINE-V2-M1-REAL-OWNER-025 |
| M1 Prompt v2.5 approved 真实集诊断 | 0 pass / 1 review / 9 fail；2 条确定性失败；测量有效性需修正；Gate 未通过 | E-20260829-PIPELINE-V2-M1-REAL-GATE-026 |
| M1 Dataset/Rubric v2.4 测量修正 | 通过（工程；真实同输出重评分 0/5/5；短集 16/16；v2.4 数据待审核） | E-20260829-PIPELINE-V2-M1-EVAL-V24-027 |
| M1 004/005/008/010 边界与 Prompt v2.6 修正 | 通过（工程；真实同输出重评分 1/5/4；短集 Rubric 回放 16/16；未调用 Provider） | E-20260829-PIPELINE-V2-M1-BOUNDARY-028 |
| M1 Source Match Policy v2 与 Prompt v2.6 双集诊断 | 工程通过；短集 15/16、真实集 2/3/5；测量缺口待审核，M1 Gate 未通过 | E-20260829-PIPELINE-V2-M1-V26-GATE-029 |
| M1 短集 v2.3-draft / 真实集 v2.5-draft 离线重评分 | 工程通过；现有 outputs 为 16/0/0 与 2/6/2；两集待复审，M1 Gate 未通过 | E-20260829-PIPELINE-V2-M1-DATASET-030 |
| M1 Prompt v2.7 根因修正 | 工程通过；Prompt 契约与全量回归通过；未调用 Provider，质量效果待新运行验证 | E-20260829-PIPELINE-V2-M1-PROMPT-031 |
| M1 Prompt v2.7 双集 Provider 回归 | 运行完成；短集 16/0/0、真实集 2/6/2；008 修复但 005 未完全修复且 009 回归，M1 Gate 未通过 | E-20260829-PIPELINE-V2-M1-V27-GATE-032 |
| M1 Prompt v2.8 候选颗粒度修正 | 工程通过；跨 owner、同 owner 连续事件与复扫规则已固化；未调用 Provider，质量效果待验证 | E-20260829-PIPELINE-V2-M1-PROMPT-033 |
| M1 Prompt v2.8 双集 Provider 回归 | 运行完成；短集 16/0/0、真实集 2/5/3；009 transformation 改善，用户确认 006/009 无问题，005 非唯一引文与少年脸貌仍失败，M1 Gate 未通过 | E-20260829-PIPELINE-V2-M1-V28-GATE-034 |
| M1 Prompt v2.9 泛化修正 | 工程通过；重复裸描述唯一性闭环与同载体视觉 cue 独立覆盖已固化；未调用 Provider，质量效果待验证 | E-20260829-PIPELINE-V2-M1-PROMPT-035 |
| M1 Prompt v2.9 双集 Provider 检查 | 运行完成；短集 16/0/0、真实集 1/6/3；005 仍失败，007 为 Provider finish_length，006/009 用户确认无问题，M1 Gate 未通过 | E-20260829-PIPELINE-V2-M1-V29-GATE-036 |
| M1 主 Prompt v2.8 回退与 005 残余风险 | 条件批准（用户）：只授权继续 N2；历史分数不改，非逐字证据仍失败关闭 | E-20260829-PIPELINE-V2-M1-CONDITIONAL-GATE-037 |
| N2 v2 GroundedEvidencePacket 纵向切片 | 工程通过；96 项测试、Ruff、Mypy、Schema/账本校验通过；尚未接默认主链 | E-20260829-PIPELINE-V2-N2V2-038 |
| M1 v1 模型线与机械字段物化 | 通过（legacy） | E-20260828-PIPELINE-V2-M1-013 |
| M1 v1 approved 真实集结果 | 历史 5/6，不作为 v2 Gate | E-20260828-PIPELINE-V2-M1-013 |
| N2 唯一证据定位、哈希、上下文和失败关闭 | 通过 | E-20260828-PIPELINE-V2-N2-014 |
| M2 v1 使用唯一精确字段目录和 string-only 值 | 通过（legacy） | E-20260828-PIPELINE-V2-M2-015 |
| N2 v2 运行时契约与确定性工程 Gate | 通过；尚未接默认主链 | E-20260829-PIPELINE-V2-N2V2-038 |
| M2 v2 运行时迁移与新数据 Gate | 未实现 | E-20260828-PIPELINE-V2-BOUNDARY-019 |
| owner 双向索引与 M4 单人物组包契约 | 通过（设计） | E-20260828-PIPELINE-V2-OWNER-021 |
| Git 工作树只保留 V2 当前实现与资料 | 通过 | E-20260828-CLEANUP-V2-016 |
| 当前仓库无需旧项目即可独立导入和验证 | 通过 | E-20260828-ENV-ISOLATION-017 |
| 独立历史分支已发布且不修改旧 `main` | 通过 | E-20260828-REPO-PUBLISH-018 |

## 证据索引

- `.project-to-act/tasks/PIPELINE-V2-DESIGN-012/evidence/`
- `.project-to-act/tasks/PIPELINE-V2-M1-013/evidence/`
- `.project-to-act/tasks/PIPELINE-V2-N2-014/evidence/`
- `.project-to-act/tasks/PIPELINE-V2-M2-015/evidence/`
- `.project-to-act/tasks/CLEANUP-V2-016/evidence/`
- `.project-to-act/tasks/ENV-ISOLATION-017/evidence/`
- `.project-to-act/tasks/REPO-PUBLISH-018/evidence/`
- `.project-to-act/tasks/PIPELINE-V2-BOUNDARY-019/evidence/`
- `.project-to-act/tasks/PIPELINE-V2-M1V2-020/evidence/`
- `.project-to-act/tasks/PIPELINE-V2-OWNER-021/evidence/`
- `.project-to-act/tasks/PIPELINE-V2-M1-EVAL-022/evidence/`
- `.project-to-act/tasks/PIPELINE-V2-M1-SHORT-GATE-023/evidence/`
- `.project-to-act/tasks/PIPELINE-V2-M1-PROMPT-024/evidence/`
- `.project-to-act/tasks/PIPELINE-V2-M1-REAL-OWNER-025/evidence/`
- `.project-to-act/tasks/PIPELINE-V2-M1-REAL-GATE-026/evidence/`
- `.project-to-act/tasks/PIPELINE-V2-M1-EVAL-V24-027/evidence/`
- `.project-to-act/tasks/PIPELINE-V2-M1-BOUNDARY-028/evidence/`
- `.project-to-act/tasks/PIPELINE-V2-M1-V26-GATE-029/evidence/`
- `.project-to-act/tasks/PIPELINE-V2-M1-DATASET-030/evidence/`
- `.project-to-act/tasks/PIPELINE-V2-M1-PROMPT-031/evidence/`
- `.project-to-act/tasks/PIPELINE-V2-M1-V27-GATE-032/evidence/`
- `.project-to-act/tasks/PIPELINE-V2-M1-PROMPT-033/evidence/`
- `.project-to-act/tasks/PIPELINE-V2-M1-V28-GATE-034/evidence/`
- `.project-to-act/tasks/PIPELINE-V2-M1-PROMPT-035/evidence/`
- `.project-to-act/tasks/PIPELINE-V2-M1-V29-GATE-036/evidence/`
- `.project-to-act/tasks/PIPELINE-V2-M1-CONDITIONAL-GATE-037/evidence/`
- `.project-to-act/tasks/PIPELINE-V2-N2V2-038/evidence/`

## 验收记录

- 2026-08-29：用户决定主 Prompt 回退到 v2.8，并批准 005 为 M1 残余风险。该 Gate 结论为 conditional，不把 v2.8/v2.9 的失败报告改成 pass；N2 对重复引文 deferred，对非逐字引文 rejected，active 写入仍禁止。

- 2026-08-29：按用户要求不针对 005 特化，Prompt v2.9 将问题泛化为重复引文二次唯一性闭环和同载体不同视觉谓词分别覆盖；两套 Dataset 仅更新 Prompt 元数据，未调用 Provider，质量 Gate 待验证。
- 2026-08-29：用户授权完成 Prompt v2.9 双集 Provider 检查。短集 16/0/0，真实集 1/6/3；005 的非唯一引文仍复现，007 记录 provider_finish_length 后续跑，006/009 按用户审查不构成问题；M1 Gate 未通过。
- 2026-08-29：Prompt v2.8 明确每个候选最多包含一个本地人物的外观事实、owner 转换必须拆分，同一人物连续外观画像/变形/presentation 保持复合跨度，覆盖复扫只查漏且不产生重复或纯动作候选。两套 Dataset 仅更新 Prompt 元数据；89 项测试、Ruff、Mypy、diff check 和账本校验通过。未调用 Provider，因此不通过质量 Gate。
- 2026-08-29：用户明确确认将两套 Dataset 外发至 `.env` Provider，完成 Prompt v2.8 双集回归。短集 16/0/0；真实集 2/5/3；9/10 真实条目成功通过 deterministic validation，005 逐条失败后仍保留工件并继续。009 transformation 主要缺口改善；005 非唯一引文仍失败，006/009 暴露 alias/跨度缺口；质量 Gate 未通过。
- 2026-08-29：用户明确授权将短集与真实集共 26 条小说 Chunk 发送到 `.env` 配置的外部 Provider。Prompt v2.7 短集 16/0/0、真实集 2/6/2；26/26 均通过 deterministic validation。008 从 fail 改善为 review；005 从校验失败改善为普通 Rubric fail，但仍漏少年脸貌与青衫管家服饰；009 因 transformation 原子化从 review 回归 fail。89 项测试、Ruff、Mypy、diff check 和账本校验通过；M1 Gate 未通过。
- 2026-08-29：依据真实 005/008 将 Prompt v2.7 修改为两阶段引文构造与全 Chunk 二次覆盖复扫，明确 owner 不能替 evidence 引文消歧，并覆盖观察、动作、对话结构中的短视觉线索。Dataset 金标与版本、Rubric、Source Match Policy 均不变；89 项测试、Ruff、Mypy 和 diff check 通过，未调用 Provider，因此只通过工程验收，不通过质量 Gate。
- 2026-08-29：按人工审计结论升级短集 v2.3-draft 与真实集 v2.5-draft，只补充安全的局部 owner alias/完整逐字跨度。复用已保存 Prompt v2.6 outputs 离线重评分为 16/0/0 与 2/6/2；真实硬失败只剩 005、008。89 项测试、Ruff、Mypy、diff check 和账本校验通过；未调用 Provider。
- 2026-08-29：用户授权 Source Match Policy 修正与 Prompt v2.6 双集真实运行。规则只忽略 whitespace、唯一映射并回填原始切片；旧 004 保存输出由 fail 变为 review，证明规则生效。短集 16 次 Provider 调用最终按 Rubric v2.5 重评分 15/16；真实集 10 次调用为 2 pass / 3 review / 5 fail，9 条通过 deterministic validation，005 因青衫老者引文不唯一失败。89 项测试、Ruff、Mypy 和 diff check 通过。结果暴露新 alias/跨度测量缺口，不能通过 M1 Gate。
- 2026-08-29：根据用户对 004/005/008/010 的人工审查，Rubric v2.4 允许逐字唯一的长候选覆盖相邻多个金标且按实际候选计 precision；005 接受月白衣袍候选内“老者/老人”局部 alias；010 删除兵器/坐骑混入服饰引文的 forbidden；Prompt v2.6 增强脱鞋 presentation 与人物定位起点。10/10 金标自评分、短集 16/16、84 项测试与静态检查通过；同一真实 outputs 为 1/5/4，未调用 Provider。
- 2026-08-29：Dataset/Rubric v2.4-draft 补全 001/002/003 的明确人物 alias 与 007 的唯一逐字替代跨度；Rubric 新增跨 owner alias 冲突、单候选多金标和唯一定位 quote fidelity。10/10 金标自评分通过；同一真实 outputs 为 0 pass / 5 review / 5 fail，短集回放 16/16；未调用 Provider，真实集仍待审核。
- 2026-08-29：用户批准真实集 v2.3 并明确授权发送给 DeepSeek；attempt 2 完成 10 条调用，8 succeeded、2 deterministic validation failed，Rubric 为 0 pass / 1 review / 9 fail。evidence recall 0.50、candidate precision 0.2453、quote fidelity 0.9878、required owner recall 0.4091、owner binding precision 0.2453。至少 001/002/003/007 存在 owner alias 或跨度覆盖问题，因此 Gate 不通过且须先修测量有效性。
- 2026-08-29：真实集 v2.3-draft 将青衫管家与月白衣袍客人分成不同 owner，二者均不接受歧义泛称“老者”；新增逐字且唯一定位的“一名青衫老者”required 候选。10 条 source-backed Chunk 重建与金标自评分通过，未调用 Provider，数据仍待用户审核。
- 2026-08-29：Prompt v2.3–v2.5 逐版保存对照结果；v2.5 在同一 approved 短集上 16/16，evidence recall、candidate precision、quote fidelity、required owner recall、owner binding precision 和 must-be-null accuracy 均为 100%。短回归通过不代表真实 Chunk 或发布 Gate 通过。
- 2026-08-29：用户确认 16 条短金标无问题，数据集冻结为 approved；Prompt v2.2 真实调用 16/16 成功且确定性校验通过，Rubric 为 14 pass / 2 fail。失败属于模型召回与证据跨度，不修改已批准金标，也不通过 M1 质量 Gate。
- 2026-08-29：M1 Prompt/Dataset/Rubric 升级到 v2.2；短集修正推断年龄与明确年龄跨度，owner 使用三态策略，真实运行器经 deterministic validation 并保存三类 hash 与模型元数据；10 条真实 Chunk 可由四份原文按生产分块重建。数据仍为 draft，未调用真实 Provider。
- 2026-08-28：用户确认采用 Chunk/人物双向 owner 访问设计；契约明确 Chunk owner 仅为 M3 后可重建缓存，权威绑定保留 provenance/version/supersede，M4 仅按单人物观察批次调用。本轮未实现运行时。
- 2026-08-28：用户确认 M1 只召回视觉相关句段，M2 接管分类、原子化、认知状态和显式信号；设计与机器 Schema 已更新，运行时仍保持 v1，未冒充实现完成。
- 2026-08-28：通过已验证的 GitHub SSH 身份新建并推送 `v2-semantic-pipeline`，本地与远程提交一致。
- 2026-08-28：删除旧项目后，当前工作区的导入来源、59 项测试、Ruff、Mypy、diff check 和账本校验重新通过。
- 2026-08-28：V2 清理后的测试、静态检查和账本校验作为 `E-20260828-CLEANUP-V2-016` 的最终证据。
