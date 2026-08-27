# 通用小说分解质量改进方案

> [← 上一篇](21-retrieval-augmented-visual-enrichment.md) · [文档索引](README.md) · [下一篇 →](23-visual-first-extraction-refactor.md)
>
> 文档版本：1.1 · 修订日期：2026-08-26
>
> 当前状态：本文大部分内容仍是后续实现方案；22.13 所述完整抽取检查器已经落地。实际能力边界见[当前实现状态](00-current-status.md)。

## 22.1 目标与适用边界

本方案解决一次真实小说分解中暴露出的共性问题：实体未收敛、人生阶段缺失、外观状态碎片化、变身被误判为冲突、检索上下文过宽、关系类型失控，以及“Run 成功但结果尚不可用于出图”。

项目目标始终是处理**大多数具有角色叙事的中文小说**，不是适配某一部作品。真实作品只用于发现问题、构造匿名化回归样例和验证改进，不得成为生产代码的隐含前提。

通用性约束如下：

1. `src/`、生产 Prompt、数据库枚举和默认词典不得写死作品名、角色名、门派、力量体系或专属道具。
2. “前世、童年、成年、变身、梦境”等是跨作品语义概念；具体阶段名称由当前小说的证据动态产生，不使用固定作品阶段表。
3. 项目词典只能作为版本化、可替换的检索资源；没有某部作品词典时，主流程仍须正确运行。
4. 规则必须由结构化证据触发，例如年龄变化、时间跳跃、叙事模式和外观变化，不能由某个专名触发。
5. 所有阈值、兼容词表和模型选择通过多作品 validation 集冻结；单部作品结果只能发现问题，不能证明方案通用。
6. 生产实现中的示例专名扫描纳入 CI：除测试夹具、评测数据和说明文档外，业务代码与 Prompt 不得出现样例作品专名。

《斗罗大陆》在本文中仅作为问题示例。例如“同一角色前世与转生幼年混在一起”代表通用的**跨人生阶段污染**问题；同样的机制必须能够处理现代小说中的“少年/十年后”、悬疑小说中的“真实身份/伪装身份”、科幻小说中的“原身体/克隆体”，以及循环叙事中的不同轮次。

## 22.2 总体修改思路

现有链路以块级一次结构化提取为主，后续直接持久化人物、事实、场景和时间假设。改进后分为“发现、收敛、定位、聚合、验收”五个层次：

```text
章节与细粒度 passage
  → 块级发现：mention、候选人物、证据、场景、时间信号
  → 小说级收敛：实体聚类、别名审核、泛称抑制
  → 角色级时间定位：人生阶段、时间线、叙事模式、变身状态
  → 事实绑定：character_id + phase + timeline + scene/event + mention
  → 分层外观聚合：身份基线 + 阶段基线 + 持久变化 + 临时叠加
  → 冲突分类与人工审核
  → 分解质量报告：ready / needs_review / insufficient
  → 只有满足门禁的档案进入图像生成
```

实现原则是保留当前块级提取的吞吐优势，但不让块级模型独自决定全书人物身份和人生阶段。块级输出是候选证据，小说级确定性流程与有界语义判断负责收敛。

## 22.3 人物实体与别名收敛

### 22.3.1 问题

同一人物可能以全名、简称、昵称、亲属称谓、职位和代词出现；“门房”“医生”“男孩”等泛称也可能只在局部场景有效。如果逐块按字符串创建人物，会产生重复实体和没有稳定身份的渲染档案。

### 22.3.2 两阶段实体解析

第一阶段只发现，不做高风险合并：

- 保存每次 `MentionSpan` 的精确区间、类型、候选角色和局部上下文；
- 姓名可创建候选实体，称谓和代词默认只加入候选集；
- 单次出现的泛称没有独立外观或关系证据时，保存为 unresolved mention，不创建 RenderProfile；
- Observation 暂时引用候选 mention，不能只保存自由文本角色名。

第二阶段在小说级执行实体收敛：

```text
字符串规范化与精确别名
  → 同场景共现和互斥约束
  → 说话人、称谓对象与亲属关系约束
  → 跨章节稳定属性和叙事连续性
  → 候选聚类评分
  → 高置信自动链接 / 中置信人工合并建议 / 低置信保持分离
```

