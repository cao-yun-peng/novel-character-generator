# M1 v2.5 approved 真实 Chunk 失败分析

## 运行结论

- Run：`m1-v25-real-v23-approved-20260829`
- 完整工件：attempt 2，10 条调用完成；8 条通过 deterministic validation，2 条被确定性校验拒绝。
- Rubric：0 pass / 1 review / 9 fail。
- 核心指标：evidence recall 0.50；candidate precision 0.2453；quote fidelity 0.9878；required owner recall 0.4091；owner binding precision 0.2453。
- 本结果未达到 M1 真实 Chunk Gate，也不构成发布证据。

## 测量有效性问题

- 001：模型使用明确人名“萧媚”，owner 金标只接受泛称“少女”。
- 002：模型使用明确人名“萧薰儿”，owner 金标只接受“少女/紫裙少女”。
- 003：模型使用完整人物短语，owner 金标只接受较短的“孩子/男孩”。
- 007：模型给出语义成立但比唯一金标跨度更短的相邻视觉证据；需要复核是否增加可接受逐字替代跨度。

以上问题会造成正确证据被 owner exact-match 或单一金标跨度拒绝，因此不能把原始 0 pass 全部归因于 Prompt。若修改已批准金标，必须升级到新数据集版本并重新人工审核。

## 明确的模型/Prompt 问题

- 004：模型把跨句长描述合并，并改变原文换行，触发 `visual_evidence_quote_not_in_chunk`。
- 005：输出重复出现的“青衫老者”短引文，触发 `visual_evidence_quote_not_unique_in_chunk`；同时把月白衣袍客人绑定到歧义“老者”。
- 006：遗漏少女相对年龄。
- 008：遗漏换鞋 presentation，且年龄、金环引文裁掉了人物定位起点。
- 010：服饰引文混入兵器和坐骑，触发 forbidden candidate。
- 009：四个 required transformation 候选均命中，但额外合理视觉候选按当前非穷举规则进入 review。

## 建议顺序

1. 先修复 Dataset/Rubric 的 owner alias 与可接受跨度覆盖，形成 v2.4-draft 并重新审核。
2. 用冻结的 v2.4 重新评分同一 outputs，分离评分问题与模型问题。
3. 再针对跨句逐字性、唯一定位、人物锚点、漏召回和服饰/持物边界优化 Prompt。
