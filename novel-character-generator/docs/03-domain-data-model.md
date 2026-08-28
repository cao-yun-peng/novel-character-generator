# 领域模型与数据库设计

> [← 上一篇](02-architecture-and-tech-stack.md) · [文档索引](README.md) · [下一篇 →](04-text-understanding-pipeline.md)
>
> 文档版本：3.2 · 源章节：6. 数据模型 · 修订日期：2026-08-26
>
> 当前状态：核心文本、人物、时间、任务、审批和评测表已有基础实现；部分图像与审计模型仅为预留或目标设计。实际 Schema 以 Alembic migration 和 ORM 为准，功能闭环见[追踪矩阵](19-feature-traceability-matrix.md)。

## 6. 数据模型

### 6.1 核心表

| 表 | 作用 | 关键约束 |
|---|---|---|
| `novels` | 小说元数据与处理状态 | 原文不直接塞入状态快照 |
| `source_documents` | 小说的逻辑源文档 | 只保存文档身份和当前版本指针 |
| `source_document_versions` | 每次上传/修改的不可变内容、哈希、编码与存储位置 | `(source_document_id, version)` 唯一，旧版本不覆盖 |
| `normalization_maps` | 规范化文本到原文件偏移的可逆映射 | 关联 source document version 和算法版本 |
| `chapters` | 章节边界和顺序 | `(novel_id, ordinal)` 唯一 |
| `text_chunks` | 稳定文本块、原文区间和内容哈希 | 关联 source document version；`(version_id, ordinal, content_hash)` |
| `retrieval_index_builds`、`retrieval_passages`、`retrieval_passages_fts`、`retrieval_passage_embeddings` | 上传后可重建的细粒度文本库和 BM25/向量混合索引 | 目标设计；SQLite 保存正文/FTS/索引引用，完整向量进入 Qdrant Local；绑定不可变源版本、lexical/index/embedding profile，不替代 `text_chunks` |
| `timelines` | 主时间线、分支时间线及继承关系 | 分支点以前继承父时间线状态 |
| `story_events` | 故事时间中的事件与因果顺序 | `story_order` 与叙事出场顺序分离 |
| `event_participants` | 事件中的 actor、patient、observer 等角色及证据 | `(event_id, character_id, role)` 唯一 |
| `scenes` | 场景、视角、所在事件和叙事区间 | 每个场景绑定一个时间线 |
| `characters` | 规范角色实体 | 不直接保存完整事实 JSON |
| `character_aliases` | 别名、称谓、有效范围 | `(novel_id, normalized_alias)` 建索引 |
| `feature_observations` | 字段级观察、证据与来源 | 不覆盖旧观察 |
| `feature_suggestions` | 身份原型、画风默认值等非事实建议 | 不得伪装成原文 Observation |
| `retrieval_query_runs`、`retrieval_query_hits` | 视觉精提取的 QueryPlan、候选段和排序审计 | 目标设计；可重放“为何将这些段交给模型” |
| `expression_observations` | 外显神情、内在情绪、对象和诱因 | 默认只在当前场景有效 |
| `character_appearance_states` | 角色在特定时间段的外观状态 | 同一时间线内有效区间可计算 |
| `character_image_sets` | 一个角色的阶段形象集合、默认代表形象和集合版本 | 每个集合关联已批准阶段，不按章节穷举 |
| `character_stage_images` | 阶段快照、候选图、阶段基准图及排序 | `(image_set_id, stage_key)` 唯一，可组合多个状态 |
| `character_render_profiles` | 当前生成档案及锁定状态 | 带版本号和乐观锁 |
| `pipeline_runs` | 一次导入/提取/生成运行 | 幂等键唯一 |
| `pipeline_steps` | 步骤状态、尝试次数和游标 | `(run_id, step_key)` 唯一 |
| `run_events` | 面向进度流的追加事件 | 单调序号 |
| `external_operations` | 外部调用提交、查询、取消、对账和未知状态 | `(provider, idempotency_key)` 唯一，保存 request fingerprint 与 fencing generation |
| `model_calls` | 外部调用、token、价格快照和请求 ID | 请求摘要不得含密钥 |
| `agent_runs` | 一次 Agent 语义任务、版本、预算和最终状态 | 关联 pipeline step |
| `agent_turns` | 每轮模型输出摘要、上下文哈希和使用量 | 不保存隐藏推理内容 |
| `tool_calls` | 工具输入/输出摘要、耗时、错误和副作用 | `call_id` 唯一，写工具需幂等 |
| `decision_records` | 实体合并、档案选择等关键决策及证据 | 保留策略/人工来源 |
| `human_approvals` | 审批对象、审批结果、修改内容与审批人 | 追加写审计记录 |
| `agent_evaluations` | 最终结果、工具选择与执行轨迹评分 | 关联评测集和评分器版本 |
| `eval_datasets` | 评测集版本、来源、切分策略和冻结状态 | 发布测试集不可被运行时修改 |
| `eval_cases` | 文本、实体、时间、Agent、图像等评测样本 | 关联小说级 split 和标注版本 |
| `eval_runs` | 被测配置、基线、随机种子、费用与汇总 | 配置哈希和数据集版本不可变 |
| `eval_results` | 每个 case、grader 的分数、通过状态和诊断 | `(eval_run_id, eval_case_id, grader_version)` 唯一 |
| `grader_versions` | 确定性、模型和人工评分器的版本化定义 | 模型评分器必须记录模型与 rubric |
| `artifacts` | 图像、源文件、模型等统一产物 | 内容哈希、MIME、存储 URI |
| `generated_images` | 图像业务元数据和评测结果 | 关联 workflow/profile/run |

