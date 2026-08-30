# M1 真实集与 Rubric v2.4 交接

## 已完成

- 已补全 001/002/003 的 owner alias，并为 007 增加逐字且唯一定位的替代跨度。
- Rubric v2.4 已增加 owner alias 冲突、候选多重匹配和唯一定位 quote fidelity 规则。
- v2.4-draft 金标自评分 10/10；同一真实 outputs 离线重评分为 0 pass / 5 review / 5 fail。
- approved 短集用 Rubric v2.4 回放仍为 16/16。
- 83 项测试、Ruff、Mypy、diff check 与 Project-to-Act validate 通过；未调用 Provider。

## Gate

- v2.4 数据集保持 draft，须重新人工审核。
- 本任务不通过 M1 真实 Chunk Gate，也不产生 active Observation。

## 下一步

1. 用户审核 v2.4-draft 新增的 alias 和 007 替代跨度。
2. 批准后冻结 v2.4，再开始 Prompt 优化。
