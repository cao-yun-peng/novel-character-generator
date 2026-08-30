# M1 v2.2 短测评集批准与真实测试交接

## 已完成

- 用户已批准 16 条短金标；数据集冻结为 `m1-visual-evidence-short-v2.2`、`review_status=approved`。
- 离线金标自测 16/16 通过；全量 79 项测试、Ruff、Mypy、diff check 和 Project-to-Act validate 通过。
- 使用 `deepseek-v4-flash` 与 Prompt v2.2 完成 16 条真实诊断，全部一次调用成功并经过 deterministic validation。
- Rubric 结果为 14 pass / 0 review / 2 fail；失败是 `negated-004` 漏召回和 `inferred-age-006` 引文裁掉“从他”。
- 输出、报告和含 prompt/dataset/rubric/validation hash 的 run manifest 已保存到 `data/diagnostics/m1-v2.2/`。

## Gate

- 短数据集审核 Gate：通过。
- Prompt v2.2 M1 质量 Gate：未通过，不得据此发布。
- 10 条真实 Chunk 数据集：仍为 draft，不在本次批准范围。
- `AGENT_LIFECYCLE.json` 的既有结构仍无法通过当前 lifecycle validator，本任务未修改其 revision 或历史。

## 下一步

1. 为否定外貌和推断跨度补充邻近反例，再设计下一版 Prompt。
2. 用户审核 10 条真实 Chunk 金标。
3. 新 Prompt 版本必须重新运行 approved 短集，不覆盖本次 v2.2 结果。
