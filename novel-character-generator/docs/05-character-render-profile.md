# 角色渲染档案

> [← 上一篇](04-text-understanding-pipeline.md) · [文档索引](README.md) · [下一篇 →](06-image-generation-and-drift-control.md)
>
> 文档版本：4.0 · 源章节：8. 角色渲染档案 · 修订日期：2026-08-26
>
> 当前状态：真实 Observation 已能自动形成 AppearanceState、Conflict 和待审核 RenderProfile；冲突编辑/批准、父子时间线继承、人工确认值保护和 Snapshot 已实现核心，Mock 图像链路已部分实现。本文新增的设计缺口、来源分类、出图就绪度、`SceneRenderBrief` 和 `ImageRenderSpec` 是目标契约，尚未完整落地。

## 8. 角色渲染档案

### 8.1 档案在出图链路中的职责

```text
FeatureObservation（有证据的小说事实）
  → CharacterAppearanceState（按阶段和持续性聚合的事实）
  → ResolvedAppearanceFacts（指定时间点成立的事实视图）
  → CharacterRenderProfile（事实状态 + 已批准的可复用角色设计）
  → ResolvedCharacterSnapshot（指定时间点的已批准角色快照）
  → SceneRenderBrief（这张图的表演、环境、美术和镜头）
  → ImageRenderSpec（可提交给 Provider Adapter 的编译结果）
```

`CharacterRenderProfile` 不是 Observation 的漂亮 JSON，也不是最终 Prompt。它保存已批准、可跨多张图复用的角色设计：稳定身份锚点、可用人生阶段、阶段基础外观、默认造型、设计缺口决策和参考资产。姿势、一次性表情、环境、镜头和画风通常不属于角色档案。

Profile 中每个可生成字段必须保留来源：

```text
novel_asserted
human_decision
approved_suggestion
reference_asset
```

`novel_inferred` 只能作为待审核建议；`workflow_default` 只能进入 `SceneRenderBrief` 或 `ImageRenderSpec`。身份原型只提供建议，默认优先补充服装、道具和时代风格。对于脸型、肤色、体型等个体差异大的特征，不应仅凭职业或身份自动写入确定值。

角色档案字段决策顺序为：用户已确认值 > 有明确原文证据的有效观察 > 用户批准的建议。这里的“顺序”只用于解决同一角色设计字段，不允许低层来源覆盖高层来源，也不允许用画风默认值填充事实快照。

### 8.2 冲突处理

两条观察只有同时满足以下条件，才进入“真实冲突”候选：

```text
same_character
AND same_field
AND same_effective_timeline_domain_at_target_event
AND temporal_scopes_overlap
AND compatible_reality_status
AND values_are_incompatible
```

冲突不采用简单“新值覆盖旧值”，按以下类别处理：

- 时间变化：少年黑发、老年白发，分别进入不同 `CharacterAppearanceState`，不冲突；
- 场景变化：换装、临时伤势和一次性神情默认不冲突；
- 分支变化：平行时间线中的不同状态分别保存，不互相覆盖；
- 伪装/梦境/传闻：保留但不进入 canonical 默认状态；
- 细化描述：更具体值可替代宽泛值，但保留来源链；
- 持久转变：新增疤痕、伤愈、染发等以事件为边界结束旧状态并开始新状态；
- 真矛盾：同一场景、同一现实层级中“蓝眼睛”和“黑眼睛”等不兼容值标记 `needs_review`；
- 用户选择：形成新档案版本并记录审核人。

“后文没有再提到疤痕”不等于疤痕消失。持久字段延续到明确终止事件；瞬时神情则不得跨场景延续。解析器应维护字段级持续性策略，而不是对所有字段使用同一过期规则。

冲突检测中的“有效时间线域”必须先解析继承关系：子时间线在 `branch_event_id` 以前继承父时间线状态，因此父子 timeline ID 不同并不自动意味着不冲突；只有分支事件以后才独立判断。梦境、传闻等 `reality_status` 使用版本化兼容矩阵，禁止把现实层级兼容性留成未定义布尔判断。

