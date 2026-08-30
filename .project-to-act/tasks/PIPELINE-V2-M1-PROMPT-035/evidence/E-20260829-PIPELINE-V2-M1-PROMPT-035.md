# M1 Prompt v2.9 泛化修正证据

## 用户约束

- 用户明确要求：不能针对 005 的具体人物或词语特化，必须解决一类问题。
- 006、009 已由用户复审确认没有实质问题；本任务不修改这两个案例的 Dataset 金标或 Rubric。

## 根因泛化

- 重复裸描述类：短描述词在 Chunk 中多次出现时，模型不能只返回裸短语并依赖 owner_index 猜测目标位置；必须保留同一出现位置的量词、指示词、角色/位置修饰、动作或完整从句，直到引文唯一；若无法唯一定位则删除候选。
- 同载体 cue 覆盖类：同一人物、同一身体部位或同一物件上，不同视觉谓词/修饰/状态是独立覆盖项。先前的物理外观描述不能被后续情绪、动作或状态谓词替代，除非同一连续引文明确包含两者。

## Prompt v2.9 变更

- Prompt 版本升级为 `visual-evidence-discovery-prompt-v2.9`。
- 增加“Uniqueness is a hard output invariant”规则：草拟后再次检查全部候选；重复引文必须修复为唯一连续原文或删除，不得由 owner mention 补救。
- 增加“each distinct visual predicate”覆盖规则：覆盖复扫按视觉谓词、修饰、状态和关系分别检查，禁止同载体不同 cue 互相替代。
- 未加入 005 的人名、具体短语、固定答案或 Dataset 专用示例。

## 不可变边界与哈希

- Dataset 仍为 `m1-visual-evidence-short-v2.3-draft` 与 `m1-visual-evidence-real-v2.5-draft`；仅更新 prompt_version 为 v2.9。
- Rubric 保持 `visual-evidence-evaluation-rubric-v2.5`；Source Match Policy 保持 `visual-evidence-source-match-policy-v2`。
- Prompt 文件 SHA-256：`011ab810779e06f5cc4d440354bdea4ec4eecd3e7c70b843a2556926ad65da2e`。
- Prompt runtime SHA-256：`a55cc18e274e7f3eb17ef9c61cbfb201d7e46993fff24fe9d70ec37e35688b13`。
- Short Dataset SHA-256：`59f33020c69354aa733e7b58e0bbb9266af84cd54d813bd6945764ac090f1773`。
- Real Dataset SHA-256：`08eb80d3c4145767e531e2b35efecf4d1ce8b136f7b61ebd8da15de39705ae3d`。

## 工程验证

- 真实 Dataset 重建成功：10 cases。
- 定向 Prompt/评测测试：29 passed。
- 全量测试：89 passed。
- Ruff：passed；Mypy：36 source files passed；Project-to-Act validate：valid；`git diff --check`：passed（仅既有 LF/CRLF warning）。
- 不调用 Provider；v2.8 outputs 不可作为 v2.9 质量结果。