一期 Prompt 使用 Git 管理的文件版本；二期增加 `prompt_templates`、`identity_prototypes`、发布记录和管理 API。

### 6.2 P0 前置数据模型

以下数据模型是 **P0 基础结构**。其中多项已经有 ORM 与迁移，但仍需按追踪矩阵核对调用链和测试；“表已存在”不等于对应功能已经闭环。它们决定证据能否重放、角色合并能否回滚，以及后续阶段形象是否可信：

| P0 项 | 最低要求 | 未完成时的限制 |
|---|---|---|
| `MentionSpan` | 持久化每次人名、称谓、代词的原文区间、原始文本、候选角色和最终绑定 | 不允许自动执行实体合并 |
| `AliasAssertion` | 保存别名类型、说话人/视角、场景、时间线、支持与反对证据、审批状态 | 别名只能作为候选召回，不能成为确定关系 |
| 规范化偏移映射 | 版本化记录 Unicode、换行和不可见字符转换，并可逆映射回原文件 | 无法精确回到原文的观察不得批准 |
| Grounding 状态 | 区分 `exact`、`fuzzy`、`ungrounded`、`manually_grounded` | `ungrounded` 默认不得进入 RenderProfile |
| 重叠块去重 | 使用来源版本、证据区间、字段、规范值和提取器版本生成稳定指纹 | 禁止直接按出现顺序去重 |
| 事件参与者 | 保存 actor、patient、observer 等参与角色及证据 | 复杂事件不自动绑定外观变化 |
| 双时态记录 | 区分故事有效时间与系统抽取、审核、失效时间 | 不能可靠重放历史决策 |
| 审核优先级 | 综合影响范围、错误风险、不确定性和角色重要度排序 | 高影响合并与阶段选择必须人工处理 |

```python
class SourceDocumentVersion(BaseModel):
    id: UUID
    source_document_id: UUID
    version: int
    content_sha256: str
    storage_uri: str
    encoding: str
    normalization_map_id: UUID
    supersedes_version_id: UUID | None
    created_at: datetime


class MentionSpan(BaseModel):
    id: UUID
    source_document_version_id: UUID
    source_chunk_id: UUID
    char_start: int
    char_end: int
    mention_text: str
    mention_kind: Literal["explicit_name", "descriptor", "pronoun", "unknown"]
    candidate_character_ids: list[UUID]
    resolved_character_id: UUID | None
    grounding_status: Literal["exact", "fuzzy", "ungrounded", "manually_grounded"]
    normalization_map_version: str


class AliasAssertion(BaseModel):
    id: UUID
    alias_text: str
    normalized_alias: str
    mention_span_id: UUID
    proposed_character_id: UUID | None
    speaker_id: UUID | None
    scene_id: UUID | None
    timeline_id: UUID | None
    supporting_evidence_ids: list[UUID]
    opposing_evidence_ids: list[UUID]
    status: Literal["proposed", "approved", "rejected", "superseded"]
```

