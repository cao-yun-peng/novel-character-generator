# M1 真实集多老者 owner 消歧交接

## 已完成

- 将第 3 章 Chunk 中青衫管家与月白衣袍客人拆成独立局部 owner。
- 增加青衫老者视觉证据金标，并保持真实集待用户审核状态。
- 真实集升级为 v2.3-draft；Prompt v2.5、Dataset Schema/Rubric v2.2 与 approved 短集未修改。
- 全量 80 项测试、Ruff、Mypy、diff check 与 Project-to-Act validate 通过；未调用真实 Provider。

## Gate

- 本任务只修正 draft 金标，不代表真实 Chunk 质量 Gate 通过。
- `AGENT_LIFECYCLE.json` 存在既有结构不兼容，本任务不手工修改其 revision 或历史。

## 下一步

1. 用户继续审核 v2.3-draft 的 10 条真实 Chunk 金标。
2. 全部批准后，再明确授权 Prompt v2.5 的真实 Provider 运行。
