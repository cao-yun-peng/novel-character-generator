# M1 v1 Prompt、模型线字段与真实 Chunk 审核指南

> 历史结论：15 条短回归集与 6 条真实 Chunk 均按 M1 v1 rubric 批准；Prompt `local-observation-discovery-prompt-v1.6` 最终重评分 5/6。该 Prompt、wire 和评分口径现为 legacy implemented v1，不再代表目标 M1 v2。
>
> 已确认的新边界是：M1 只返回人物视觉相关的连续证据和可选局部 owner；事实原子化、field、epistemic 与显式 signal 由 M2 负责。完整目标协议见 [`32-m1-m2-evidence-semantic-boundary-v2.md`](32-m1-m2-evidence-semantic-boundary-v2.md)。在 v2 rubric 下，完整保留“年龄、英俊、身材挺拔”但未按 body 拆 fact 不再自动算 M1 失败。

## 1. 当前已实现 v1 Prompt 在哪里

运行时唯一提示词是 [`01-local-observation-discovery.system.md`](../src/novel_character_generator/infrastructure/llm/prompts/01-local-observation-discovery.system.md)。该文件就是 Provider 实际加载的完整 system prompt，不在本文复制第二份，以免两份内容以后漂移。

- Prompt version：`local-observation-discovery-prompt-v1.6`
- 当前文件 SHA-256：`dc9f5242d1b264ccbfe99fcc03751bbf00d70ec882d46438b1790c4aa5af4f12`
- 模型线 schema：`local-observation-model-wire-v1`
- 内部输出 contract/schema：`local-observation-contract-v1.1` / `local-observation-discovery-v1.1`

以下内容记录 v1 的历史演进，不再作为 v2 目标边界。v1.2 修复年龄、presentation、unresolved，v1.3 删除机械字段，v1.4 明确变化信号与事实类别，v1.5 重定直接近似年龄并确认脱下穿戴物，v1.6 加强逐字引文、独立穿戴物拆分、外观推龄比较基线和手持物排除：

1. **年龄**：当前/呈现年龄必须同时输出 `physical_identity` fact 和 `age` signal；signal 的 `fact_index` 精确指向年龄 fact。叙述者直接给出的精确值、近似区间或相对年龄均用 `asserted`；只有“似乎/可能”等显式认知不确定用 `uncertain`；从外观推断年龄用 `inferred`。
2. **presentation**：换衣、穿脱、整理发型/妆容、伪装等外在呈现改变用 `presentation`。引文必须是改变动作；若结果外观没有说清，signal 的 `fact_index` 为 `null`，不能虚构 fact。身体/物种变化仍用 `transformation`，普通背景时间和地点不是 `other_state`。
3. **unresolved**：先用姓名、泛称、代词或 unknown 建立 Chunk 局部 owner。只有“明确是视觉命题，但 owner、证据边界或局部视觉范围确实无法安全表达”才进入 unresolved。动作、关系、对话、情绪、地点、手持物和情节直接省略，不能把 unresolved 当垃圾桶。

4. **机械字段下沉**：版本、Chunk 对应关系、局部 ID、重复名称/标签和引用字符串全部由代码生成；模型只判断原文语义和数组间关系。
5. **变化类别**：`transformation/presentation` 只能用于 `signal_kind`；变化后的鳞片、利爪、肢体、身份或服装 fact 仍分别使用 `body/physical_identity/clothing` 等 `coarse_family`。

年龄、presentation、unresolved、owner 和事实类别仍由模型做开放语义判断；确定性代码只负责 Schema、索引、ID 物化、原文引文和评分对齐，不用关键词规则替代语义。

## 2. 模型输入与内部来源信封

模型业务输入只有一个字段：

| 字段 | 含义 | 为什么需要 |
|---|---|---|
| `chunk_text` | 当前待发现的完整文本 | 所有人物提及、事实、信号和引文只能由它证明 |

传输层还提供严格输出 JSON Schema，但它不是小说业务数据。服务内部仍保存 `schema_version`、`chunk_id`、`previous_tail`、`allowed_coarse_families`，它们用于来源追踪和代码契约，不进入模型上下文：`chunk_id` 和版本由代码绑定；分类枚举已经在 Prompt/Schema 中；M1 不做跨 Chunk 身份，发送 `previous_tail` 反而会增加把前文事实复制进当前 Chunk 的风险。