### 6.3 FeatureObservation

```python
class FeatureObservation(BaseModel):
    id: UUID
    character_id: UUID
    field_path: str                 # 字段路径；视觉事实使用 skin.color、body.build 等规范路径
    value: JsonValue
    source_kind: Literal["text", "manual"]
    source_document_version_id: UUID | None
    source_chunk_id: UUID | None
    mention_span_id: UUID | None
    evidence_quote: str | None
    char_start: int | None
    char_end: int | None
    grounding_status: Literal["exact", "fuzzy", "ungrounded", "manually_grounded"]
    chapter_ordinal: int | None
    scene_id: UUID | None
    event_id: UUID | None
    temporal_scope: TemporalScope | None  # 故事有效时间；永久身份锚点可为空
    epistemic_status: Literal["asserted", "negated", "inferred", "uncertain"]
    confidence: float               # 0..1，仅表示抽取置信度
    extraction_run_id: UUID | None
    manual_approval_id: UUID | None
    extractor_version: str
    supersedes_id: UUID | None
    record_status: Literal["active", "invalidated", "superseded"]
    recorded_at: datetime           # 系统时间：何时记录
    invalidated_at: datetime | None
    invalidated_by_run_id: UUID | None


class FeatureSuggestion(BaseModel):
    id: UUID
    character_id: UUID
    field_path: str
    value: JsonValue
    suggestion_kind: Literal["identity_prototype", "style_default"]
    resource_version: str
    confidence: float
    allowed_fields: list[str]
    rationale: str
    status: Literal["candidate", "accepted", "rejected"]
    approval_id: UUID | None
```

当前数据库的 `temporal_scope` 是 JSON。提取链路在其中保存 `life_phase_key` 和 `life_phase_label` 扩展键，Observation API 再将它们投影为同名顶层响应字段；没有为人生阶段新增独立数据库列。领域值对象的强类型化扩展可在后续迁移中完成。

规则：

- 可出图视觉事实必须使用原子规范路径，主要根字段为 `skin`、`hair`、`face`、`body`、`clothing`、`cleanliness`、`age`/`age_stage`、`accessory`/`accessories`、`injury`/`injuries`、`distinctive_marks` 和 `disguise`；
- `appearance.build` 规范为 `body.build`；综合 `appearance` 只作为旧输入兼容层，持久化前拆成 `skin.color`、`hair.color`、`hair.length`、`clothing.style`、`cleanliness`、`body.build` 等原子事实，无法安全拆分时降级为 `body.description`；
- `field_path` 不带角色名前缀，例如使用 `hair.color`，不能使用 `唐三.hair.color`；
- `life_phase_key` 是同一人物规范人生历程中的阶段维度，不等于 `timeline_id`。例如“前世”和“转生幼年”通常是同一 canonical 时间线上的两个阶段，平行世界、假设分支才建立父子时间线；
- 原文观察永远不被身份原型覆盖；
- `inferred` 与 `text/asserted` 必须区分；
- 同一字段允许存在多条观察和冲突；
- 用户修订创建新的 `manual` 观察或档案版本，不静默改写历史；
- 原文引用应控制长度并保存精确区间，避免保存无法定位的整段文本；
- `text` Observation 必须关联不可变的 source document version；`ungrounded` 默认不得进入 RenderProfile；
- `text` Observation 必须关联 extraction run；`manual` Observation 必须关联 `manual_approval_id`；
- 故事有效时间由 `temporal_scope` 表示，系统记录/失效时间由 `recorded_at`、`invalidated_at` 表示，两类时间不得混用；
- 章节删除或文本版本更新只会失效旧观察，不物理删除；重放历史运行时按 source version 和系统时间读取当时有效记录；
- 原型和画风默认值保存为 `FeatureSuggestion`，只有人工接受后才参与渲染决策，不能写成 `source_kind=prototype/style` 的事实。

