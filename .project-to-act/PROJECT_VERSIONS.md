# 项目版本

## 当前版本

- 项目版本：`0.1.0`，未发布
- GitHub 开发分支：`origin/v2-semantic-pipeline`（独立历史，不与旧 `main` 合并）
- 设计基线：`semantic-pipeline-v2-design-v1.3`
- 机器 Schema 注册表：`semantic-pipeline-v2-model-schemas-v1.4`
- 当前 legacy M1：`local-observation-model-wire-v1`、Prompt `v1.6`
- 当前 M1 v2 shadow：`visual-evidence-discovery-model-wire-v2`、主 Prompt `visual-evidence-discovery-prompt-v2.8`
- 当前 M1 v2 评测：Dataset Schema `visual-evidence-evaluation-dataset-v2.4`（兼容读取 v2.2）、Rubric `visual-evidence-evaluation-rubric-v2.5`、Source Match Policy `visual-evidence-source-match-policy-v2`
- 当前短数据集：`m1-visual-evidence-short-v2.3-draft`，状态 `draft_user_review_required`
- 当前真实 Chunk 数据集：`m1-visual-evidence-real-v2.5-draft`，状态 `draft_user_review_required`
- 当前 legacy N2：`local-grounding-input-v1`、`grounded-local-packet-v1`
- 当前 legacy M2：`field-disambiguation-model-wire-v1`、`visual-field-catalog-v1`
- 目标 M1：`visual-evidence-discovery-model-wire-v2`
- 当前 N2 v2：`evidence-grounding-input-v2`、`grounded-evidence-packet-v2`、`evidence-grounding-policy-v2`、`evidence-context-sentence-window-v2`
- 目标 M2：`local-visual-semantic-model-wire-v2`

这里的 `v1` 是各 V2 子契约的独立版本号，不代表已删除的旧架构。

## 下一版本计划

主 Prompt 固定回退到 v2.8；005 作为用户批准残余风险，不再继续 Prompt 特化。完成 N2 v2 工程 Gate后进入 M2 v2 与 M1→N2→M2 shadow 组合；重复引文只能 deferred，不得猜测定位或进入 active 状态。任何 active 写入或持久化设计都必须建立独立任务并重新验收。

## 版本历史

- 2026-08-29：用户决定主 Prompt 从 v2.9 回退到 v2.8，并接受 005 的非唯一逐字引文与少年脸貌漏召回为 M1 残余风险；历史 Provider 结果不改写。新增 N2 v2 `evidence-grounding-input-v2` / `grounded-evidence-packet-v2` 确定性切片，重复引文 deferred、非逐字引文 rejected。