## 3. 模型线输出字段

### 3.1 顶层

| 字段 | 含义 | 判定方式 |
|---|---|---|
| `entities` | 本 Chunk 中为 fact 或 signal 提供 owner 的局部人物 | 只在本响应内有效，不代表跨 Chunk 已合并身份 |
| `facts` | 原文支持、尚未映射 canonical field 的视觉命题 | 逐项校验 owner、引文、粗类别、认知状态 |
| `temporal_signals` | 年龄、人生阶段、时间跳转、呈现改变、变形等显式信号 | 逐项校验类型、owner、fact 绑定和引文 |
| `unresolved_items` | 确属视觉内容但当前契约无法安全表示的少数项目 | 默认额外输出一项就算误报 |

### 3.2 `entities[]`

| 字段 | 含义 | 例子/约束 |
|---|---|---|
| `mention_quote` | 能在当前原文中定位人物的连续原文 | 如“萧炎”“这位少女”“他” |
| `mention_kind` | 表面提及类型 | `explicit_name` 姓名；`descriptor` 少年/老者/少女等泛称；`pronoun` 代词；`unknown` 仍无法归类的原文提及 |

实体在数组中的位置就是零基 `owner_index`。例如第一个实体用 `owner_index=0`。代码随后生成 `local_entity_id=e1`，并把 `representative_name` 设为 `mention_quote`。

### 3.3 `facts[]`

| 字段 | 含义 | 例子/约束 |
|---|---|---|
| `owner_index` | 此事实属于哪个局部人物 | 必须是 `entities` 中存在的零基位置 |
| `evidence_quote` | 最小但语义完整、且适合下游唯一定位的连续原文 | 必须逐字存在于 `chunk_text`；不得裁掉否定、推断、年龄或变化关系 |
| `raw_proposition` | 对原文视觉命题的简洁同语种表达 | 可自然改写，但不能增加原文没有的信息 |
| `coarse_family` | 粗粒度视觉类别 | 如 `physical_identity`、`hair`、`face`、`body`、`clothing`、`worn_accessory`；精细字段留给 M2 |
| `epistemic_status` | 原文如何支持该命题 | `asserted` 直接陈述（含直接近似值/区间）；`negated` 明确不存在；`uncertain` 原文明示似乎/可能；`inferred` 原文明示由外观推断 |

代码按数组顺序生成 `local_fact_id=f1/f2...`，并把 `owner_index=0` 转成内部 `entity_ref=e1`。

### 3.4 `temporal_signals[]`

| 字段 | 含义 | 例子/约束 |
|---|---|---|
| `owner_index` | 没有直接 fact 时，信号明确属于谁 | 能确定时引用 entity 数组位置；有 `fact_index` 时必须省略/为 `null` |
| `fact_index` | 信号直接限定的具体 fact | 填 facts 零基位置；年龄必须指年龄 fact；只说“换了一身衣衫”而没说换成什么时为 `null` |
| `evidence_quote` | 证明信号的连续原文 | presentation 应引用“换了一身衣衫”，不是“走出房间” |
| `signal_kind` | 信号类别 | `age`、`life_phase`、`time_jump`、`presentation`、`transformation`、`other_state` |

Prompt 要求 `owner_index` 与 `fact_index` 不同时填写。若模型仍同时返回，代码只在二者 owner 一致时接受，并以 fact 为准；不一致则拒绝。若 `fact_index` 缺失，但 signal 引文只被同 owner 的唯一一个 fact 引文包含，代码确定性补齐该绑定；零个或多个候选时保持未绑定。代码再生成内部 `local_signal_id`、`entity_ref`、`fact_ref`，并令 `raw_label=evidence_quote`。

### 3.5 `unresolved_items[]`

| 字段 | 含义 | 例子/约束 |
|---|---|---|
| `owner_index` | 若仍能确定局部 owner，则填实体数组位置 | canonical 人物不知道不代表这里必须为 `null` |
| `evidence_quote` | 确实存在的视觉疑难原文 | 必须逐字来自当前 Chunk |
| `raw_proposition` | 未能安全形成 fact 的视觉命题 | 不能放动作、关系、对白、手持物等非外观内容 |
| `reason_code` | 无法安全表示的原因 | `ambiguous_owner`、`ambiguous_evidence`、`ambiguous_local_scope`、`unsupported_visual_content` |