| 描述组合 | 是否冲突 | 处理 |
|---|---|---|
| 前世长发；转生幼年短发 | 否 | 同一 canonical 历程中的两个 `life_phase_key` 阶段 |
| 少年黑发；老年白发 | 否 | 两个阶段外观状态 |
| 主线无伤；梦中胸口有伤 | 否 | 不同现实层级 |
| 分支事件后主时间线蓝衣；分支时间线黑衣 | 否 | 分别绑定时间线 |
| 同一场景先微笑、后皱眉 | 否 | 按场景内顺序保存两个瞬时状态 |
| 内心狂喜；表面不动声色 | 否 | 内外情绪分字段 |
| 同一角色同一场景被明确写为蓝眼和黑眼 | 是 | 标记审核，不自动覆盖 |
| 角色甲黑发；角色乙白发 | 否 | `character_id` 不同 |

### 8.3 目标时点快照解析

图像生成不得只传 `character_id`，必须给出目标语境：

```python
class CharacterRenderRequest(BaseModel):
    character_id: UUID
    timeline_id: UUID
    target_event_id: UUID | None
    target_scene_id: UUID | None
    target_chapter_ordinal: int | None
    expression_override: ExpressionRenderOverride | None
    render_overrides: dict[str, JsonValue]


class ExpressionRenderOverride(BaseModel):
    outward_emotion: str | None
    visible_cues: list[str]
    intensity: float | None
    reason: str
```

角色快照解析顺序为：本次明确且已记录来源的角色覆盖 > 目标场景瞬时人物状态 > 目标时点有效的已批准阶段外观/设计 > 稳定身份锚点。它可以包含经批准的设计决定，但画风、镜头、设计性灯光和 Provider 默认值不得进入 `ResolvedCharacterSnapshot`。若目标时间缺失且角色存在多个已批准阶段，API 返回 `ambiguous_appearance_state`，由用户选择，不擅自使用最新章节状态。

`render_overrides` 只影响本次生成。它必须以 `human_decision` 进入冻结上下文，并明确是替换角色设计、场景指令还是美术指令；除非用户另行保存并批准，否则不回写 Observation、AppearanceState 或 Profile。

### 8.4 设计缺口和出图就绪度

小说没有写某个字段，不代表角色没有该特征，也不代表系统应该继续无限检索。Profile 草稿应保存结构化设计缺口：

```python
class CharacterDesignGap(BaseModel):
    field_path: str
    state: Literal["unknown", "not_stated", "conflicted"]
    importance: Literal["blocking", "recommended", "optional"]
    target_stage_key: str | None
    candidate_suggestion_ids: list[UUID]
    resolution_source: Literal["human_decision", "approved_suggestion"] | None
```

显式否定事实（例如原文明说“没有胡须”）是带证据的 `negated` Observation，不属于 `not_stated`。检索达到版本化预算仍无证据时才标记 `not_stated`；之后转入角色设计，而不是重复调用抽取模型。

出图资格使用独立报告，不复用文本分解的 `ready`：

```python
class RenderReadinessReport(BaseModel):
    concept_ready: bool
    character_design_ready: bool
    consistent_scene_ready: bool
    blocking_conflict_ids: list[UUID]
    blocking_design_gaps: list[CharacterDesignGap]
    missing_scene_fields: list[str]
    missing_reference_roles: list[str]
    policy_version: str
```

- `concept_ready`：允许产生带“探索候选”标记的概念图，不能成为阶段基准图；
- `character_design_ready`：关键身份、阶段基础外观和默认造型已批准，可生成角色设定图并选择基准图；
- `consistent_scene_ready`：本次场景简报、负向约束、工作流与所需参考资产已冻结，可进入一致性场景生成。

### 8.5 场景简报与渲染规格

`SceneRenderBrief` 描述一张图的意图，不改变角色事实：

```python
class FieldSourceRef(BaseModel):
    source_kind: Literal[
        "novel_asserted", "human_decision", "approved_suggestion",
        "workflow_default", "reference_asset"
    ]
    source_id: UUID | None
    evidence_ids: list[UUID]


class SceneRenderBrief(BaseModel):
    character_snapshot_hash: str
    target_scene_id: UUID | None
    pose: dict[str, JsonValue]
    action: str | None
    gaze: str | None
    visible_expression: dict[str, JsonValue] | None
    held_objects: list[str]
    environment: dict[str, JsonValue]
    art_direction: dict[str, JsonValue]
    composition: dict[str, JsonValue]
    source_map: dict[str, list[FieldSourceRef]]
    approval_status: Literal["draft", "approved"]
```

