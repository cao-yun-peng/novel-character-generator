# R1-GOLD-008 Handoff

- 状态：已完成；当前阶段仍为 5，生命周期 revision 2，L1。
- 历史 `visual_extraction_seed_v0.json` 未修改；新默认是 31 case 的 `visual_extraction_seed_v1.json` / `visual-observation-seed-v3`。
- v1 将输出分为 required、allowed、forbidden，并独立评分 mention、deferred 和 temporal；已纠正长袍/礼服/白衣/黑靴/清俊五类旧黄金边界。
- 6 个真实小说 Chunk 已增加 `audited-slice-v1` 约束：15 个 required、11 个 forbidden；它们是非穷尽审计切片，未标注输出只计数，不伪造 false positive。
- A/B 报告新增重复候选、重复 grounded fact 和 asserted/deferred 双写指标；逐 case 工具默认 v1，显式传 v0 仍可重放旧报告。
- 验证：21 项定向、225 项完整 Pytest、Ruff 全仓、Mypy 120 个源码文件通过；旧 v0 三案例报告离线重评分成功。
- 未运行真实 Provider，未修改生产 Prompt、数据库或 R2 身份解析。历史 v0 A/B 指标不能与 v1 横比；下一次 Prompt 决策必须在 v1 上重新建立真实基线。
