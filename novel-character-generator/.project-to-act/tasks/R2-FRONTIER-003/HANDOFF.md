# R2-FRONTIER-003 Handoff

- 状态：自动化增量完成，待真实新 Run 复核
- 目标：十章收敛只处理当前批次 dirty non-stable memory，历史未变化 unresolved 不重复消耗输出。
- 当前不变量：固定十章/尾批边界、完整 memory 保留、final-only 物化、身份决定仍由模型给出。
- 可观测性：RunEvent/Inspector 显示 non-stable 总量、frontier/deferred 记录与 mention 数、Provider 原始覆盖和 omission、收敛后状态。
- 不在本轮：frontier 分片、continuation/repair、高置信直接物化、历史 unresolved 文末全量回收。
- 下一 Gate：核心/失败/恢复路径自动测试与静态检查全部通过。
- 已完成：dirty frontier 选择、frontier 外 memory 保留、独立 frontier RunEvent、Provider 原始覆盖/omission 指标、Inspector 汇总/详情和工作台展示。
- 验证：18 项定向测试、全量 Pytest、全项目 Ruff、115 个源码文件 Mypy、Node 语法均通过。
- 证据：`evidence/E-20260827-R2-FRONTIER-003.md`。
- 未覆盖：未执行真实付费 Provider 新 Run；单 frontier 分片、omission repair、stable context 检索和有界 final sweep 尚未实现。
- 下一建议：实现 token/mention-aware convergence sharding，并对每个 shard 做缺失 mention continuation/repair。
