# R2-SHARD-004 Handoff

- 状态：自动化增量完成，待真实新 Run 复核
- 目标：收敛 frontier 使用失败数据校准的四重预算有界分片；遗漏记录有限 repair；耗尽后显式警告并安全降级。
- 当前不变量：固定十章/尾批边界、dirty frontier、完整 memory、final-only 物化和模型身份决策边界不变。
- 预算原子性：同一 EntityMemoryRecord 不拆分；原子记录超预算失败关闭。
- 数据边界：Trace 只含计数、预算、哈希、覆盖率和动作状态。
- 已完成：record/mention/完整请求预计输入/预计输出四重预算原子分片、安全覆盖分析、最多两轮遗漏 repair、调用预算兜底、`completed_with_warnings` 恢复、RunEvent/Inspector/UI。
- 配置默认值：16 records、32 mentions、12,000 完整请求预计输入 token、4,500 预计输出 token、2 轮 repair；真实 Provider 的 system prompt 与 JSON Schema 固定开销进入输入估算。
- 校准依据：历史批次 35/35 mention 全覆盖；46 mention 仅覆盖 15、48 mention 仅覆盖 6。默认值是失败数据驱动的保守起点，不是 Provider 硬上限。
- 验证：172 项完整 Pytest、全项目 Ruff、115 个源码文件 Mypy、Node 语法通过；四重预算、分片/repair/警告/恢复失败路径均有自动反例。
- 最新证据：`evidence/E-20260827-R2-SHARD-004-CAL1.md`；初版证据保留为 `evidence/E-20260827-R2-SHARD-004.md`。
- 未覆盖：稳定人物候选检索、有界文末历史 sweep、真实付费 Provider 质量与成本复核。
