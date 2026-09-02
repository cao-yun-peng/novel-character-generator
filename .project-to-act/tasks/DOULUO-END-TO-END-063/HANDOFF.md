# DOULUO-END-TO-END-063

进行中。输入共 38,251 字符，标题虽称前20章但实际只有第1至19章。计划使用 2,500 字符 Chunk、250 字符重叠、8,192 最大输出预算，依次运行 M1→M2→N3/promotion→document evidence→M3 identity→profiles。所有阶段可恢复，真实 API Key 不落盘。

2026-09-01 恢复点：M1 首轮 14/17；将输出预算提高到 16,384 后，第 12、14 个无效 JSON Chunk 已恢复，当前 16/17。第 17 个 Chunk 的上一轮恢复因瞬时网络错误在 3 次有界重试后失败；下一动作只重试第 17 个 Chunk，复用其余 16 个缓存。

2026-09-01 阻塞点：M1 已完成 17/17；M2 已完成 32/32，得到 84/84 grounded facts 和 1 个 `multiple_target_occurrences` review。N3 已完成并缓存 8/11，得到 8 个 promoted characters、42 个 grounded facts；剩余 `男孩儿`、`高大苍老的男人`、`看门的青年` 三项可恢复。前两项网络重试耗尽，第三项明确为 `ProviderInsufficientBalanceError`/HTTP 402。余额/额度恢复后对同一 N3 命令和目录续跑；完成前不得生成部分 document evidence 或继续 M3。

2026-09-01 解除阻塞：用户确认 DeepSeek 已充值。任务恢复为进行中，继续使用原 N3 目录，只调用剩余 3 项并复用 8 个成功缓存。

2026-09-01 完成：N3 恢复为 11/11；文档汇总得到 129 facts/130 occurrences；M3 63/63，得到 47 same、15 uncertain、1 different，严格隔离 9 条 grounding issue；最终生成 8 profiles、106 assigned/23 unassigned facts、10 unresolved、17 review、1 cannot-link。118 tests、67 个 Schema 实例、129 fact/130 occurrence/105 identity evidence 原文回放、治理和 Lifecycle 校验通过。Stage 5 保持 in_progress，任务完成不替代人工模型质量 Gate。
