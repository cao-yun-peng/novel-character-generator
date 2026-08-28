# R1-PROMPT-AB-007 Handoff

- 状态：已完成；候选 v2.6 未通过切换门禁。
- A 组：冻结 `visual-extraction-prompt-v2.5`。
- B 组：`visual-extraction-prompt-v2.6`，阶段化并保持 R1/R2/R3 职责边界，作为实验候选保留。
- 真实实验：三轮、130 次 DeepSeek 调用，共记录 426,190 tokens；报告为 `data/diagnostics/r1-prompt-ab-v2.6/ab-report*.json`。
- 决策：生产/default Prompt 指针保持 v2.5。最终轮 B 虽提高 pass 并补足年龄信号，但 token 约增加 28%，deferred/warning/服务端拒绝均增加，并在真实多人样例中产生重复与 asserted/deferred 双写。
- 保留增量：`visual-observation-v3.4`、新增 deferred reason 和确定性字段语义门禁向后兼容，已进入默认链路，用于阻断 v2.5/v2.6 都可能产生的污染候选。
- 验证：49 项 R1 定向测试、203 项完整 Pytest、Ruff、Mypy 通过；无数据库迁移。
- 后续：若再设计候选，应减少 Prompt 规则堆叠并优先压缩实体重复、deferred 噪声和请求成本，不能在 v2.6 上直接继续打补丁后切换。
