# E-20260829-PIPELINE-V2-M1-BOUNDARY-028

## 变更证据

- Prompt：`visual-evidence-discovery-prompt-v2.6`；Prompt 文件 SHA-256 `b9f230b826296ff0162e870c22e527db0907c1053f18e2a1764a7279de058ff0`；Provider 运行时 Prompt hash `cbb889fe0703b5fe964fce4e2d99696561093a6d0aa4b4b23051e4b8bfafc844`。
- 真实 Dataset：`m1-visual-evidence-real-v2.4-draft`，SHA-256 `94f7f216ccf0d6d84a2960b834c781b53f1312fda14c19f28cb1236ebaf92a91`。
- approved 短 Dataset：`m1-visual-evidence-short-v2.2`，SHA-256 `5579c8533a304b338eddf564a91acfc102137f42ed4edfb3670701dbf389166d`。
- Rubric：`visual-evidence-evaluation-rubric-v2.4`，实现 SHA-256 `dd424e4a7c9b5cb52c783697aaa2765699b42d0fe4e9c64472d1dad4cbeb67ae`。
- 004：逐字且唯一的单条实际候选可覆盖相邻多个金标；scored actual、unscored 与 owner binding precision 均按实际候选计数一次。保存输出仍因非逐字引文失败。
- 005：月白衣袍人物接受候选局部 alias `老者/老人`，并接受去掉量词但保留人物与视觉关系的唯一逐字跨度；青衫老者与其仍为不同 owner。
- 008：Prompt 新增脱鞋/解开可穿戴物 presentation 召回，并要求相对年龄/发型、配饰保留人物定位起点。
- 010：真实案例删除 `held_weapon_or_mount_is_not_appearance` forbidden；仅有手持物的 approved 短边界 case 仍保持失败规则。

## 离线结果

- v2.4-draft 金标自评分：10 pass / 0 review / 0 fail。
- 同一 v2.3 真实 outputs 重评分：1 pass / 5 review / 4 fail；evidence recall `0.807692307692308`，candidate precision `0.39622641509434`，quote fidelity `0.975609756097561`，owner binding precision `0.39622641509434`。
- 真实重评分报告 SHA-256：`579f68450a79b741bdcf4dc99f7e29fde5f361a0ce90b0c1a0204b7cf7948305`。
- approved 短集 Rubric 回放：16 pass / 0 review / 0 fail；报告 SHA-256 `ebc697386197b570dee65f3678f8da63c81588f66e93f3a02f473c5f6aeebb86`。
- 未调用 Provider；短集 16/16 仅证明 Rubric/数据兼容，不代表 Prompt v2.6 模型质量。

## 工程验证

- Pytest：84 passed。
- Ruff：通过。
- Mypy：36 source files 无问题。
- `git diff --check`：通过。
- Project-to-Act validate：`valid=true`，无 issues。
- `AGENT_LIFECYCLE.json` 保持 preexisting revision 1/current stage 5，不手工伪造 Gate transition。
