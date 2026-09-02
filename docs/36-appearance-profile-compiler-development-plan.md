# 外貌状态层与 Profile Compiler 后续开发计划

## 1. 结论

当前 `document-character-evidence.json`、`document-character-registry.json` 和 `document-character-profiles.json` 继续作为 Evidence Layer。它们负责保存可回放事实、人物身份结果和失败历史，不承担最终人物卡编译职责。

下一阶段在它们之后新增可重放的 Profile Compiler 链路：先关闭有逐字原文支持的局部身份链，再按最终人物归属建立 canonical facts，随后建立时间/形态/场景作用域，最后按明确选择器编译 render-ready profile。任何中间层都不得覆盖或删除 raw evidence。

## 2. 不可破坏的约束

1. `document-character-evidence-v1` 的 raw facts 永久保留；派生层只保存反向引用。
2. 只有显式命名、同位或连续局部共指原文可以新增 same edge。`proper name + global unique` 只能用于审计或候选召回，不能建立身份关系。
3. `fact_hash` 仍表示 raw evidence fact；canonical fact 使用独立 ID，并保留全部 `source_fact_hashes` 与 `source_occurrences`。
4. 去重必须保留 `category`、`attribute` 和作用域。不同合法属性即使来自同一 span 也不得因位置相同而删除。
5. `true_conflict` 只能在同一人物、同一作用域、同一规范属性且有效期重叠时成立。时间变化、形态变化和语义包含不能直接标成冲突。
6. render-ready 编译必须显式选择 `life_stage`、`form_state` 和需要时的 `scene_state`。选择器不足时输出多个候选 variant 或失败关闭，不静默混合。
7. 新模型阶段若确有必要，仍拆分代码信封、最小模型输入、最小模型输出和代码验证；模型不得读写内部 ID、hash、span、cache key 或 trace。
8. 历史 review 不删除。最终人物簇已消解的问题进入 `audit_only/resolved` 视图；只有仍需用户决策的项目进入 actionable queue。

## 3. 目标数据流

```text
document-character-evidence-v1
              +
document-character-registry-v1
              |
              v
local identity closure decisions
              |
              v
document-character-profiles-v1（raw evidence view，保持兼容）
              |
              v
document-character-fact-groups-v1
  - post-link structural dedup
  - source_fact_hashes / source_occurrences 全保留
              |
              v
document-character-appearance-states-v1
  - life_stage / form_state / scene_state
  - persistence / transitions
  - scope 内语义关系与冲突分类
  - corrected labels / actionable review projection
              |
              v
render-ready-character-profiles-v1
  - 按时期、形态、场景选择
  - 结构化人物卡
  - 到 canonical fact 和 raw evidence 的双向引用
```

## 4. 中间 Schema

### 4.1 `document-character-fact-groups-v1`

第一遍只做 post-link 结构去重，不做语义猜测。建议最小字段：

```json
{
  "canonical_fact_id": "cfact-...",
  "character_id": "char-...",
  "category": "face",
  "attribute": "眉眼",
  "value": "剑眉星目",
  "document_fact_span": {"start": 13152, "end": 13156},
  "source_fact_hashes": ["..."],
  "source_occurrences": [],
  "grouping_reason": "same_character_span_category_attribute_value",
  "scope_assignment_status": "unassigned"
}
```

结构分组键为：

```text
character_id
+ document_fact_span
+ category
+ attribute
+ value
```

这一层不合并 `眉眼` 与 `眉毛和眼睛`，也不合并不同 span 的同义事实。它解决身份归并后由多个 local/promoted mention 重复物化同一事实的问题。

### 4.2 `document-character-appearance-states-v1`

状态层是 Profile Compiler 的核心输入。每个人物至少包含：

