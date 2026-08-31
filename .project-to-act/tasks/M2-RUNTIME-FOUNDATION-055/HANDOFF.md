# M2-RUNTIME-FOUNDATION-055

任务已完成。M2 exact attribution 与 remaining-describe promotion 两种运行模式已经实现。模型只接收/返回项目文档冻结的最小字段；所有来源引用、span、hash、缓存键和复核原因由代码生成。

Exact 模式为每个 individual exact 生成一个携带全部 individual describe 的任务；事实优先绑定 target evidence，否则只接受单一 describe occurrence。Promotion 模式验证标签和事实唯一来源，拦截跨人物重叠，以最早事实位置稳定编号，并保留未分配残片。两种模式共用 DeepSeek 结构化 Provider，但 schema name 和 response schema 随任务提供。

N3 跨 exact 冲突仲裁与 describe 片段实际消费不在本任务内。M2 只输出已经安全回填来源的候选事实，供 N3 后续处理。Schema 为 `3.8.0-draft1`，运行时为 `0.1.0.dev7`；77 项测试和 13 个子测试、Draft 2020-12 meta/runtime packet 校验、Project-to-Act、Lifecycle 与 diff 检查通过。真实 Provider 调用 0，M2 模型质量仍需后续样本验收。