代码生成内部 `local_item_id` 和 `entity_ref`。

### 3.6 哪些字段明确不让模型输出

| 字段 | 代码处理方式 | 删除原因 |
|---|---|---|
| `schema_version`、`chunk_id` | 从当前调用请求注入 | 模型复述不能提供新语义，只会增加串错风险 |
| `local_entity_id/local_fact_id/local_signal_id/local_item_id` | 按数组顺序生成 `e1/f1/t1/u1...` | 完全确定，无需模型生成 |
| `representative_name` | 复制 `mention_quote` | 当前 M1 没有独立规范化职责 |
| `raw_label` | 复制 signal 的 `evidence_quote` | 当前字段没有独立信息量 |
| `entity_ref`、`fact_ref` | 由 `owner_index`、`fact_index` 物化；唯一引文包含时可补 `fact_ref` | 避免模型同时维护 ID 和重复引用 |

## 4. 测试集的期望字段怎样对应输出

测试文件中的 `expected` 不是模型输出，而是人工金标：

| 测试字段 | 对应模型输出 | 怎样匹配 |
|---|---|---|
| `entities` | `entities[]` | `mention_quote` 或 `representative_name` 命中允许称呼；同一金标 owner 可列出 Chunk 内不同表面词及其 alias mention kinds，不跨 Chunk 合并 |
| `required_facts` | `facts[]` | owner、允许引文、`coarse_family` 必须匹配；唯一的逐字较长引文可包含较短金标；缺一项就是 fail |
| `allowed_facts` | `facts[]` | 输出了就按正确 fact 评分，没输出不扣召回 |
| `forbidden_facts` | `facts[]` | 命中禁用语义载体/类别就是 fail，例如把手持刀矛当人物外观 |
| `proposition_concept_groups` | `raw_proposition` | 每组至少出现一个等价表达；未覆盖的新说法进入人工 review，不直接判语义错误 |
| `epistemic_status` | `facts[].epistemic_status` | 必须精确一致 |
| `temporal_signals` | `temporal_signals[]` | `signal_kind`、owner、`fact_ref` 对应的金标 fact、允许引文全部一致 |
| `unresolved_items` | `unresolved_items[]` | reason、owner 和允许引文全部一致；默认额外项视为误报 |
| `allow_additional_facts` | 真实长 Chunk 的额外 fact | `true` 时，未人工穷举但通过契约的额外 fact 记为 `unscored`，既不加分也不扣 precision |
| `allow_additional_temporal_signals` | 额外 signal | 当前六条均为 `false`，因为三类修复要求 signal 穷举评分 |
| `allow_additional_unresolved_items` | 额外 unresolved | 当前六条均为 `false`，专门测 unresolved 误报 |

评分顺序是：先做服务端契约与原文引文校验，再匹配人工金标。核心指标含义：

- `required_fact_recall = 命中的 required facts / required facts 总数`；
- `supported_fact_precision = 命中的 required/allowed facts / 参与评分的实际 facts`；真实长 Chunk 中允许的 `unscored` facts 不进入分母；
- `temporal_signal_recall/precision` 同时要求类别、owner、fact 绑定和引文正确；
- `unresolved_item_recall/precision` 同时要求原因、owner 和引文正确；期望正例为零时，数值 1.0 只能表示“没有误报”，不能解释为已验证正例召回；
- `quote_fidelity` 检查所有人物和证据引文是否逐字来自当前 Chunk；
- `epistemic_accuracy` 检查 asserted/negated/uncertain/inferred 是否保持。

## 5. 两组数据分别负责什么

### 已批准回归集

[`m1_local_observation_discovery_v1.json`](../tests/evaluation/m1_local_observation_discovery_v1.json) 共 15 条短 case，版本为 `m1-local-observation-v1.2`、状态为 `approved`。它用于防止修复年龄、presentation 和 unresolved 时破坏此前已经正确的能力。

三类修复的直接对应关系：

| 问题 | 回归 case | 通过条件 |
|---|---|---|
| 年龄 | `m1-inferred-age-006`、`m1-explicit-age-007` | age fact 不漏；age signal 指向该年龄 fact，不指白发或体型 |
| presentation | `m1-presentation-change-015` | 输出 presentation，引用换装动作，并绑定换装结果 fact |
| unresolved | `009`–`014` 中的空结果、手持物、情绪、局部 owner、前文边界和不可信指令 | 非视觉内容不进入 unresolved；可用 descriptor 表示的 owner 不 defer |