### 6.4 时间线、事件与场景作用域

章节顺序是“作者何时讲到”，故事时间是“事情何时发生”，两者必须分开。回忆可能出现在第 30 章，但描述的是角色少年期；不能仅用 `chapter_ordinal` 推断角色当时的外观。

```python
class Timeline(BaseModel):
    id: UUID
    novel_id: UUID
    name: str
    parent_timeline_id: UUID | None
    branch_event_id: UUID | None
    canonicality: Literal["canonical", "alternate", "hypothetical"]


class StoryEvent(BaseModel):
    id: UUID
    timeline_id: UUID
    name: str | None
    story_order: Decimal | None       # 故事内顺序，允许后续插入
    starts_at: datetime | None        # 小说给出明确时间时才填写
    ends_at: datetime | None


class EventParticipant(BaseModel):
    event_id: UUID
    character_id: UUID
    role: Literal["actor", "patient", "observer", "speaker", "other"]
    evidence_observation_ids: list[UUID]


class Scene(BaseModel):
    id: UUID
    novel_id: UUID
    timeline_id: UUID
    event_id: UUID | None
    chapter_ordinal: int
    narrative_order: int             # 文本中的出场顺序
    point_of_view_character_id: UUID | None


class TemporalScope(BaseModel):
    timeline_id: UUID
    start_event_id: UUID | None
    end_event_id: UUID | None
    start_scene_order: Decimal | None # 同一场景内的先后顺序
    end_scene_order: Decimal | None
    start_chapter_ordinal: int | None
    end_chapter_ordinal: int | None
    scope_type: Literal[
        "instant", "scene", "chapter", "interval", "persistent", "unknown"
    ]
    presentation_mode: Literal[
        "direct", "flashback", "flashforward", "dream",
        "illusion", "rumor", "hypothetical"
    ]
    reality_status: Literal["canonical", "subjective", "alleged", "counterfactual"]
```

规则：

- `narrative_order` 与 `story_order` 独立保存，禁止互相替代；
- 同一场景内“先微笑、后皱眉”使用 `scene_order` 区分连续瞬时状态，不误判为同时冲突；
- 新分支时间线从父时间线继承分支事件以前的角色状态，分支后独立演化；
- 同一时间线、章节和字段在不同 `life_phase_key` 下分别聚合，避免“前世黑发”和“转生幼年短发”被误判成同阶段冲突；
- 无法定位时使用 `unknown`，不得强行绑定到“当前时间”；
- 梦境、幻觉、传闻和假设保留为证据，但不自动更新 canonical 角色状态；
- 时间线重绑定属于可审计决策，修改后只重算受影响角色的状态和快照。

### 6.5 神情与内外情绪观察

神情可以提取，但必须区分“可见表情”和“角色内心”。例如“嘴角带笑，眼神却冰冷”不能被压缩成单一的 `happy`。

```python
class ExpressionObservation(BaseModel):
    id: UUID
    character_id: UUID
    source_document_version_id: UUID
    source_chunk_id: UUID
    char_start: int
    char_end: int
    outward_emotion: Literal[
        "joy", "sadness", "anger", "fear", "surprise",
        "disgust", "calm", "mixed", "unknown"
    ]
    expression_text: str | None       # 受控枚举无法完整表达时的短语
    visible_cues: list[str]           # 皱眉、抿嘴、瞳孔收缩等可见证据
    intensity: float | None           # 0..1
    valence: float | None             # -1..1
    arousal: float | None             # 0..1
    is_masked: bool | None            # 是否刻意隐藏真实情绪
    internal_emotion: str | None      # 仅在原文明确或可靠叙述时填写
    target_character_id: UUID | None
    cause_event_id: UUID | None
    scene_id: UUID | None
    temporal_scope: TemporalScope
    evidence_quote: str
    epistemic_status: Literal["asserted", "inferred", "uncertain"]
    confidence: float
    extraction_run_id: UUID
    extractor_version: str
    record_status: Literal["active", "invalidated", "superseded"]
    recorded_at: datetime
    invalidated_at: datetime | None
    invalidated_by_run_id: UUID | None
```