自动合并必须同时满足正证据阈值和反证据为零。以下情况强制人工确认：

- 两个名称在同一场景同时出现；
- 合并后产生不可能的亲属自环或互斥身份；
- 泛称跨场景指向不同人物；
- 两个候选各自已有已批准档案或图像资产；
- 仅靠向量相似或模型主观判断，没有可回放证据。

### 22.3.3 生命周期

统一人物状态为：

```text
candidate → active → merged | rejected
```

- `candidate`：刚发现，尚未达到稳定身份门槛；
- `active`：证据充分或人工批准，可参与阶段聚合；
- `merged`：已合并到其他规范角色；
- `rejected`：误识别、纯泛称或非人物。

必须提供候选确认和别名审核入口，不能让 `candidate` 与 `proposed alias` 永久没有状态迁移。人物合并/拆分继续保留 revision、幂等键和审计快照。

## 22.4 通用人生阶段与时间语义

### 22.4.1 四个正交维度

外观时间语义不能压缩成单一 `age_stage`。每条事实至少区分：

| 维度 | 含义 | 示例 |
|---|---|---|
| `timeline_id` | 事实属于哪个现实分支 | 主线、平行世界、假设分支 |
| `presentation_mode` | 作者如何讲述 | 直接叙述、回忆、预叙、梦境、传闻 |
| `life_phase_key` | 角色在当前人生历程中的阶段 | 少年期、入职后、失忆期、重生幼年 |
| `transformation_state` | 同一阶段内的可逆或特殊形态 | 变身、伪装、附体、病中、战斗形态 |

回忆通常只是 `presentation_mode=flashback`，不自动创建新时间线；梦境也不是默认 canonical 现实。重生前后是否属于同一 timeline，由作品叙事定义，但两者必须有不同 life phase。变身通常是 transformation，不是新人生阶段，也不是永久身份冲突。

### 22.4.2 小说级阶段发现

增加 `resolve_character_phases` 步骤，输入全书已校验的时间信号和角色事件摘要，不输入整本原文。阶段边界信号包括：

- 明确年龄、年份、学年、婚育、职业或身份变化；
- “多年后、小时候、重生后、失忆期间、恢复记忆后”等时间表达；
- 死亡、转生、重大成长、长期伤势或持续身份改变；
- 章节/卷级时间跳跃和事件因果顺序；
- 人工修正的 scene/event/timeline 绑定。

阶段 key 不从作品专名硬编码，而由规范化标签和稳定边界生成。例如：

```text
phase_key = slug(normalized_label) + short_hash(boundary_evidence)
```

常见生理年龄仅规范到 `age_stage`；小说专属阶段保留原标签。无法唯一判断时生成多个候选并 `defer`，不得静默把事实塞入默认阶段。

### 22.4.3 建议数据模型

新增角色阶段注册表，避免阶段只散落在 Observation JSON 中：

```python
class CharacterLifePhase:
    id: UUID
    character_id: UUID
    timeline_id: UUID
    phase_key: str
    label: str
    phase_order: Decimal | None
    age_stage: str | None
    start_event_id: UUID | None
    end_event_id: UUID | None
    evidence_observation_ids: list[UUID]
    confidence: float
    status: Literal["candidate", "active", "rejected"]
    resolver_version: str
```

`FeatureObservation.temporal_scope.life_phase_key` 仍可保留为快速投影，但必须引用有效阶段注册项。阶段边界修正后，只重算受影响角色的状态和快照。

## 22.5 事实类型、来源与 Mention 绑定

### 22.5.1 分离事实领域

模型可能同时返回外观、身份、能力、职业、关系和事件行为。它们都可以有价值，但不能混进视觉聚合。为 Observation 增加或派生 `observation_domain`：

```text
visual | identity | relationship | capability | narrative
```

只有 `visual` 进入 AppearanceState。生产落库前使用版本化字段注册表校验；未知字段进入 rejection/suggestion，不直接成为可出图事实。

### 22.5.2 统一来源语义

`source_kind` 表示事实真值来源，`extraction_mode` 表示如何发现：

