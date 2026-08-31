# Promotion 部分接受离线重放报告

## 运行方式

- 来源：`runs/doupo-first5-n3-promotion-dev9-20260831`
- 策略：`promotion-partial-fact-acceptance-v1`
- 模型调用：0
- 旧 run：只读，未覆盖

## 结果

- 重放 promotion 模型输出：5/5
- promoted characters：5（旧策略为 4）
- promoted grounded facts：12（旧策略为 11）
- review issues：1，仍为 `ambiguous_promotion_fact`
- 文档级事实：61，其中 exact 49、promoted 12
- 重叠 Chunk 副本：安全删除 1 条，保留 62 个来源 occurrence

## 青衫老者修复结果

- 人物 `青衫老者` 已创建。
- 唯一匹配事实 `浑浊的老眼` 已接受，Chunk span `[616,621)`，文档绝对 span `[7366,7371)`。
- `青衫` 匹配 2 个 occurrence，没有猜测具体位置；review 明确记录 `fact_quote=青衫`、`candidate_occurrence_count=2`。
- 两个 `青衫` 片段均保留在 `unassigned_fragments`。

## 能力边界

- 只重放确定性 Grounding，不重新调用或修改模型。
- 标签无效、全部事实失败或跨人物重叠时仍失败关闭。
- 单次样本修复通过不代表完整人工质量 Gate 已通过。