神情默认是 `instant` 或 `scene` 级瞬时状态，不写入永久脸部特征。“常年冷着脸”只有在文本明确表达持续性时，才可形成 `persistent` 的习惯神态观察。内心情绪不得由面部表情反推为事实；模型推断必须标记为 `inferred` 并降低置信度。反过来，内心写着“狂喜”但原文明说“不动声色”时，视觉快照采用外显神情而不是内心情绪。

### 6.6 稳定身份、阶段外观与场景状态

角色描述采用三层模型，避免把少年、成年、受伤后或伪装状态互相覆盖：

```text
IdentityAnchor（跨时间稳定）
  + CharacterAppearanceState（某一阶段有效）
  + SceneCharacterState（当前场景瞬时）
  + RenderOverrides（本次用户明确覆盖）
  = ResolvedCharacterSnapshot（本次生成的不可变快照）
```

```python
class CharacterAppearanceState(BaseModel):
    id: UUID
    character_id: UUID
    temporal_scope: TemporalScope
    label: str | None                 # 少年期、受伤后、宴会伪装等
    state_kind: Literal[
        "base_age_stage", "persistent_change", "disguise",
        "clothing", "temporary_condition", "manual_override"
    ]
    merge_priority: int
    age_stage: str | None
    face: FaceBlock | None
    body: BodyBlock | None
    hair: HairBlock | None
    clothing: ClothingBlock | None
    injuries: list[MarkItem]
    distinctive_marks: list[MarkItem]
    cleanliness: str | None
    disguise: str | None
    field_sources: dict[str, list[UUID]]
    resolver_version: str
    created_by_run_id: UUID
    record_status: Literal["active", "invalidated", "superseded"]
    status: Literal["draft", "needs_review", "approved"]


class SceneCharacterState(BaseModel):
    character_id: UUID
    scene_id: UUID
    expression_observation_ids: list[UUID]
    pose: str | None
    action: str | None
    temporary_condition: list[str]


class ResolvedCharacterSnapshot(BaseModel):
    character_id: UUID
    timeline_id: UUID
    target_event_id: UUID | None
    target_scene_id: UUID | None
    render_profile_version: int
    identity: IdentityBlock
    applied_state_ids: list[UUID]
    resolved_appearance: ResolvedAppearanceBlock
    scene_state: SceneCharacterState | None
    field_sources: dict[str, list[UUID]]
    unresolved_conflicts: list[ConflictItem]
    snapshot_schema_version: str
    resolver_version: str
```

`CharacterAppearanceState` 是部分字段覆盖层，不要求每个状态复制完整角色。解析器先应用基础年龄阶段，再按 `persistent_change → disguise → clothing → temporary_condition → manual_override` 合并同一目标时点所有有效状态；同优先级写入同一字段且值不兼容时停止解析并进入审核。最终扁平结果写入 `resolved_appearance`，完整 JSON 作为不可变 Artifact 保存，`applied_state_ids` 仅用于追溯，避免状态组合爆炸。

父子时间线解析时，祖先状态只读取到子线的 `branch_event_id`，按“最远祖先 → 当前子线”顺序应用；子线分支后的明确状态可以覆盖继承基线，父线分支后的变化不会泄漏到子线。同一时间线、同一优先级的重叠矛盾仍必须进入审核，时间线循环或无效分支事件直接拒绝解析。

`CharacterConflict.conflict_kind` 区分普通 `incompatible_values` 与 `human_confirmation`。后者表示新自动事实与已批准档案、人工 override 或人工确认身份锚点冲突；自动任务只能创建待审核冲突，不能覆盖确认值。身份锚点冲突解决后直接更新档案锚点并写入 `manual:conflict:<id>` 来源，阶段字段则形成最高优先级 `manual_override` 状态。

