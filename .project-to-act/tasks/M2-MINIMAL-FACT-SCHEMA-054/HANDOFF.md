# M2-MINIMAL-FACT-SCHEMA-054

任务已完成。M2 归属模式的模型输入只包含 target/describe 的人物称呼、允许 evidence 原文和 `chunk_text`；模型输出只包含 `belongs_to_target`，每条事实只有 `fact_quote/category/attribute/value`。promotion 模式沿用相同的无 ref/span 原则。

`describe_ref`、`fragment_ref`、`evidence_ref`、span、状态、hash、cache key 与 trace 只保存在代码信封或代码回填结果中。代码先查 target evidence，再要求 fact_quote 在单一 describe occurrence 中严格或纯空白等价匹配；不唯一时不归并、不删除。N3 只消费唯一 exact 认领且无跨人物冲突的 fact span，N2 packet 保持不可变。

Schema 升级到 `3.7.0-draft1`，M2 与 promotion envelope 升级到 v4；运行时保持 `0.1.0.dev6`，M2 仍未实现。60 项测试、Draft 2020-12 meta/schema 样例、旧字段拒绝、Project-to-Act、Lifecycle 和 diff 检查通过；真实 Provider 调用 0。Stage 5 保持 `in_progress`，未执行阶段 Gate。
