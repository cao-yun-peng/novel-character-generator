# N3-PROMOTION-DOUPO-RUN-057

任务已完成。实现 `resolve_n3_chunk`、N3 DTO/Schema、来源回放及可恢复的 `run-deepseek-n3-promotion-from-m2-run` CLI；输入 M1/N2/M2 产物保持只读，新产物位于 `runs/doupo-first5-n3-promotion-dev9-20260831/`。

斗破前5章 N3 得到 18 个 exact target packet、50 条 exact facts、5 个 individual describe pool，消费 0、冲突 0、collective promotion task 0。5/5 promotion 调用成功，4 个 promoted character 的 11 条事实严格逐字 grounding。`青衫老者` 的 `青衫` 在池中出现两次，代码拒绝该候选并保留全部片段，任务明确进入 review。

最终验证为 90 tests passed、13 subtests passed；7 个 N3 chunk result、18 个 target packet、5 个 pool result、5 个 promotion grounded result 通过 Draft 2020-12 Schema 实例校验。Stage 5 仍为 `in_progress`，本任务不构成人工人物质量 Gate。
