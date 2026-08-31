# M1-GROUNDING-SCOPE-051

实现任务已完成。用户明确取消的 mention occurrence 位置方案未进入运行时；`mention_quote` 只做严格存在性验证。Evidence span 继续作为事实追溯基础。严格匹配失败时仅允许纯 Unicode 空白差异，恢复结果回填 raw source quote、span 与 hash；非空白变化关闭失败。`mention_scope=collective` 保留在 quarantine，并从 `single_character_mentions` 排除。

契约升级到 `3.5.0-draft1`，grounded packet 升级到 `grounded-character-packet-v4`，运行时升级到 `0.1.0.dev4`。旧 `m1-chunk-result-v1` 不允许与新批次续跑混用，必须使用新输出目录。本轮没有调用真实 Provider，也没有改写既有 `runs/` 产物。

验证：51 项自动测试通过；Draft 2020-12 Schema 元验证、Project-to-Act 验证、Agent Lifecycle 验证和 `git diff --check` 均通过。Stage 5 仍为 `in_progress`，未执行 Gate 决策。