```text
source_kind: text | manual
extraction_mode: chunk | retrieval_enrichment | manual
```

把现有 `retrieval_text` 数据迁移为 `source_kind=text, extraction_mode=retrieval_enrichment`。这样块级和检索增强发现的原文事实使用同一聚合规则，不会因实现路径不同被过滤。

### 22.5.3 Mention 所有权

每条自动 Observation 必须：

1. 精确绑定 source document version、chunk/passage 和 evidence span；
2. 在证据附近找到已解析的 mention；
3. 保存 `mention_span_id` 和最终 `character_id`；
4. 如果 mention 所有权不唯一，降级为待审核，不进入自动聚合。

这使人物合并、拆分和重新共指时能够准确迁移相关事实，而不是按角色名或整章批量猜测。

## 22.6 分层外观聚合

### 22.6.1 目标模型

状态按语义层级组织，而不是按每条事实或每章生成一个状态：

```text
IdentityAnchor              跨阶段稳定且人工确认的身份特征
  + BaseLifePhaseState      某人生阶段的基础年龄与外观
  + PersistentChangeState   伤疤、截肢、长期染发等持续变化
  + TransformationState     变身、伪装、附体等有界形态
  + SceneOverlayState       服装、污渍、湿发、瞬时表情等临时状态
  = ResolvedSnapshot
```

同一 phase、同一 state kind、作用域兼容的多个原子字段合并为一个状态。章节序号只帮助确定有效区间，不直接成为状态身份。

### 22.6.2 作用域归一化

- 身体结构、自然发色等默认持续到明确变化，但不得跨 life phase 自动继承；
- 服装、整洁度、表情默认限于 scene/event；
- 伤势根据“受伤/恢复/留下伤疤”等证据决定临时或持久；
- transformation 必须有开始条件，缺少结束证据时标记范围不确定并待审；
- 已批准人工值优先，但不能覆盖其他 timeline/phase 的原文事实。

### 22.6.3 冲突分类

冲突不再只有“值不同”一种：

| 类型 | 处理 |
|---|---|
| `true_incompatibility` | 同一有效范围内确实互斥，进入人工审核 |
| `temporal_change` | 前后变化，拆成连续状态，不视为错误 |
| `transformation_variant` | 进入变身/伪装叠加层 |
| `compatible_description` | 经版本化同义/包含规则合并，保留原文值 |
| `uncertain_scope` | 时间范围不清，要求补证据或人工定位 |
| `protected_manual_conflict` | 新自动结果挑战人工确认，必须人工处理 |

颜色、年龄和体型兼容规则必须是跨作品词汇资源，并记录规则版本；模型只能给出候选分类，最终是否自动合并由确定性策略决定。

## 22.7 场景、事件与关系

关系分成两类：

1. 稳定或阶段性人物关系：亲属、师徒、伴侣、上下级、敌对等，使用封闭且版本化的 ontology；
2. 一次性事件行为：护送、检查、交付、攻击、观察等，写入 `StoryEvent + EventParticipant`，不扩张 relation type。

`canonical_relation_type` 必须统一方向语义，例如选择 `parent_of/child_of`，不能同时保留 `father`、`father_of` 和自由中文同义词。原始模型词保存在 provenance 中用于审计。

每个已创建 StoryEvent 至少满足以下之一：

- 有一个带证据的 participant；
- 明确标记为环境/无人物事件；
- 进入 incomplete/deferred，而不是以空参与者事件悄悄通过。

场景覆盖率是质量指标，不要求机械地每章一个场景；但有有效人物事实却没有可绑定 scene/event 时必须产生 warning。

## 22.8 检索增强的预算与去偏

精提取应补缺，而不是近似重读全书。QueryPlan 改为按“角色 × 阶段 × 字段组”构建，并执行以下预算：

1. 每个字段组独立 BM25/vector top-K；
2. RRF 后做近重复折叠和按章节去偏；
3. 只对高分 anchor 加相邻 passage，不对每个命中无限扩展；
4. 对已被证据覆盖的字段降低优先级；
5. evidence packet 同时受 passage 数、token 数和章节跨度限制；
6. Provider 请求必须设置最大输出 token、超时、费用和最大调用数；
7. 报告“选中 passage/全库 passage 比例”和“每个新增已确认字段成本”。