### 6.7 CharacterRenderProfile

```python
class CharacterRenderProfile(BaseModel):
    character_id: UUID
    version: int
    status: Literal["draft", "needs_review", "approved", "locked"]
    identity_anchor: IdentityBlock
    default_stage_key: str | None
    appearance_state_ids: list[UUID]
    palette: ColorPaletteBlock
    field_sources: dict[str, list[UUID]]  # observation IDs
    field_suggestions: dict[str, list[UUID]]  # accepted suggestion IDs
    unresolved_conflicts: list[ConflictItem]
    style_preset: str
    approved_by: str | None
    approved_at: datetime | None
    revision: int                      # 乐观并发控制
    record_status: Literal["active", "stale"]
    source_document_version_id: UUID | None
    input_fingerprint: str | None
```

`CharacterRenderProfile` 是用户确认过的角色规则与可用状态集合，不再代表唯一的“当前外观”。源文档版本替换时，旧批准档案保持 `status=approved` 和原 revision 不变，同时将 `record_status` 标记为 `stale`；新版本分析形成新的活动草稿。每次生成前必须解析出 `ResolvedCharacterSnapshot`，stale 档案不得生成快照。所有 Block 使用 Enum 或受约束字符串，未知值为 `None`。不要使用无法区分缺失、空列表和明确“无”的字段定义。

上面的类保留当前实现兼容字段。目标版本需要把 `field_sources` 扩展为带 `source_kind` 的字段级 provenance，至少区分 `novel_asserted`、`human_decision`、`approved_suggestion` 和 `reference_asset`。`style_preset` 逐步从角色 Profile 迁出，进入 `SceneRenderBrief`/WorkflowProfile；`palette` 只有在它是该角色经批准的固有配色时才保留在 Profile。`ResolvedCharacterSnapshot` 只保存目标时间点的已批准角色外观，不保存画风、镜头、设计性灯光或 Provider 参数。详见[角色渲染档案](05-character-render-profile.md)和[视觉优先的出图字段与全文抽取重构方案](23-visual-first-extraction-refactor.md)。

### 6.8 任务状态机

```text
PipelineStep
queued → claimed → running ───────────────→ succeeded
                   ├──→ waiting_external ─→ running
                   ├──→ waiting_approval ─→ queued（审批后新 attempt）
                   ├──→ retry_scheduled ──→ queued
                   ├──→ cancelled
                   └──→ failed

ExternalOperation
prepared → submitting → submitted → polling → succeeded
              │             │          ├────→ failed
              │             │          └────→ cancelled
              └→ submission_unknown → reconciling
                                         ├→ submitted
                                         ├→ failed
                                         └→ manual_review
```

```python
class ExternalOperation(BaseModel):
    id: UUID
    run_id: UUID
    step_id: UUID
    provider: str
    operation_type: str
    request_fingerprint: str
    idempotency_key: str
    state: Literal[
        "prepared", "submitting", "submitted", "polling", "submission_unknown",
        "reconciling", "manual_review", "succeeded", "failed", "cancelled"
    ]
    external_job_id: str | None
    lease_generation: int
    attempt: int
    request_hash: str
    response_hash: str | None
    last_reconciled_at: datetime | None
```

状态变化使用显式允许列表和 compare-and-set，不能由任意路由直接写字符串。`PipelineStep` 表示业务步骤是否可继续，`ExternalOperation` 表示一次远程副作用的提交真相；二者不得合并成一个状态字段。Worker 每次写入必须携带 `lease_generation`，旧租约写入由 fencing 拒绝。Provider 不支持幂等键且进程在提交窗口崩溃时，操作进入 `submission_unknown`，自动重提之前必须先按请求指纹、远程任务列表、回调或人工方式对账。无法自动对账时将 ExternalOperation 置为 `manual_review`，同时把 PipelineStep 置为 `waiting_approval` 并创建审批项。

---

[← 上一篇](02-architecture-and-tech-stack.md) · [文档索引](README.md) · [下一篇 →](04-text-understanding-pipeline.md)