- 2026-08-29：Prompt 升级为 `visual-evidence-discovery-prompt-v2.9`，将 005 的重复裸描述和同载体不同视觉 cue 根因泛化为唯一性二次闭环、重复描述扩展/拒绝和独立 cue 覆盖规则；Dataset/Rubric/Source Match Policy 不变，未调用 Provider。
- 2026-08-29：Prompt 升级为 `visual-evidence-discovery-prompt-v2.8`，针对 v2.7 真实运行暴露的 005 跨 owner 混绑与 009 同 owner 连续 transformation 原子化，增加 owner 硬边界、同 owner 复合事件和覆盖复扫去重规则；Dataset 只更新 Prompt 元数据，未调用 Provider。
- 2026-08-29：用户明确确认将两套 Dataset 外发至 `.env` Provider 后，Prompt v2.8 完成 26 条双集回归：短集 16/0/0，真实集 2/5/3。009 transformation 主要缺口改善；005 仍有非唯一引文，006/009 暴露 Dataset alias/跨度待审核，M1 Gate 未通过。
- 2026-08-29：Prompt v2.7 以 `deepseek-v4-flash` 完成短集 v2.3-draft 与真实集 v2.5-draft 共 26 次调用；短集 16/0/0，真实集 2/6/2。008 从 fail 到 review，005 仍 fail，009 从 review 回归 fail；所有调用通过 deterministic validation，M1 Gate 未通过。
- 2026-08-29：Prompt 升级为 `visual-evidence-discovery-prompt-v2.7`，针对真实 005/008 增加两阶段引文边界和全 Chunk 逐子句覆盖复扫；Dataset 只更新被测 Prompt 元数据，金标和版本不变，Rubric/Source Match Policy 不变，未调用 Provider。
- 2026-08-29：短集升级为 `m1-visual-evidence-short-v2.3-draft`，真实集升级为 `m1-visual-evidence-real-v2.5-draft`；Dataset Schema 仍分别为 v2.2/v2.4，Prompt/Rubric/Source Match Policy 不变。现有 Prompt v2.6 outputs 离线重评分分别为 16/0/0 与 2/6/2，未调用 Provider。
- 2026-08-29：新增 `visual-evidence-source-match-policy-v2`，仅忽略 whitespace 并回填原始切片；Rubric 升级到 `visual-evidence-evaluation-rubric-v2.5`。Prompt v2.6 使用 `deepseek-v4-flash` 完成短集与真实集共 26 次调用；结果分别为 15/16 与 2 pass / 3 review / 5 fail，仍不满足 M1 Gate。
- 2026-08-29：Prompt 升级为 `visual-evidence-discovery-prompt-v2.6`，补充脱鞋/解开可穿戴物 presentation 与年龄/配饰人物定位起点；Dataset/Rubric 保持 v2.4-draft/v2.4，在 draft 内按人工复核放宽相邻金标合并候选、补充 005 局部 alias/跨度并删除 010 forbidden。未调用 Provider。
- 2026-08-29：Dataset Schema/Rubric 升级到 v2.4，真实集形成 `m1-visual-evidence-real-v2.4-draft`；补全 owner alias 与 007 替代跨度，新增 owner alias 冲突、候选多重匹配和唯一定位 fidelity 规则。短集仍保留 v2.2 approved 数据版本并兼容回放。
- 2026-08-29：用户批准并冻结 `m1-visual-evidence-real-v2.3`；Prompt v2.5 真实诊断为 0 pass / 1 review / 9 fail。运行器兼容单条 deterministic failure 后继续批次，不升级 Prompt、Rubric 或模型 wire 版本。
- 2026-08-29：真实 Chunk 数据集升级为 `m1-visual-evidence-real-v2.3-draft`；第 3 章中青衫管家与月白衣袍客人分用独立 owner，并增加青衫老者金标。Dataset Schema、Rubric、Prompt 和已批准短集均不变。
- 2026-08-29：Prompt 经 v2.3/v2.4 诊断迭代到 v2.5；不修改 approved 金标和 Rubric。v2.5 使用 `deepseek-v4-flash` 在 16 条 approved 短集达到 16/16，v2.2/v2.3/v2.4 的中间结果分别保留在独立诊断目录。
- 2026-08-29：短数据集由用户审核批准并冻结为 `m1-visual-evidence-short-v2.2`；Prompt v2.2 使用 `deepseek-v4-flash` 首次真实诊断为 14/16，不能升级 Prompt 或发布版本状态。
- 2026-08-29：Prompt 升级到 v2.2，要求最小但语义完整且唯一可定位的逐字跨度；Dataset/Rubric 升级到 v2.2，并新增 10 条生产切分真实 Chunk draft 集。v2.1 的 13/15 结果不迁移为 v2.2 结果。
- 2026-08-28：在设计基线 v1.3 内澄清 owner 物化与索引契约，不升级模型 wire Schema：Chunk 侧只允许版本化派生缓存，M3 `OwnerBinding` 是事实源，M4 固定为单人物输入。
- 2026-08-28：设计升级到 v1.3，Schema 注册表升级到 v1.4；M1 收窄为 evidence discovery，M2 扩展为 local semantic parsing。旧 v1 工件不就地改写。
- 2026-08-28：M1 v2 shadow 版本落地：`visual-evidence-discovery-model-wire-v2`、Prompt `v2.1`、不可变 Artifact 和 15 条 draft evidence-coverage 评测；不切换默认主链。
- 2026-08-28：提交 `ed8396d` 已推送到 `origin/v2-semantic-pipeline`；旧 `main` 保持不变。
- 2026-08-28：不变更 `0.1.0` 语义版本；修正源码包布局和本机 editable 安装来源，当前仓库可独立运行。
- 2026-08-28：完成 M1、N2、M2 离线工程切片。
- 2026-08-28：清除无关实现、测试、文档、运行数据和历史账本，仓库收敛为 V2 单一路线。
