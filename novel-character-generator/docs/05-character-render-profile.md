# 角色渲染档案

> [← 上一篇](04-text-understanding-pipeline.md) · [文档索引](README.md) · [下一篇 →](06-image-generation-and-drift-control.md)
>
> 文档版本：2.8 · 源章节：8. 角色渲染档案 · 修订日期：2026-08-22

## 8. 角色渲染档案

### 8.1 聚合优先级

```text
用户已确认值
  > 有明确原文证据的有效观察
  > 多证据一致的高置信度推断
  > 经审核的身份原型建议
  > 画风默认值
```

身份原型只提供建议，默认优先补充服装、道具和时代风格。对于脸型、肤色、体型等敏感或个体差异大的特征，不应仅凭职业或身份自动写入确定值。

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

解析顺序为：用户本次覆盖 > 场景瞬时状态 > 目标时点有效的阶段外观 > 稳定身份锚点 > 画风默认值。若目标时间缺失且角色存在多个已批准阶段，API 返回 `ambiguous_appearance_state`，由用户选择，不擅自使用最新章节状态。

### 8.4 角色阶段形象集

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

### 8.5 身份原型

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
