# R1 v1 黄金集真实 A/B 归因

## 结论

本轮不能把失败全部归因于 Prompt，也不能把当前 v1 分数直接当成发布 Gate。结果同时证明：

1. 黄金/评分契约仍有若干确定问题，至少影响 7 个 seed 案例和 5 个真实审计 Chunk 的最终状态。
2. Prompt 与确定性适配层存在独立真实缺陷；即使修正黄金，这些案例仍会失败。
3. v2.6 没有形成可切换优势：召回略高，但 pass 更少、成本约增加 27.9%、deferred 和 asserted/deferred 双写更多。

## 冻结运行条件

- Provider：DeepSeek（项目当前配置）。
- Model：`deepseek-v4-flash`。
- Schema：`visual-observation-v3.4`。
- A：`visual-extraction-prompt-v2.5`。
- B：`visual-extraction-prompt-v2.6`。
- 样例：31 个 v1 硬黄金 + 6 个真实审计 Chunk。
- 调用：74/74 成功；记录 tokens 242,288；Schema/transport 运行期失败 0。
- 报告：`report.json`，SHA256 `6F8560A940269953F9F28600AA520E3D67E0823433CD7F0C72403882D0D0BAB9`。

## 汇总

| 指标 | v2.5 | v2.6 |
|---|---:|---:|
| seed pass / review / fail | 13 / 7 / 11 | 12 / 7 / 12 |
| seed TP / FP / FN | 33 / 7 / 7 | 34 / 7 / 6 |
| seed precision / recall | 0.825 / 0.825 | 0.829 / 0.850 |
| real audit pass / fail | 0 / 6 | 1 / 5 |
| total tokens | 106,292 | 135,996 |
| deferred | 6 | 21 |
| warnings | 44 | 55 |
| asserted/deferred collisions | 3 | 6 |
| exact duplicate candidates / grounded facts | 0 / 0 | 0 / 0 |

## 已确认的黄金或评分问题

| 范围 | 问题 | 影响 |
|---|---|---|
| `phase-childhood`、`phase-adulthood` | R1 required observation 强制 `life_phase_key`，但阶段归属本应由 temporal/R3 独立评分 | 正确视觉事实被同时计为 FP+FN |
| `explicit-absence` | `无疤痕` 未列为 `无` 的 accepted value | 两组无意义进入 review |
| 安全 deferred | `unsupported_visual_field` 用于排除的审美评价、瞬时表情或“未描述”内容时仍被计为 fail | `reported-attractiveness`、`face-description`、`eye-color-not-expression` 被过度惩罚 |
| temporal scorer | label/evidence 只接受精确枚举，不使用 observation 已有的窄 containment 兼容；重复信号也未先按语义键去重 | 相对年龄和真实年龄信号产生假失败 |
| real chunk 10 | 黄金 owner 固定为“男子”，模型代表名可合理使用“青年”；`clothing.insignia` 又违反当前 clothing canonical policy，正确字段应是 `accessories.insignia` | 两组真实多人样例出现多项假 FN |
| mention scorer | mention 类型取 grounded packet；原始 entity 正确但重复姓名无法唯一定位时会被误报为 missing mention | 真实 chunk 4/12 的显式姓名被假判缺失 |
| real Shuihu chunk | 黄金把“年幼”绑定到“天师”，依赖 R2 身份关系；R1 单 Chunk 视觉审计不应以此作为必选 owner | 两组均出现身份依赖型假 FN |

此外，疤痕、眼神、纹身、胡须等多个 review 只是明显的值措辞变体；多衣物颜色是否必须在 value 中保留载体仍是产品政策问题，当前保留 review 是合理的人工决策点。

## 已确认的 Prompt/适配层真实问题

| 层 | 问题 | 证据案例 |
|---|---|---|
| Prompt | 两组都把有两个可能先行词的“他的头发”绑定为 asserted fact，且没有 `ambiguous_entity` deferred | `ambiguous-owner` |
| Prompt + evidence gate | 两组都把“看上去约四十岁”作为 asserted age；模型缩短 evidence 为“约有四十岁”，使适配层看不到推断提示词 | `approximate-age-perception` |
| Adapter | 正确的 `clothing.coverage=赤着上身` 被 `clothing_coverage_without_coverage` 拒绝 | `clothing-coverage-not-body-build` |
| 字段规范化 | 两组使用 `accessories.earring`，黄金/下游使用 `accessories.earrings`，当前没有单复数别名 | `descriptor-not-explicit-name` |
| 排他分支 | v2.5 输出 inferred candidate 却不写 deferred；v2.6 同一年龄同时 asserted 和 deferred。当前 scorer 没有把双写升级为 case fail | `inferred-age-exclusive-deferred` |
| Prompt | 重复“白衣”证据虽然被 grounding 安全拒绝，但两组都没有返回 `ambiguous_evidence` deferred | `repeated-phrase-ambiguous-owner` |
| Prompt | 假发只输出 accessory，没有输出当前黄金要求的 disguise hair color；额外 accessory 本身可合理允许 | `disguise-overlay` |
| Prompt | 真实《水浒》Chunk 中铁笛、黄牛、动作/表情被当配饰或人物事实，并大量 asserted/deferred 双写 | `shuihu-chunk-5-descriptor-dialogue` |
| Temporal | v2.5 年龄候选 7 个但只有 1 个带信号；v2.6 为 6/6，但 chunk/fact 信号存在重复与 owner/evidence 不稳定 | seed 与真实年龄案例 |

## 判断

- 黄金集不是“完全没问题”：当前 pass/fail 数会高估错误，尤其不能据此判定 6 个真实 Chunk 全部失败。
- 黄金集也不是失败主因：模糊 owner、外貌估龄、coverage 门禁、字段别名和手持物双写均是可直接从原始候选与 grounding 证明的系统问题。
- v2.6 暂不应切换：它只小幅提高结构召回，未提高 pass，总 tokens 增加 27.9%，deferred 由 6 增至 21，双写由 3 增至 6。

## 建议顺序

1. 先修测量层：R1 observation 不携带阶段硬约束、temporal 窄包含/去重、accepted variants、安全 deferred、owner/surface aliases、raw mention 类型评分、真实 insignia 与 identity-dependent gold。
2. 对本报告离线重评分，不再调用 Provider；确认新分数只改变假失败。
3. 再修适配层：coverage marker、earring alias、推断年龄必须保留推断 cue、asserted/deferred 排他 Gate。
4. 最后针对仍失败的 Prompt case 调整提示词并做小样本 A/B；不要立即再次运行 74 次全量。