### 已批准真实 Chunk 集

[`m1_local_observation_real_v1.json`](../tests/evaluation/m1_local_observation_real_v1.json) 共 6 条，全部由当前分块器以 `target_tokens=1000` 从 `tests/测试` 生成，并保存源文件、chunk 序号、chapter 序号和文本 SHA-256。测试会重新分块并逐字校验输入，避免手工截取或改写小说片段。

| Case | 来源 | 主要人工金标 |
|---|---|---|
| `m1-real-presentation-no-result-001` | 《斗破苍穹》chunk 9 | 萧炎稚嫩脸庞；“换了一身衣衫”是 presentation，因结果未知所以 `fact_ref=null` |
| `m1-real-two-approximate-ages-002` | 《斗破苍穹》chunk 10 | 男子二十左右、少女与萧炎年龄相仿均为 asserted age fact + 正确绑定；人物 owner 不串线 |
| `m1-real-inferred-age-003` | 《斗罗大陆》chunk 4 | 唐昊显得比同龄父亲苍老、像祖父是 inferred age；泛指父亲三十岁不能归给唐昊 |
| `m1-real-relative-age-and-accessories-004` | 《牧神纪》chunk 54 | 女孩十一二岁为 asserted；三根辫子、脚踝金环、虎牙；脱掉铁鞋是 presentation；对白中的“牛变女人”不是当前视觉 transformation |
| `m1-real-transformation-not-presentation-005` | 《牧神纪》chunk 55 | 怪物化和恢复女孩模样是两次 transformation；“衣衫半解”不是一次独立 presentation 动作 |
| `m1-real-classic-apparel-no-held-items-006` | 《水浒传》chunk 19 | 史进、陈达古典服饰可抽取；弓箭、刀矛、坐骑和战斗动作不属于外观，也不进入 unresolved |

## 6. 当前限制与审核 Gate

这六条真实原文能强测 unresolved **误报**，但没有发现一个“明确视觉命题且在 M1 契约中确实无法安全表示”的可靠正例。因此本轮可以判断 unresolved precision 是否改善，不能宣称 unresolved 正例 recall 已验证。不能为了让指标完整而人工把可表示内容标成 unresolved。

用户已确认安全扩展引文、Chunk 内 owner 表面词、脱掉铁鞋 presentation 和直接近似年龄 asserted，真实数据集已经升为 `approved`。但该批准只冻结测量口径；Prompt v1.6 仍有一条独立 body fact 漏召回，且本真实集没有 unresolved 正例，因此 M1 质量 Gate 尚未通过。当前调用只用于离线验证，不产生 active 事实。

## 7. v1.6 真实质量结果

2026-08-28 使用 `deepseek-v4-flash` 与 Prompt v1.6 完成 6/6 条已批准真实 Chunk 调用，全部一次成功。最终 rubric v1.1 离线重评分为 **5 pass / 0 review / 1 fail**：required fact recall 95.65%，scored fact precision、quote fidelity、epistemic accuracy、temporal recall/precision 和 unresolved precision 均为 100%。

逐 case 离线复核把差异分成两组：

| 类型 | 结果 | 当前处理 |
|---|---|---|
| 已修复 | 直接近似年龄 asserted、脱鞋 presentation、外观推龄、同 Chunk owner aliases、逐字引文、古典服饰拆分、武器/坐骑排除、静态“衣衫半解”不升 presentation | 5 条真实 case 通过 |
| v1 rubric 失败、v2 重新归类 | 模型把“男子二十左右、英俊、身材挺拔”合并成一个 `physical_identity` fact，但 quote/raw proposition 完整保留相关语义 | v1 保留历史分数；v2 将其作为合格 evidence candidate，拆分与分类转入 M2 |
| 未覆盖 | 真实集无可靠 unresolved 正例 | 只声明无误报，不声明正例召回已验证 |

诊断产物：

- 完整运行：`data/diagnostics/m1-local-observation/20260828-deepseek-v4-flash-prompt-v1.6-real4/run.json`
- 结构化输出：同目录 `outputs.json`
- Provider 原始评分报告：同目录 `report.json`
- 最终测量修正报告：同目录 `report-rubric-v1.1-final.json`
