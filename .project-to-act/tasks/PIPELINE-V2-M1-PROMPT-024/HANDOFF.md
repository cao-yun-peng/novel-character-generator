# M1 Prompt v2.3–v2.5 优化交接

## 已完成

- v2.3 将 Prompt 优先级重构为“召回 → 语义/语法完整与唯一定位 → 最后最小化”，修复 v2.2 的否定漏召回和推断跨度失败。
- v2.4 禁止 body part、衣物、配饰和外貌特征充当人物 mention。
- v2.5 进一步要求 owner mention 必须正向识别一个具体局部人物；疑问、否定归属、未知人物表达不能作为 owner anchor。
- 三个版本均使用同一模型、approved 16 条短集和 Rubric v2.2 真实运行，输出保存在独立目录。
- 最终 v2.5 为 16 pass / 0 review / 0 fail，六项核心质量指标均为 100%。
- 全量 79 项测试、Ruff、Mypy、diff check 与 Project-to-Act validate 通过。

## Gate

- approved 短回归 Gate：通过。
- 10 条真实 Chunk：仍为 draft，尚未运行；完整 M1 evidence Gate 仍未通过。
- v2.5 在开发/回归短集上的 16/16 不能替代未见保留集，需要用真实 Chunk 和近邻样本继续检查过拟合。
- `AGENT_LIFECYCLE.json` 的既有结构仍无法通过当前 lifecycle validator，本任务未修改其 revision 或历史。

## 下一步

1. 用户审核 10 条真实 Chunk 金标。
2. 批准后以 Prompt v2.5 运行真实 Chunk 诊断。
3. 为否定、推断关系和 unknown owner 准备未见近邻切片，确认 v2.5 的泛化性。
