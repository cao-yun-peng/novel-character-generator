# M2 字段消歧开发与测试集审核说明

> 当前状态：离线工程已实现；测试集为 `m2-field-disambiguation-v1-draft1`，需要用户审核。没有运行真实 Provider，也不产生 active Observation。

## 1. 本阶段解决什么

M2 消费 N2 已唯一定位的 grounded facts，只负责把每条事实拆成原子视觉维度、绑定修饰载体并映射到规范字段。它不补 M1 漏掉的事实，不判断跨 Chunk 人物身份、时间持续性或 Promotion。

本版本冻结三项决定：

1. [`visual_field_catalog.py`](../src/novel_character_generator/domain/policies/visual_field_catalog.py) 是 M2 v1 唯一字段来源。只允许精确叶子，不接受 `face.*`、旧 alias 或临时字段。
2. `normalized_value` 统一为非空源语言字符串。近似年龄也保留为“十六七岁”这类字符串，不在 v1 混入 number/boolean/list union。
3. 模型只返回 `fact_index` 和 `semantic_unit_index`。代码注入 N2 `fact_id`、原始 `evidence_quote` 以及 `m1.../s1...`，并校验完整覆盖、载体引文和 catalog。

## 2. map、defer 与 reject

- `map`：事实明确、载体明确、字段在 catalog 中；可拆成一个或多个 mapping。
- `defer`：事实已经 grounded，但修饰范围或语义拆分有歧义，或 local context 不足。
- `reject`：事实不属于人物视觉契约，例如手持/邻近物、纯审美评价或非视觉内容。

M2 的 reject/defer 是字段语义判断；N2 的 rejected/deferred 是来源定位与结构安全分流，两者不能混称。

## 3. draft 测试集

测试集：[`m2_field_disambiguation_v1.json`](../tests/evaluation/m2_field_disambiguation_v1.json)

当前 9 个审核边界覆盖：

- 同一头发载体的颜色/长度拆分；
- 单件衣物的 type/color/material 共享载体；
- `蓝衣红裤` 的不同衣物绑定；
- 帽子与腰带的不同配饰绑定；
- 纹身与疤痕的不同身体载体；
- 歧义颜色修饰 defer；
- 手持书籍 reject；
- 纯美貌评价 reject；
- 近似年龄保持源语言字符串。

评分器分别报告 decision accuracy、mapping accuracy 和 semantic grouping accuracy。draft 状态会强制返回 `blocked_pending_user_review`，自动 self-test 全绿不等于真实模型质量通过。

## 4. 离线评分

保存的输出文件应是 `{case_id: FieldDisambiguationResult}` JSON 对象，然后运行：

```powershell
uv run python scripts/evaluate_m2_field_disambiguation.py `
  --dataset tests/evaluation/m2_field_disambiguation_v1.json `
  --outputs <saved-m2-outputs.json> `
  --report <report.json>
```

真实 Provider 运行必须在用户批准测试集后单独授权。本阶段没有使用 API Key、付费调用或持久化。