```json
{
  "scope_id": "scope-...",
  "character_id": "char-...",
  "sequence_index": 0,
  "chapter_ref": {"chapter_id": "chapter-1", "source_span": {"start": 0, "end": 0}},
  "life_stage": {"key": "reincarnated-child", "status": "grounded"},
  "form_state": {"key": "base", "status": "default"},
  "scene_state": {"key": "scene-...", "status": "grounded"},
  "fact_bindings": [
    {
      "canonical_fact_id": "cfact-...",
      "persistence": "persistent_until_changed"
    }
  ]
}
```

`persistence` 最小枚举：

- `stable_trait`
- `persistent_until_changed`
- `scene_bound`
- `momentary`
- `unknown`

关系记录独立于事实值：

```json
{
  "transition_id": "transition-...",
  "character_id": "char-...",
  "dimension": "attribute",
  "transition_type": "changes_from_to",
  "from_value": "黑色",
  "to_value": "灰色",
  "from_scope_id": "scope-...",
  "to_scope_id": "scope-...",
  "source_fact_hashes": ["..."],
  "source_evidence_spans": [{"start": 0, "end": 0}]
}
```

状态内第二遍语义归一必须包含 `scope_id`。关系枚举为：

- `equivalent`
- `compatible`
- `temporal_change`
- `state_change`
- `true_conflict`
- `unclassified`

第一版允许保守输出 `unclassified`，不得为了降低 review 数量强制归类。

### 4.3 `render-ready-character-profiles-v1`

编译器输入必须包含人物和状态选择器：

```json
{
  "character_id": "char-...",
  "selector": {
    "life_stage": "reincarnated-child",
    "form_state": "base",
    "scene_state": null,
    "document_position": 15000
  }
}
```

输出保持结构化，不在第一版直接生成自然语言 Prompt：

- `identity_labels`：区分 proper name、alias、title 和 contextual description；
- `stable_traits`：当前时期/形态持续有效的外貌；
- `variant_traits`：时期或形态专属事实；
- `scene_overrides`：衣着、表情、临时身体状态；
- `transitions`：与当前选择相关的变化关系；
- `unresolved_conflicts`：仅保留该作用域内的真正冲突；
- `provenance`：`canonical_fact_id -> source_fact_hash -> source span/occurrence`；
- `compile_warnings`：选择器不足、状态未知或仍有未分类关系。

自然语言人物总结、图像提示词、多视角母版和视觉验收在结构化编译器稳定后另立阶段。

## 5. 开发切片与验收

### 067：路线与 Schema 规划

冻结本文的层次、边界、产物和任务顺序；不修改运行时代码，不宣称任何新质量 Gate 通过。

### 068：局部确定性身份闭合

实现 `explicit_apposition / demonstrative_naming / continuous_local_coreference` 三类 grounded edge，并复用现有 union/cannot-link 约束。

验收样例：

- `高大的身影 -> 中年男子 -> 这就是唐昊` 形成可回放的 same 链；
- `高大的身影` 不再是 singleton，129 条 raw facts 不丢失；
- 不增加 `global unique name` 自动 join；
- 无关系原文的“看门的青年”继续未决；
- Provider 调用为 0，相关反例证明同名不同人不会因此合并。

### 069：Post-link canonical fact groups

新增独立构建器、Schema、CLI 和失败关闭验证。输入只接受同文档 registry/profile，输出结构 fact groups。

验收样例：

- 当前 129 facts 可重放；结构重复合并后数量可解释；
- 老杰克、素云涛的重复来源进入 `source_fact_hashes/source_occurrences`；
- 同 span 不同 `attribute` 的合法事实均保留；
- raw evidence/profile 不被改写。

### 070：Appearance Scope / Variant Schema

先实现章节位置、事实顺序、作用域 ID 和状态选择器；场景边界不确定时允许显式 `unknown`，不猜测。

验收样例：

- 唐三前世 29 岁与转生后 5～6 岁进入不同 `life_stage`；
- 素云涛普通形态与独狼附体进入不同 `form_state`；
- 衣着与表情不升级为永久外貌；
- 所有 scope/fact/transition 都可反向引用 raw evidence。

### 071：状态物化与 transition 恢复

