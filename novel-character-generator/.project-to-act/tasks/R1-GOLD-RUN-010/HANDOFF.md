# R1-GOLD-RUN-010 Handoff

- 状态：已完成真实 A/B 与逐层归因。
- 范围：31 个 v1 硬黄金 case + 6 个真实审计 Chunk；v2.5 与 v2.6 各一次，74/74 调用成功。
- 报告：`data/diagnostics/r1-gold-v1-ab-20260828/report.json`；分析：同目录 `analysis.md`。
- v2.5 seed 为 13 pass / 7 review / 11 fail；v2.6 为 12 / 7 / 12。v2.6 recall 略高，但 tokens +27.9%，deferred 6→21，asserted/deferred collision 3→6，不切换。
- 当前黄金/评分至少影响 7 个 seed 和 5 个真实 Chunk：阶段键层级、accepted variants、安全 deferred、temporal 精确匹配、owner alias、grounded mention 评分以及 identity-dependent real gold。
- 独立系统缺陷仍成立：模糊 owner 被 asserted、估龄通过截短引文绕过、coverage 正确候选被适配器拒绝、earring 单复数未归一、年龄排他分支双写、手持物污染。
- 下一步先修测量层并对本报告离线重评分；之后再修适配层和剩余 Prompt，不应立即再做 74 次全量调用。