默认参数只作为 PoC 候选。不同体裁可能需要不同已验证的 RetrievalProfile，但业务逻辑和证据契约保持一致。

## 22.9 技术成功与语义质量分离

`PipelineRun.status=succeeded` 只表示步骤按契约执行完成，不代表结果已经适合出图。新增版本化 `DecompositionQualityReport`：

```python
class DecompositionQualityReport:
    run_id: UUID
    source_document_version_id: UUID
    evaluator_version: str
    quality_status: Literal["ready", "needs_review", "insufficient"]
    metrics: dict[str, float | int]
    warnings: list[QualityIssue]
    blocking_issue_codes: list[str]
    created_at: datetime
```

首版确定性指标至少包括：

- candidate/active/merged 人物数和高影响重复候选数；
- mention 解析率、Observation mention 绑定率和 exact grounding 率；
- 主要角色阶段覆盖率、无阶段视觉事实比例；
- 每角色状态数、单字段碎片状态比例；
- unresolved conflict 数及分类；
- 事件参与者覆盖率、关系 ontology 合法率；
- RenderProfile 的默认阶段、identity anchor、审核状态；
- 检索选中率、模型 token/延迟/费用及每个有效新增字段成本。

建议首版阻断条件：

- 主要角色仍存在高置信重复实体；
- 主要角色跨明显年龄/身份跃迁但没有有效 life phase；
- 自动 Observation 没有精确证据或人物 mention 所有权；
- 主要角色没有可解析的默认阶段快照；
- unresolved hard conflict 仍会影响目标图像字段。

首版报告由确定性 `QualityEvaluator` 生成，不能把完整质量判断委托给一个模型 Agent。它在以下时机执行：首次全文实体/阶段 final 解析并完成聚合后、增量章节影响闭包重算后、人物合并/拆分后、阶段人工修正后，以及检索增强产生新 asserted Observation 后。相同输入指纹和 evaluator version 必须得到相同报告。

`Review Agent` 只处理报告标出的少量语义疑难，例如高影响人物误合并疑点、阶段边界语义不清、冲突属于时间变化还是矛盾、或 `not_stated` 的检索覆盖是否合理。它只输出 `ReviewFinding`，不能直接修改指标、`quality_status`、阻断代码或业务事实。Agent 关闭或失败时，确定性报告仍然可生成，并将对应问题转人工。

质量状态不自动批准档案。`ready` 表示可以进入人工档案确认；图像生成仍只接受 approved/locked Profile。

## 22.10 API、Worker 与迁移建议

建议增加或调整以下步骤：

```text
normalize_and_chunk
extract_candidates
resolve_entities
resolve_character_phases
bind_observations
aggregate_appearance
evaluate_decomposition_quality
```

为保持可恢复性，每步使用独立 cursor 和稳定输入指纹。实体或阶段人工修正后，只触发 `bind_observations → aggregate → quality`，不默认重新调用全文 LLM。

建议 API：

```text
GET  /novels/{novel_id}/entity-review
POST /characters/{character_id}/accept
POST /alias-assertions/{id}/resolve
GET  /characters/{character_id}/life-phases
POST /characters/{character_id}/life-phases/{id}/resolve
GET  /runs/{run_id}/quality-report
```

迁移按兼容顺序执行：

1. 增加 `character_life_phases`、质量报告和 `extraction_mode/observation_domain`；
2. 回填现有 source kind 与可确定 domain，不改写原始证据；
3. 新聚合器以新 resolver version 生成并行派生结果；
4. 对比旧/新状态与档案，不原地覆盖已批准数据；
5. 验收后将新 resolver 设为默认，旧版本继续可重放。

## 22.11 实施顺序

### P0：先修数据正确性

1. 统一 `retrieval_text` 的来源语义，使检索事实进入聚合；
2. Observation 绑定 MentionSpan，未知视觉字段不进入聚合；
3. 补人物 candidate 接受、别名审核和重复实体建议；
4. 统一关系 ontology，并持久化 EventParticipant；
5. 增加确定性质量报告，暴露当前结果是否可用。

