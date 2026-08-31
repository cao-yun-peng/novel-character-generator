# E-20260831-M2-DOUPO-LIVE-RUN-056

## 结论

使用斗破前5章既有 M1 原始输出重放最新 N2 后，DeepSeek M2 exact attribution 完成 18/18 个任务。结构化输出、代码 Grounding、可恢复执行和审计产物通过本任务验收；M2 人工归属质量与 N3 未验收，Stage 5 保持 `in_progress`。

## 输入与版本

- 原文：`tests/小说/斗破苍穹前5章.txt`
- 原文 SHA-256：`7ca3fd295b5d0d454ca0b0bac2f4a49f2271602fc8e55bca2f120bb11d85172a`
- M1 来源：`runs/doupo-first5-m1-scope-v4/m1-model-outputs.json`
- N2：`grounded-character-packet-v5` + `exact-evidence-precedence-v1`
- Schema：`3.8.0-draft1`
- 实跑标识 runtime：`0.1.0.dev7`；恢复修复后当前 runtime：`0.1.0.dev8`
- Provider/model：DeepSeek Responses API / `deepseek-v4-flash`

## 结果

- 7 个 Chunk；N2 重放：18 exact、5 individual describe、1 collective、57 approved evidence bindings。
- M2 任务：planned 18、succeeded 18、failed 0。
- 模型事实 50、grounded facts 50、unique `fact_quote` 45。
- Match mode：exact 50、whitespace_equivalent 0。
- 来源：exact 50、describe 0；grounding issues 0。
- 18 条 Provider trace；usage 总计 input 35,757、cached input 7,808、output 12,954、reasoning 11,384、total 48,711 tokens。
- 只有两个任务携带 describe pool，池内五个 describe 均明显属于其他人物；模型未将其错误归给萧炎或萧熏儿，因此 describe 来源为 0 合理。

## 中断与恢复

- 第一次执行完成 5 个任务后，`http.client.IncompleteRead` 从 `response.read()` 越过旧网络异常分类并终止进程。
- 已完成的 5 个 task result 已按 task cache key 落盘。
- Provider 将 `HTTPException` 纳入有界瞬态重试并新增回归测试。
- 第二次执行 resumed 5、new provider calls 13，最终 18/18 完成；`run-history.json` 保留两次尝试。

## 验证

- 81 tests passed，13 subtests passed。
- 18 个 envelope、18 个模型输出、18 个 grounded result 和 7 个 N2 packet 全部通过 Draft 2020-12 Schema 校验。
- 50/50 `fact_chunk_span` 回放等于 `fact_quote`；50/50 `source_evidence_span` 回放等于 `source_evidence_quote`。
- 模型事实字段严格等于 `fact_quote/category/attribute/value`。
- Trace 共 18 条，不含 API Key、`chunk_text`、system instruction 或模型 reasoning 文本。
- `failures.json` 为空；Project-to-Act、Lifecycle 和 diff 验证见任务结束检查。

## 产物与 SHA-256

- `runs/doupo-first5-m2-dev7-20260831/m2-model-outputs.json`：`f092974e71fa2274db5bc803594bedf96fe8eaddbe92e84acc94f0739d8e7876`
- `runs/doupo-first5-m2-dev7-20260831/m2-grounded-results.json`：`68fa4fdb6dc1b6ffd3e71283192f4b404e409b042106286fe2fc3c0bbb8b05d0`
- `runs/doupo-first5-m2-dev7-20260831/summary.json`：`480cda83a2d99f281771975c2776993dcedb225ff83c36b6106e43f251313172`
- `src/novel_character_generator/m2_batch.py`：`95d0ef1f14d9ab11a1c5ffe7f7e46b7206e02051d8c3bb42dd33958c43720288`
- `src/novel_character_generator/providers/deepseek.py`：`3439b4aeec12a6ecbf562d674e54e7fb6f8ca48702f2c5243b8c5a5f47b6eb59`

## 能力边界

- 本轮只运行 exact attribution，没有 N3 remaining pool，因此不运行 promotion。
- 45 条 unique quote 不是跨 Chunk/跨人物去重后的最终事实数。
- 单次真实运行证明链路可执行，不证明所有人物归属、事实类别和值均达到人工质量阈值。
