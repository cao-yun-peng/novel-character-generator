# R1-EVAL-004 Handoff

- 状态：待复核
- 目标：为视觉抽取评测增加结构、值、证据分层及三态结果。
- 安全边界：未知语义不自动通过；无 LLM judge；不修改生产抽取链。
- 已完成：rubric v2、局部 accepted/rejected value、证据精确/包含/未知/未落地边界、离线重评分模式和 126 项全量回归。
- 结果：v2.1 离线重评分为 3 pass / 4 review / 0 fail；v2.2 定向结果为 2 pass / 1 review / 0 fail。
- 证据：`evidence/E-20260826-R1-EVAL-004.md`。
- 已知限制：review 决策目前通过人工修改版本化 seed 写回；没有批量审核 UI/CLI。
- 下一建议：复核纹身 value 的新措辞，再继续扩充 30–40 case。
