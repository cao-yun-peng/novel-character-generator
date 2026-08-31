# 斗破苍穹前 5 章 M2 实跑报告

## 输入

- 原文：`tests/小说/斗破苍穹前5章.txt`
- 原文 SHA-256：`7ca3fd295b5d0d454ca0b0bac2f4a49f2271602fc8e55bca2f120bb11d85172a`
- M1 来源：`runs/doupo-first5-m1-scope-v4/m1-model-outputs.json`
- N2：从 M1 原始输出重新物化 `grounded-character-packet-v5`，应用 `exact-evidence-precedence-v1`
- 模型：`deepseek-v4-flash`

## 结果

- Chunk：7
- N2：18 个 exact、5 个 individual describe、1 个 collective、57 条 approved evidence bindings
- M2 exact attribution 任务：18/18 成功，0 失败
- 模型事实：50 条；代码 Grounding 通过：50 条
- 不同 `fact_quote`：45 条；这不是跨 Chunk 去重后的事实数
- Grounding：50 条严格逐字匹配，0 条空白恢复，0 条歧义或越界
- 来源：50 条来自 exact evidence，0 条来自 describe evidence
- Trace：18 条，全部脱敏；整批 usage 为 35,757 input、12,954 output、11,384 reasoning、48,711 total tokens

只有两个任务携带 describe 池，目标分别为萧炎和萧熏儿；池中五个 describe 指向青衫老者、月白衣袍老者、二十岁男子、少女和黄袍老者。模型没有把这些他人物证据归给当前目标，因此 describe 来源事实为 0 属于合理结果，不是 Grounding 丢失。

## 恢复记录

第一次执行完成 5 个任务后，HTTP chunked response 在读取尾部时触发 `IncompleteRead`。已完成任务均已落盘。Provider 随后增加 `HTTPException` 瞬态重试覆盖，第二次执行恢复前 5 个任务并完成剩余 13 个。详细记录见 `run-history.json`。

## 产物

- `m2-model-outputs.json`：模型最小输出
- `m2-grounded-results.json`：代码回填来源与 span 后的阶段输出
- `m2-envelopes.json`：代码编排信封和真实模型输入
- `source-n2-grounded-packets.json`：本轮重新物化的最新 N2 packet
- `source-n2-grounding-traces.json`：N2 exact precedence trace
- `provider-traces.json`：脱敏 Provider trace
- `summary.json`：整批汇总
- `failures.json`：失败任务，本次为空
- `run-history.json`：追加式执行/恢复历史

## 边界

本次完成证明结构化调用、可恢复执行和逐字 Grounding 链路可用，不等于人工人物归属质量 Gate。重叠 Chunk 中可能存在重复人物/事实；N3 冲突仲裁、describe 消费、remaining describe promotion 和跨 Chunk 人物合并尚未执行。