`ImageRenderSpec` 是 Provider 中立的编译产物：

```python
class ReferenceAssetBinding(BaseModel):
    artifact_id: UUID
    role: Literal["identity", "pose", "structure", "style"]
    weight: float | None


class ImageRenderSpec(BaseModel):
    identity_prompt_block: list[str]
    stage_prompt_block: list[str]
    outfit_prompt_block: list[str]
    performance_prompt_block: list[str]
    environment_prompt_block: list[str]
    art_direction_prompt_block: list[str]
    negative_constraints: list[str]
    reference_assets: list[ReferenceAssetBinding]
    output_parameters: dict[str, JsonValue]
    source_map: dict[str, list[FieldSourceRef]]
    compiler_version: str
    spec_hash: str
```

Prompt 文本只是这些块在某个模板版本下的序列化结果。不同 Provider 可以重排或翻译表达，但不能自行添加人物事实；Provider 特有节点、参数名和请求 JSON 只存在于 Adapter 层。

### 8.6 角色阶段形象集

一本小说中的主角通常存在少年、成年、受伤后、身份揭露、阵营变化或重要换装等可视差异。既然系统已保存这些 `CharacterAppearanceState`，一期不再把输出限制为一个形象，而是将已批准且差异足够大的状态组织为 `CharacterImageSet`。

阶段选择遵循以下规则：

- 一期每个主要角色默认生成 2–4 个关键阶段，数量上限由预算和 PoC 结果冻结；
- 阶段必须由一个或多个已批准的 `CharacterAppearanceState` 组合，并绑定明确时间线与事件范围；
- 少年期、成年期、长期伤势、长期伪装或身份转折可成为独立阶段；
- 同一阶段内的短暂表情、单次动作、一次性污渍和普通换装通常只作为场景状态，不自动新增阶段；
- 相邻状态若视觉差异不足，则合并展示，避免为每章或每次描述重复出图；
- 每个阶段独立解析 `ResolvedCharacterSnapshot`、生成候选图并锁定阶段基准图；
- 用户可从阶段基准图中指定一个 `default_representative_image_id`，但该默认图不覆盖其他历史形象；
- 后续新增章节出现新的重要阶段时，新建集合版本，只生成新增或受影响阶段，不重跑全部历史阶段。

```python
class CharacterImageSet(BaseModel):
    id: UUID
    character_id: UUID
    render_profile_version: int
    version: int
    default_representative_image_id: UUID | None
    stage_image_ids: list[UUID]
    selection_policy_version: str
    status: Literal["draft", "partially_approved", "approved"]


class CharacterStageImage(BaseModel):
    id: UUID
    image_set_id: UUID
    stage_key: str
    appearance_state_ids: list[UUID]
    resolved_snapshot_hash: str
    stage_label: str
    representative_event_id: UUID | None
    candidate_image_ids: list[UUID]
    baseline_image_id: UUID | None
    display_order: int
    selection_reason_codes: list[str]
```

**[PoC 决策项 POC-IMAGE-02]** 第 0 阶段必须比较“单一代表形象”和“2–4 个关键阶段形象集”两种产品输出，记录阶段覆盖率、重复形象率、人工选择耗时、单角色成本和用户对角色历程表达的评价。PoC 只决定默认阶段数、差异阈值和预算上限，不改变底层保存全部历史观察与阶段状态的原则。

### 8.7 身份原型

一期原型为只读、版本化、人工审核的 JSON 资源。原型字段必须带：

```json
{
  "value": "monk robe",
  "confidence": 0.7,
  "allowed_fields": ["clothing.style", "clothing.accessories"],
  "rationale": "visual convention, not textual fact"
}
```

二期实现在线编辑、LLM 生成、灰度发布与回滚。自动生成的原型必须先处于 `draft`，不能直接成为活跃版本。

---

[← 上一篇](04-text-understanding-pipeline.md) · [文档索引](README.md) · [下一篇 →](06-image-generation-and-drift-control.md)
