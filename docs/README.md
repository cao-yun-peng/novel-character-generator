# V2 技术文档索引

当前文档只描述证据优先语义流水线 V2。

| 文档 | 内容 |
|---|---|
| [V2 总契约](27-semantic-pipeline-v2-contract.md) | N0–N11、M1–M5 的职责、输入输出、失败路由和质量 Gate |
| [M1 审核说明](28-m1-local-observation-evaluation.md) | M1 审核集、评分边界与离线评分 |
| [M1 真实基线](29-m1-real-baseline-evaluation.md) | 真实运行结果、失败归因与当前 Gate |
| [M1 Prompt 与输出指南](30-m1-prompt-and-output-guide.md) | M1 模型线、代码物化字段和真实 Chunk 金标 |
| [M2 审核说明](31-m2-field-disambiguation-evaluation.md) | 精确字段目录、最小模型线和 draft 测试集 |
| [机器可读 Schema](contracts/semantic-pipeline-v2-model-schemas.json) | M1–M5 条件 Schema 原型 |
| [M3–M5 Prompt](prompts/semantic-pipeline-v2/) | 尚待实现的身份、时间和联合复核系统提示词 |

运行时使用的 M1/M2 Prompt 位于 `src/novel_character_generator/infrastructure/llm/prompts/`，它们是实现的唯一提示词来源。
