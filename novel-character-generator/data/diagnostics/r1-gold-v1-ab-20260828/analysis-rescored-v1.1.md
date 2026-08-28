# R1 黄金集 v1.1 离线重评分

## 范围

- 输入：`report.json` 已保存的 74 份原始候选输出。
- 执行：重新运行 grounding、adapter、contract metrics 和评分器；没有调用 DeepSeek，也没有修改生产 Prompt 指针。
- 输出：`report-rescored-v1.1.json`。
- SHA256：`15433C58A9D489C6E056F5AECA9506326EBB1980148943E8DEC1A92C48BB3954`。

## 测量层修正

- R1 视觉事实不再强制携带 R3 `life_phase_key`；阶段要求只在 temporal signal 中评分。
- 黄金集增加受控的 owner/surface 别名、值异体和可选安全 deferred；未列 deferred 仍然失败。
- mention 类型优先按原始且可在原文中定位的 entity candidate 评分，避免唯一定位失败掩盖模型已经正确给出的 mention 类型。
- temporal 引文允许黄金片段与模型片段的窄范围包含关系；相同 owner/kind/label/evidence 的重复信号只计入重复指标，不重复扣分。
- 同一引文同时出现在 asserted candidate 与 deferred item 中改为硬失败，并单独计数。
- required 配对不再用完全无关的同 owner/同 field 事实遮蔽真正缺失；至少 value 或 evidence 必须落入黄金边界。
- 真实 Chunk 10 的徽记改为 `accessories.insignia`，男子/青年作为受控称谓别名；《水浒传》样例移除依赖 R2 身份归并的“天师=道童”年龄要求。

## 重评分结果

| 范围 | A / v2.5 旧 → 新 | B / v2.6 旧 → 新 |
|---|---:|---:|
| Seed pass/review/fail | 13/7/11 → 20/1/10 | 12/7/12 → 22/1/8 |
| Seed TP/FP/FN | 33/7/7 → 36/3/4 | 34/7/6 → 37/3/3 |
| Real pass/review/fail | 0/0/6 → 0/0/6 | 1/0/5 → 2/0/4 |
| Real mention failures | 2 → 0 | 3 → 0 |
| Real temporal failures | 4 → 2 | 4 → 0 |

新评分同时暴露此前只统计、未进入 case Gate 的排他冲突：A 在真实切片有 3 次，B 有 5 次；加上 seed 后总数仍为 A=3、B=6，与原始 contract metrics 一致。

## 剩余问题归因

- Prompt/模型：模糊代词被直接断言；估龄被断言且未 deferred；阶段信号漏抽；真实 Chunk 的衣袖、眉毛、手部事实漏抽；v2.6 仍有大量 asserted/deferred 双写。
- Adapter/字段政策：`clothing.coverage` 正确候选被语义门禁拒绝；`accessories.earring` 未归一到 `accessories.earrings`；银色假发未映射到 `disguise.hair_color`。
- 仍保留的 review：多人多衣物场景中的裸颜色值缺少载体。这是明确的产品字段策略，不作为同义词自动放宽。
- 黄金/评分：本轮已确认的问题已修；没有为了让模型过关而删除模糊 owner、估龄、held-object 或排他双写等安全反例。

## 决策

黄金集 v1.1 与评分器可用于下一轮适配层/Prompt 修复；当前生产 Prompt 仍不能据此宣称通过发布 Gate。v2.6 虽然新 rubric 下 seed recall 更高，但 token 仍比 v2.5 高 27.9%，且总 asserted/deferred collision 为 6 对 3，因此默认继续保持 v2.5。
