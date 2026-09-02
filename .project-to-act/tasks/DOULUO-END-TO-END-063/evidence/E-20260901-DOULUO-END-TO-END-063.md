# E-20260901-DOULUO-END-TO-END-063

- 时间：2026-09-01（Asia/Shanghai）
- 任务：`DOULUO-END-TO-END-063`
- 基线提交：`85985e3380a755a1cd2e5d99e9cc401b0c22d335`
- 运行时：`0.1.0.dev13`
- Schema：`3.13.0-draft1`
- 输入：`tests/小说/斗罗大陆前20章.txt`，实际第1至19章，38,251 字符，SHA-256 `8bcb7305a759571b1fec70813b0631f2c884eba79697c3259170a7635d639741`
- 有效期：对应本任务输入、dev13 代码/Schema 和 `runs/douluo-20ch-e2e-dev13-20260831`；任一来源变化后需重验

## 链路结果

1. M1：17/17 Chunk，64 candidates、46 grounded mentions、97 approved evidence、0 rejected。
2. M2：32/32 tasks，84 model facts、84 grounded facts、1 `multiple_target_occurrences` review、0 failure。
3. N3/promotion：11/11 tasks；HTTP 402 前 8 项缓存，充值后只新增 3 次调用；11 promoted characters、46 facts、0 grounding issue/review。
4. 文档汇总：130 input facts → 129 document facts；1 个重叠副本删除，130 source occurrences 全保留；83 exact、46 promoted。
5. M3 identity：43 local nodes、63/63 tasks；47 same、15 uncertain、1 different；9 grounding issues、8 global characters、10 unresolved、17 review、1 cannot-link。
6. Profiles：8 characters、106 assigned facts、23 unassigned facts、130 occurrences、9 possible conflicts、17 review、10 unresolved、1 cannot-link。

真实 `different` 为 `大师` 与 `战魂大师`。Grounding 分别保留“二十多岁/剑眉星目/俊朗”和“四、五十岁”证据，N4 形成 cannot-link，未按包含关系误合并。

## 调用与 Token

| 阶段 | 最终成功任务记录 | input | cached input | output | reasoning（output 子集） | total |
|---|---:|---:|---:|---:|---:|---:|
| M1 | 17 | 43,594 | 20,096 | 65,935 | 60,783 | 109,529 |
| M2 | 32 | 67,069 | 12,288 | 35,909 | 32,908 | 102,978 |
| N3 | 11 | 23,345 | 0 | 11,103 | 8,956 | 34,448 |
| M3 | 63 | 120,037 | 32,256 | 59,569 | 56,027 | 179,606 |
| 合计 | 123 | 254,045 | 64,640 | 172,516 | 158,674 | 426,561 |

任务级 Provider invocations（含失败/恢复）为 130。Token 合计采用最终成功 task record，可复核但不等同账单；无 usage 的网络失败/截断响应和被覆盖的失败快照无法完整计量。

## 验证

1. `python -m unittest discover -s tests`：退出 0，118 tests passed。
2. Draft 2020-12：`DocumentCharacterEvidence`、`DocumentCharacterRegistry`、`DocumentCharacterProfiles` 和 63 个 `GroundedIdentityDecision`，共 67 个实例通过。
3. 原始 CRLF 保留模式独立回放：129/129 document facts、130/130 source evidence/Chunk、105/105 identity evidence、129/129 profile facts，通过；document/chunk hash 全匹配。
4. M1/M2/N3/M3 `failures.json` 最终均为空；各 summary `complete=true`。
5. Project-to-Act、Lifecycle、`git diff --check`：完成前最终复验。

## 核心工件 SHA-256

- `m1/summary.json`：`a71f86a5a645b6ed59691393f9c9ff767ae99c0fc23c4d9c31608d4f7e9092dd`
- `m2/summary.json`：`c9d765cc78a434eaa0f9424b5634dcb40f3b12cf64898dc4cc6c8081b00da63d`
- `n3/summary.json`：`d9974b1a74802e6f95701ea3f61396a975344c6cf6985ea55a1adb78ad417e45`
- `document-character-evidence.json`：`926e6221ca69ad5ae0843d90870129617df7597e47ed586d9d20035c22a3a439`
- `identity/summary.json`：`ce9ca597ef885850fefca5e4546a5258cc472e239a9a8c25ae4bac5d96b3ea44`
- `identity/document-character-registry.json`：`95ecfc588ea8723bee7b37c0c418d3a65d4a7e84ce52a1026a578d95e8146ef0`
- `profiles/document-character-profiles.json`：`65e1349edf2dcaacf94edf109986d6616179a714952942d665ff92830706e9b7`

## 边界

- 文件名写“前20章”，实际输入缺第20章；complete 只表示给定 38,251 字符全部覆盖。
- 23 条未绑定事实、17 个 review 和 10 个 unresolved 均显式保留；不得把它们解释为不存在。
- 本次证明结构化执行、严格 Grounding、可恢复运行和确定性汇总，不构成人工标注的外貌或身份 precision/recall Gate。