### P1：修阶段和状态模型

1. 新增角色阶段注册表和小说级阶段解析步骤；
2. 将 timeline、presentation、life phase、transformation 分离；
3. 聚合器改为五层状态模型；
4. 冲突分类支持时间变化、变身和兼容描述；
5. 对已有项目执行并行重聚合和差异报告。

### P2：优化成本与体验

1. 收紧检索 passage、邻居和 token 预算；
2. 为人物/阶段/冲突提供批量审核工作台；
3. 接入多作品黄金集 Runner、报告和发布门禁；
4. 根据评测结果冻结 RetrievalProfile、EntityResolver 和 PhaseResolver 版本。

## 22.12 通用性评测与完成定义

评测数据按**作品隔离**，不能把同一小说不同章节拆进训练/验证/测试。至少覆盖：

| Slice | 必须验证的问题 |
|---|---|
| 古代/玄幻、称谓密集 | 师父、殿下、门主等称谓是否错误合并 |
| 现代都市、职业变化 | 学生期/工作期是否形成阶段而不是新人物 |
| 第一人称/多视角 | “我、他、她”是否绑定正确人物 |
| 悬疑/伪装/身份反转 | 伪装是否成为 transformation，秘密身份是否被过早合并 |
| 重生/穿越/时间循环 | life phase、timeline 和 presentation 是否分离 |
| 科幻分身/克隆体 | 高相似人物是否错误自动合并 |
| 群像、同名人物 | cluster 是否保持独立，主要角色与路人是否分层 |
| 外貌描写稀少 | 系统是否正确留白而不是靠职业和性格补画 |

完成标准不是某一示例作品看起来正确，而是：

- 冻结测试集中主要角色 mention F1、阶段准确率和视觉事实 precision 达到[评测门禁](12-evaluation-and-acceptance.md)；
- 关键 slice 的跨人物、跨阶段和跨时间线污染为零或低于冻结阈值；
- 没有作品专属逻辑进入生产代码和 Prompt；
- 新作品不配置专属词典也能走完整链路，词典只带来可量化增益；
- 示例作品改进不能以其他作品关键 slice 回归为代价；
- 每个自动合并、阶段边界、冲突分类和最终快照均可回到证据和 resolver 版本。

## 22.13 当前落地：完整抽取检查器

逐块 v3 请求、原始响应、视觉候选和服务端定位结果通过 `tests/测试/inspect_visual_candidates.py` 检查；旧八类联合抽取检查器已经删除。

检查器覆盖八类块级输出：mention、alias、observation、expression、scene、timeline、relation 和 unresolved reference，并额外执行与生产链路一致的证据检查、区间修复、视觉字段规范化、人生阶段规范化、亲属事实转关系和项目门禁解释。

每个 TXT 生成四类诊断产物：

1. `*.extraction.prompt.json`：生产 Provider 的精确请求体，包含 system Prompt、JSON Schema 和对应小说 Chunk；
2. `*.extraction.raw.json`：Provider 原始响应、延迟、finish reason 和 Token usage；
3. `*.extraction.processed.json`：Schema 校验结果及逐类别规范化结果；
4. `*.extraction.report.json`：证据命中率、类别数量、warnings、errors、项目门禁和复核结论。

组合 Prompt 由生产 Provider 暴露的唯一请求构造函数生成，检查器不复制 Prompt。`--prompt-only` 只写请求预览，不调用模型，也不读取 API Key 的明文值；输出含小说原文，因此已加入 `.gitignore`。

该工具属于**本地可回放诊断 Trace**，用于回答单次抽取效果问题；它尚不是保存到数据库的全链路 Pipeline Trace，也不评估小说级实体聚合、阶段解析和外观状态聚合。没有人工标注答案时，它能评估格式与证据精度，不能证明召回率。下一步应基于多作品黄金集把该报告接入 22.9 的正式 `DecompositionQualityReport`，而不是针对示例作品增加专用规则。

---

[← 上一篇](21-retrieval-augmented-visual-enrichment.md) · [文档索引](README.md) · [下一篇 →](23-visual-first-extraction-refactor.md)
