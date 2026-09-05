# dev29 CharacterSnapshot 与有效期契约

2026-09-05，SNAPSHOT-APPLICABILITY-079。Runtime `0.1.0.dev29`，机器 Schema `3.29.0-draft1`。

## 交付范围

R04 已交付纯函数、CLI、机器 Schema、按位置解释和旧人物卡适配。R03 已交付衣着独立持续规则、有证据的事实关闭/连续性接口和边界测试；真实叙事场景识别、自动换装事件发现及人工质量评测继续实施。R02 的完整语义冲突生成仍未交付，现有双 active 冲突消费门槛保留。

`fact_applicability.py` 是唯一有效性计算入口；`character_snapshot.py` 复用原编译器的来源校验、StateSegment 选择、proposition、标签、冲突门槛和 provenance。`render_profile_compiler.py` 保留原公开导入路径，人物卡由 Snapshot 适配，不维护第二套持续规则。旧 raw facts、Registry、StateSegment observation bindings 均不被改写。

## 查询与结果

Python 入口 `build_character_snapshot` 接收原文、fact_groups、appearance_states、label_projection、run_id、character_id、document_position；可选 life_stage/form_state/scene_state、applicability_events 和 explain。

查询坐标是未经换行归一化原文的 Unicode code point，采用半开边界；`0 <= document_position < processed_source_end`。缺少位置或选择器无匹配时不返回混合 traits；越界、布尔位置、未知人物、来源版本/hash/引用不一致失败关闭。目前仅接受完整文档覆盖，不把局部覆盖伪装成完整快照。

响应包括：

- `snapshot_id` 绑定 run、精确输入产物集合、策略和查询；`artifact_set_id` 由实际输入内容派生。explain 只展开同一快照，不改变 ID。
- `source_document_version_id`、`document_hash`、`run_id`、`offset_unit` 和当前身份状态；首版使用 run-scoped character_id，subject_id 留给 R08。
- `selected_state_segment_id`、状态、`active_traits`、`provisional_traits`、原始事实 provenance、warnings、conflicts 和 review_refs。
- `applicability` 包含事实 ID、观察 span、半开有效区间、状态、原因和依据事件 ID；未知终点为 null，不表示“永远有效”。区间受 life、form 和明确关闭限制。
- `explain=True` 追加 excluded_facts，提供 future_observation、different_life/form、removed、replaced、expired_momentary、选择器失败等原因及原始来源引用。

结果中的 persistence 保留原 assignment 分类，旧来源中的衣着可能仍标为 scene；当前有效性以 status、reason 和 valid_interval 为准。旧卡的 scene_overrides 分组也为结构兼容保留，不能据此在 UI 再执行一套场景过期规则。

run_id 是调用方声明的运行命名空间；当前内容指纹和跨层验证保证精确输入绑定，不等价于 R09 尚未实现的原子发布 manifest、存储权限或 run 成员校验。未决身份审阅以 review_refs/warnings 暴露，不按人物名字猜测映射。

## 有效期规则

| 情况 | dev29 行为 |
|---|---|
| 原文正在观察该事实 | active；未来 observation 不进入当前卡 |
| 衣着/配饰跨段、跨章、换地点或暂时离场 | 不跟随 scene ID 删除；没有连续性证据时 provisional |
| 已裁决连续性证据 | 只在该证据 span 的半开区间内 active，离开区间恢复暂定 |
| 明确脱下/替换 | 在事件 evidence.end 关闭指明的事实，旧事实不重新激活 |
| 新衣服、外套或佩饰 observation | 不自动覆盖其他同 attribute 事实；原有内衬、其他部位/层次继续独立判断 |
| 表情等 momentary | 仅 observation span 内 active，之后 excluded/expired_momentary |
| 有证据的时间跳跃/连续性中断 | 指明事实降为 provisional；不把不确定性解释成脱衣 |
| life 改变 | 关闭旧生命阶段事实，即使后来出现相同状态文字也不恢复 |
| form 改变 | 不将原形事实直接迁入变身形态 |
| form 退出 | 同生命阶段、基础 form 相同且未被关闭的衣着可以暂定恢复；有效区间不穿过中间变身段 |
| 同位置关闭与连续性同时发生 | 关闭优先，输入顺序不影响结果；完全重复事件按内容 ID 去重 |

