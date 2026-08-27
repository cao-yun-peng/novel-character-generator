# OBS-RUN-001 Handoff

- 状态：已完成，待产品侧复核
- 目标：让每个文本分析 Run 的 R1、R2、R3 进度、诊断信号和结构化产出可查询、可视化。
- 已完成：`run-inspector-v1` 摘要、四类按需产出详情、Run 归属校验、工作台三阶段卡片、usage/attention 展示；R1 详情新增输入/结果哈希、Provider trace、人物候选、定位事实、时间信号和警告卡片，完整 JSON 改为折叠下钻。
- 数据边界：业务数据库仍是事实源；摘要不返回小说正文、Prompt、密钥或隐藏推理；计数不冒充准确率。
- 验证：Ruff 全仓通过；Mypy 115 个源码文件通过；全量 Pytest 157 passed；干净真实 run 的浏览器宽/窄屏检查通过，控制台 0 error/warning。
- 证据：`evidence/E-20260827-OBS-RUN-001.md`。
- 未覆盖：OpenTelemetry trace/span、采样与保留策略、Langfuse generation/eval 和两者的关联键。
- 下一建议：以 `run_id` 为业务 correlation key 接入 OTel，优先覆盖 API、Worker step、LLM call 和关键工具；之后再接 Langfuse。