从 `source_evidence_quote` 恢复显式变化关系，建立 `persistence` 和有序 transition；不要求立即重跑 M1/M2。

验收样例：

- “原本黑色 -> 变灰”保存为关系而不是两个无关联值；
- 没有显式变化原文时不生成 transition；
- 重叠 Chunk occurrence 不生成重复 transition。

### 072：状态内语义归一与冲突分类

先实现确定性规则：完全相同、明确包含、显式时间变化和显式形态变化。剩余项保守标 `unclassified`。只有在人工集证明规则不足后才增加最小模型分类节点。

验收样例：

- `高大/高大魁梧`、`矍铄/精神矍铄` 不成为 true conflict；
- `紧张/失望` 作为兼容或时间变化处理；
- 同 scope 同属性且不可兼容的值仍为 true conflict。

### 073：Label 与 Review 投影

将 mention 的 `exact/describe` 与人物标签语义解耦。建议使用正交字段 `label_kind` 与 `label_stability`，使“大师”得到 `title + stable`，而不是 `name`。

review 同时输出两个视图：

- `audit_items`：完整保存历史 review 和处理依据；
- `actionable_review_items`：只保留最终图仍未解决且需要人工选择的问题。

验收样例：8 个已被最终人物簇消解的 `partial_identity_evidence_grounding` 降为 `resolved/audit_only`；“看门的青年”仍为 actionable。

### 074：Render-ready Profile Compiler

实现按 `character_id + state selector` 的确定性编译器。选择器不足时不混合唐三两个生命阶段或素云涛两个形态。

验收样例：

- 唐三儿童基础形态、唐三前世、素云涛普通形态、素云涛独狼附体分别生成独立结构化卡；
- 输出不含无证据性格、性别、服装补全或视觉风格推断；
- 每个输出字段都能回溯到 canonical fact 和 raw evidence；
- 编译结果稳定、可缓存、相同输入重跑字节级一致。

### 075：上游人工质量评测与 Stage 6 Gate

评测建设与 068～074 并行准备，但必须在 Stage 6 前完成。首轮先冻结标注规范、样本拆分、双人裁决方法和 evaluator，再根据 baseline 与业务风险由用户确认正式阈值；在此之前不使用 9.5/10 或 8.5/10 作为 Gate。

评测至少分别报告：

- M1 mention/evidence precision、recall 和逐字 Grounding 率；
- M2 fact extraction precision、attribute/value 正确率和人物归属正确率；
- promotion 人物建立、事实保留、歧义隔离正确率；
- identity false merge/false split；
- scope、transition、语义关系和 render profile 的逐字段准确率；
- 按作品、章节、人物和错误类型分层的 error list。

## 6. 实施顺序

推荐主线：

```text
068 local coreference closure
  -> 069 structural fact groups
  -> 070 scope schema
  -> 071 state/transition materialization
  -> 072 semantic relations/conflicts
  -> 073 label/review projection
  -> 074 render-ready compiler
```

075 的标注规范和 evaluator 在 069 后即可开始；正式 Gate 在 074 纵向切片完成后执行。Stage 5 在上述切片完成并有新鲜证据前保持 `in_progress`，Stage 6 不提前进入。

## 7. 风险与决策点

1. 当前 `character_id` 受身份策略版本和 anchor 影响。068 合并更早出现的“高大的身影”后可能改变唐昊 ID。进入外部视觉资产关联前，需要决定是接受版本化 ID 迁移，还是新增与解析策略解耦的稳定 subject ID。
2. 章节标题可确定性定位，场景边界未必可靠。070 应允许 `scene_state=unknown`，不得用不稳定切场阻塞 life/form state。
3. 语义归一最容易把“包含”误当“等价”。072 必须保留原值、关系方向和置信来源，不能只保存一个覆盖后的字符串。
4. 旧 review 是审计证据。073 只能改变面向用户的可操作状态，不能删除历史 issue。
5. 首版 render-ready profile 是结构化编译结果，不等于图像 Prompt，也不等于视觉一致性已验收。