已保存的 appearance transition 仅在 before 精确等于事实 value、attribute 相同、目标观察在事件之前且匹配唯一时关闭事实；语义或部位不明确时不做全属性覆盖。明确关闭可以发生在暂时变身期间，因此退出形态不会把已脱下的衣服补回来。

## 事件输入：代码侧证据契约

`fact-applicability-events-v1` 包含 source_document_version_id、原文 document_hash 和 events。每个事件严格包含：

```json
{
  "character_id": "指定人物的代码 ID",
  "kind": "remove",
  "fact_ids": ["被关闭的 canonical_fact_id"],
  "evidence": "连续的逐字原文",
  "document_span": {"start": 100, "end": 110}
}
```

kind 为 continuity、uncertain_gap、remove、replace。fact_ids 必须存在、同人物、无重复且观察结束不晚于证据开始。replacement 事件只关闭指定旧事实；新装束必须有独立 grounded observation，不由事件凭空制造。

接口消费调用方已经完成语义裁决并绑定事实的结果；代码验证逐字 span、来源版本、引用归属和顺序，不能仅凭逐字回放证明事件语义正确。本轮没有让模型读取或输出内部 ID/span，也没有增加自动识别节点。事件 ID 由代码派生；独立文件可承载人工审核结果或未来受约束语义节点的代码回填结果。

原有 narrative scene 的行/章边界 baseline 尚未替换成真实场景识别。dev29 通过将衣着从该规则分离修复错误失效，不宣称 R03 的全部语义能力完成。

## CLI 与兼容

安装开发环境后，可查询本轮生成的斗罗状态：

```powershell
python -m novel_character_generator build-character-snapshot --input-file 'tests/小说/斗罗大陆前20章.txt' --fact-groups-file 'runs/douluo-20ch-e2e-dev13-20260831/post-link-fact-groups-dev18/document-character-fact-groups.json' --appearance-states-file 'runs/douluo-20ch-e2e-dev13-20260831/snapshots-dev29/document-character-appearance-states.json' --label-projection-file 'runs/douluo-20ch-e2e-dev13-20260831/label-review-projection-dev25/document-character-label-review-projection.json' --run-id 'douluo-snapshot-dev29' --character-id 'char-f47075b7019563fd8315' --document-position 300 --explain --output-file 'runs/douluo-20ch-e2e-dev13-20260831/snapshots-dev29/query-300.json'
```

`--applicability-events-file` 可选；原 `build-render-ready-character-profiles` 命令也接受该参数。查询不调用 Provider，Snapshot CLI 拒绝以原文或依赖文件作为输出。

旧人物卡字段结构和 API/CLI 保留，compiler/applicability policy 更新为 snapshot-render-adapter-v2 / evidence-interval-applicability-v2。历史 dev26 卡可用机器 Schema 中 LegacyRenderReadyCharacterProfilesV1 查看和验证；新结果用当前 Schema。原有 relation v1 状态在新查询前需确定性重建为当前关系策略，不能静默接受过期派生层。

## 验收

237 tests、19 subtests 通过。新增 26 个测试覆盖跨段/章、地点、叠穿、局部移除、替换、新 observation、离场、时间跳跃、瞬时状态、life/form、同位置顺序、事件去重、未来观察、来源失配、CLI、Schema、ID 失效和旧 API 适配。

斗罗原有事实基线独立生成 4 张 Snapshot：7 active、42 provisional、71 excluded bindings。新旧 Schema、重复构建确定性和 6 个源文件哈希不变均已验证，新增 Provider 0。此次使用原 dev18 fact groups，并只升级保存状态的确定性关系层，未宣称 dev27 M2 修复已重新贯穿身份及所有下游。

产物：`runs/douluo-20ch-e2e-dev13-20260831/snapshots-dev29/`。可运行 `.project-to-act/tasks/SNAPSHOT-APPLICABILITY-079/verify_real.py` 重验；已存在产物只比较，不覆盖。

更新（dev30）：自动场景/换装事件识别及语义不兼容到 Snapshot 真实冲突的工程链路已交付，真实模型质量待评测。执行命令、预算与验收见 [自动事件与冲突闭环](41-automatic-events-and-conflicts.md)。
