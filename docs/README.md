# V2 技术文档索引

当前文档只描述证据优先语义流水线 V2。

| 文档 | 内容 |
|---|---|
| [V2 总契约](27-semantic-pipeline-v2-contract.md) | N0–N11、M1–M5 的职责、输入输出、失败路由和质量 Gate |
| [M1 v1 审核说明](28-m1-local-observation-evaluation.md) | legacy M1 审核集、评分边界与离线评分 |
| [M1 v1 真实基线](29-m1-real-baseline-evaluation.md) | legacy 真实运行结果和失败归因 |
| [M1 v1 Prompt 与输出指南](30-m1-prompt-and-output-guide.md) | 当前已实现 v1 模型线、代码物化字段和历史金标 |
| [M2 v1 审核说明](31-m2-field-disambiguation-evaluation.md) | legacy 精确字段模型线和暂停审核的 draft1 |
| [M1/M2 v2 边界决策](32-m1-m2-evidence-semantic-boundary-v2.md) | M1 证据发现、已实现的 N2 v2 证据固化、M2 局部语义解析目标协议与迁移 Gate |
| [机器可读 Schema](contracts/semantic-pipeline-v2-model-schemas.json) | M1–M5 条件 Schema 原型 |
| [M3–M5 Prompt](prompts/semantic-pipeline-v2/) | 尚待实现的身份、时间和联合复核系统提示词 |

运行时使用的 M1/M2 Prompt 位于 `src/novel_character_generator/infrastructure/llm/prompts/`。legacy v1 Prompt 仍服务旧链；M1 v2 使用主 Prompt v2.8，由独立 shadow Provider 运行。N2 v2 确定性切片已实现但尚未接入默认主链；M2 v2 尚未实现。
