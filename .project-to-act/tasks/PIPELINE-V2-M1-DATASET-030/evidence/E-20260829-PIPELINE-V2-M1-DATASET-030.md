# E-20260829-PIPELINE-V2-M1-DATASET-030

## 数据集变更

- 短集升级为 `m1-visual-evidence-short-v2.3-draft`，状态 `draft_user_review_required`；short-003 接受“一个红衣少女”作为局部 owner alias 与语义完整逐字跨度。Dataset SHA-256：`6ed17283c6fae9e4cf21de6eecdc1a1ca6e5079927bfe6dbd9f8b2dd05e40244`。
- 真实集升级为 `m1-visual-evidence-real-v2.5-draft`，状态 `draft_user_review_required`；补充 003 的“他”、004 的“那是一名中年男子”、008 的“那女孩儿”、009 的“小女孩仙清儿”，并为 008 增加不含量词但语义完整且唯一定位的年龄发辫跨度。Dataset SHA-256：`800086d9d4d6f127e63fa64bd3bbea96de469402d15c23259c67e434ab7b5f69`。
- Dataset Schema 仍分别为 v2.2 与 v2.4；Prompt 保持 v2.6，Rubric 保持 v2.5，Source Match Policy 保持 v2。
- 005 的青衫老者非唯一定位、少年脸貌/月白衣袍问题及 008 的虎牙漏召回未通过金标放宽消除。

## 现有 outputs 离线重评分

- 短集复用 outputs SHA-256 `c07c08474bb1bc3fd2691d63d06996a8044b3e798f97dbd64c883c33ed39fe15`：16 pass / 0 review / 0 fail；recall、precision、quote fidelity、required owner recall 与 owner binding precision 均为 1.0。报告 SHA-256：`ef5bc29aa01fa23df0a1adbb2463bcc7d640de9e225026d59458452dedfd7559`。
- 真实集复用 outputs SHA-256 `6f491b89bdea8c90522ef8e6f46a8b2a0ac0d931b9307249c1e592f79c633d5d`：2 pass / 6 review / 2 fail；evidence recall `0.846153846153846`、candidate precision `0.461538461538462`、required owner recall `0.818181818181818`、owner binding precision `0.461538461538462`。报告 SHA-256：`926c1ac58e08e5af2a4ec15e2d2b73f8ef37a046c0c414a79ce6963c9c352077`。
- 真实 fail 只剩 `m1-v2-real-presentation-and-elder-005` 与 `m1-v2-real-relative-age-accessory-008`。
- 两份报告的 `quality_gate` 均为 `blocked_pending_user_review`，原因是新数据集仍为 draft。
- 两个 `offline-rescore.json` 保存源 run、outputs、Prompt、Dataset、Rubric、报告 hash 和模型元数据；`provider_called=false`。本任务未调用 Provider、未写数据库、未产生 active Observation。

## 工程验证

- 数据集生成器重建真实集：10 cases。
- 金标自评分与目标评分器单测：24 passed。
- 全量 Pytest：89 passed。
- Ruff：通过。
- Mypy：`src scripts` 共 36 source files 无问题。
- `git diff --check`：通过。
- Project-to-Act validate：通过（见任务完成时校验）。
- `AGENT_LIFECYCLE.json` 的既有 revision 1/current stage 5 历史问题未由本任务修改，本任务不宣称 lifecycle Gate。
