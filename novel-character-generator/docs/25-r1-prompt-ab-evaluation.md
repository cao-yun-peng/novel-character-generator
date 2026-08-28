# R1 Prompt v2.5 → v2.6 A/B 评测计划

## 目的

判断阶段化 Prompt 是否在不削弱失败关闭边界的前提下，提高真实小说文本中的人物提及、独立视觉事实拆分、字段语义、证据精确性和 deferred 可诊断性。

## 对照约束

- A/B 使用同一 Provider、模型、wire API、temperature、thinking/reasoning、token 上限和输出 Schema。
- 每个样例分别独立调用；不共享上下文或响应。
- A 使用冻结的 `visual-extraction-prompt-v2.5`；B 使用候选 `visual-extraction-prompt-v2.6`。
- 保存脱敏的统计和受控诊断文件；不在项目账本复制原始小说全文或密钥。

## 样例切片

1. 真实《斗破苍穹》短文分块：覆盖泛称、显式姓名、服装/配饰、年龄和相邻人物。
2. 跨题材既有真实诊断文本（存在时）：覆盖多人、重复证据和复合外观。
3. 冻结 seed 关键反例：同字段多实例、衣物归属、明确/模糊代词、年龄双轨、物品误入服装、审美评价和 deferred 分类。

## 当前黄金集版本

- `visual_extraction_seed_v0.json` 永久保留，用于复现 2026-08-27 已完成的历史 A/B；它仍使用 `visual-observation-seed-v2`，不再代表当前字段契约。
- `visual_extraction_seed_v1.json` 是当前默认硬黄金集，dataset 为 `v1.1`，使用 `visual-observation-seed-v3.1`。它含 31 个通用独立案例、40 个 required 事实、5 个 allowed 事实、3 个 allowed deferred 和 17 条 forbidden 规则。
- `r1_prompt_ab_real_v1.json` 中 6 个真实 Chunk 使用 `audited-slice-v1.1` 标注，共 14 个 required 事实和 11 条 forbidden 规则。真实 Chunk 不是穷尽标注；未列出的事实会计数为 `unlisted_observation_count`，但不会被误判为 false positive。
- v0 与 v1 的 TP/FP/FN 不能直接横向比较。任何新的 Prompt 切换结论必须在同一 v1 数据、同一模型和同一参数下重跑 A/B。

## v3 黄金答案格式

- `required_observations`：必须输出；缺失为 false negative，字段、人物或阶段不匹配为结构失败。
- `allowed_observations`：可以输出但不强制；正确输出不算 false positive，缺失不扣分。
- `forbidden_observations`：一旦命中立即失败，并保存人工给定的原因码。
- `expected_mentions`：按原文 surface 和 `explicit_name/descriptor/pronoun/unknown` 类型独立评分；视觉事实正确不能掩盖 mention 类型错误。
- `expected_deferred_items`：按 reason code 和原文引文评分，专门验证模糊 owner、模糊证据和推断事实的失败关闭分支。
- `allowed_deferred_items`：允许模型对不可视觉化或明确未描述内容给出安全 deferred，但不强制输出；未列出的 deferred 仍按默认规则失败。
- `expected_temporal_signals`：按 kind、label、原文引文及可选人物 owner 评分；年龄事实不能只抽值而遗漏时间证据。
- required/allowed 支持受控 `accepted_character_names`，mention 支持受控 `accepted_surfaces`；这只承认黄金明确列出的同一 Chunk 称谓，不执行自动身份归并。
- temporal 信号评分允许黄金引文与 grounded 引文的窄范围包含关系，并先按 owner/kind/label/evidence 去重；重复量单独报告。
- 所有 required/allowed/deferred/temporal 引文在加载数据集时必须能在原文中精确找到；案例 ID 必须唯一；v3 系列禁止混入旧 `expected_observations` 写法。

## 指标与门禁

- Schema 成功率：两组都必须为 100%。
- Grounding：无法定位、歧义证据和非规范字段拒绝数，B 不得高于 A。
- 人物边界：descriptor 不得成为 explicit_name；模糊代词不得形成 asserted fact。
- 事实粒度：同字段不同部位/物品分别保留；不同维度不得合并。
- 年龄：明确年龄同时提供视觉事实和时间证据；外貌估龄不得 asserted。
- deferred：unsupported、inferred、uncertain、ambiguous owner 可区分。
- 排他分支：同一事实不得同时 asserted 与 deferred；完全相同的候选或 grounded fact 不得重复。
- 质量评分：B 的 pass 数不低于 A，fail 数不高于 A；人工关键项无安全回退。
- 成本：记录 input/output/reasoning token 和延迟；质量通过后再评估增量是否可接受。

## 决策

- 全量切换：所有硬门禁通过，且 B 整体优于或等于 A。
- 保留 A：任何安全项回退，或 B 只有措辞变化而无质量收益。
- 继续调优：B 改善目标项但出现可局部修复的非安全回退；保留实验记录，不把候选误写成已通过。

## 2026-08-27 实验结论

在用户明确授权把指定小说 Chunk 发送给 DeepSeek 后，共完成三轮、130 次真实 Provider 调用，记录 375,679 input tokens、50,511 output tokens，总计 426,190 tokens；所有请求均保持同 Provider、模型、参数、Schema 与样例边界。

最终一轮中，A（v2.5）与 B（v2.6）的 seed `TP/FP/FN` 同为 `16/4/1`，B 的 `pass/review/fail` 从 A 的 `3/5/3` 改善为 `5/3/3`，年龄信号覆盖从 `1/5` 改善为 `3/3`。但 B 的总 token 从 52,683 增至 67,407（约 +28%），deferred 从 4 增至 22，warning 从 32 增至 54，服务端拒绝从 27 增至 31；真实《水浒传》样例还出现人物/事实重复、手持物和瞬时表情被同时 asserted 与 deferred 的问题。

因此 B 未通过“服务端拒绝/warning 不增加且成本可接受”的完整切换门禁。当前默认 Prompt 继续使用冻结的 `visual-extraction-prompt-v2.5`，`visual-extraction-prompt-v2.6` 只保留为可复现实验候选；`visual-observation-v3.4` 的确定性安全门禁独立保留，因为它向后兼容并能阻断两组模型产生的污染候选。三轮报告位于 `data/diagnostics/r1-prompt-ab-v2.6/`。

上述数字来自旧 v0 rubric，只用于复现实验历史，不能作为 v1 黄金集下的当前质量结论。升级黄金集没有发起新的 Provider 调用；下一次真实 A/B 才会产生 v1 下的新基线。

## 2026-08-28 v1.1 测量层修正

首轮 31 seed + 6 real、A/B 共 74 次调用发现阶段键、同义值、安全 deferred、temporal 精确匹配、owner/surface alias、raw mention 与真实身份依赖标注会制造假失败。v1.1 修正这些测量问题，并把 asserted/deferred 同引文双写提升为 case 级硬失败。

使用原报告保存的 candidates 离线重评分后，A 的 seed 从 `13/7/11` 变为 `20/1/10`，B 从 `12/7/12` 变为 `22/1/8`；真实 mention failure 均降为 0。详细归因见 `data/diagnostics/r1-gold-v1-ab-20260828/analysis-rescored-v1.1.md`。这次离线重评没有产生 Provider 调用；默认 Prompt 仍保持 v2.5。
