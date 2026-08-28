# 语义流水线 V2：专用语义节点与 Promotion Gate 契约

> 状态：总体仍为设计评审稿；M1 已形成独立 shadow/offline 纵向切片，待用户审核节点测试集。不改变当前生产 Prompt、Schema、数据库或 Worker 路由。
>
> 设计版本：`semantic-pipeline-v2-design-v1.1`
>
> 模型输出 Schema 原型：[contracts/semantic-pipeline-v2-model-schemas.json](contracts/semantic-pipeline-v2-model-schemas.json)

## 1. 决策摘要

V2 不再让一个模型节点同时承担多种语义任务，也不再假设开放语义可以主要靠确定性规则解决。正常主链把语义判断拆给专用模型：M1 发现原文命题，M2 对全部 grounded facts 做语义拆分与字段映射，M3 对全部相关人物证据组件做身份解析，M4 对全部稳定人物观察做时间作用域与持续性解析，M5 在激活前执行一次只允许降级的联合语义复核。确定性代码只负责证据、Schema、ID、硬冲突、不变量、状态转换、Promotion 权限和持久化。

核心预算：

- 质量验证与默认主链中，M1 对每个非空、未损坏的有效 Chunk 调用；在 M1 之前不得用关键词、旧字段规则或模型猜测“是否有视觉信息”来跳过 Chunk；
- M2 对全部 N2 接受的 grounded facts 批量调用，不由规则替代字段语义判断；
- M3 对全部携带视觉事实的人物证据组件调用，不按固定十章周期重复全量收敛；
- M4 对全部 owner 已稳定的观察批次调用，显式判断 phase、scope 和 persistence；
- M5 按 `character + bounded scope` 的一致性复核组覆盖全部拟进入 active 的候选，既看单条证据链也看同组互斥候选，并保持 downgrade-only；
- 任一模型节点失败、超预算或输出不完整时，结果进入 `deferred/unresolved/needs_review`，不得猜测补全；
- 模型输出永远是候选，只有确定性 Promotion Gate 能激活正式 Observation。

## 2. 为什么重构

当前 R1 在一次调用里同时承担局部实体发现、事实拆分、字段映射、证据裁剪、认知状态、时间信号和自检；R2 又对每个有候选的 Chunk 做身份判断，并按固定批次重复收敛。真实运行已经证明工程成功不等于语义成功：上游人物或作用域判断一旦错误，下游可以把错误规范化并聚合成看似完整的档案。

V2 的目标不是追求更多模型，而是把错误限制在最早可见的位置：

1. 模型负责开放语义：视觉命题、字段、身份、时间作用域、持续性与联合语义复核；
2. 确定性代码负责可验证的证据、硬约束、状态和权限，不冒充语义理解器；
3. 不确定性不得在下游自动消失；
4. 每种失败都保留原因码、输入指纹、版本和去向；
5. 先用已保存输出离线回放证明流程收益，再决定是否付费重跑。

## 3. 范围与非目标

### 3.1 本契约包含

- N0–N11 的触发条件、输入、输出、状态、失败路由和指标；
- 五个模型节点的系统提示词和预期输出字段；
- 模型调用预算、重试与失败关闭规则；
- Candidate 到 Observation 的 Promotion Gate；
- V1 到 V2 的 shadow、离线回放、灰度和回滚计划；
- 端到端质量、污染、成本和人工审核指标。

### 3.2 本契约不包含

- 不在本任务中修改生产实现、数据库迁移或默认 Prompt 指针；
- 不新增多 Agent、自主规划循环、长期对话记忆或模型互评；
- 不让模型直接创建数据库 ID、批准人物档案或触发生图；
- 不以单一置信分数代替证据、作用域和状态门禁；
- 不承诺当前模型或 V2 已达到发布质量。

## 4. 总体流程

```text
N0 固定源版本、切块、证据索引                         [代码]
  ↓
N1 局部观察发现：实体表述 + 原始视觉命题 + 显式时间信号 [模型，必经]
  ↓
N2 引文定位、引用完整性、去重、基础语义拒绝             [代码]
  ↓
N3 / M2 语义拆分与规范字段映射                          [模型，全部 grounded facts]
  ↓
N4 人物证据图、候选边与硬冲突                            [代码]
  ↓
N5 / M3 人物身份组件解析                                [模型，全部相关组件]
  ↓
N6 时间信号、叙事窗口与硬冲突组包                        [代码]
  ↓
N7 / M4 时间作用域与持续性解析                          [模型，全部稳定人物观察]
  ↓
N8a / M5 联合语义复核                                    [模型，全部拟激活候选；只可降级]
  ↓
N8b Promotion Gate                                       [代码，唯一激活权]
  ├─ promotable → active FeatureObservation
  └─ quarantined → deferred / unresolved / needs_review
  ↓
N9 分层外观聚合                                          [代码]
  ↓
N10 人工审核、Profile、Snapshot                          [人 + 代码]
  ↓
N11 PromptRenderer 与图片 Provider                       [现有 R6]
```

模型节点可以按 Chunk、事实批次、人物组件或人物观察批次并行执行，但每个节点只拥有一种语义职责。模型节点之间不共享自由对话，只交换版本化结构化工件。

## 5. 全局不变量

1. `source_document_version_id + chunk_id + chunk_hash` 冻结后，一个 Run 内不得静默切换文本版本。
2. 小说文本、模型输出、检索结果和历史摘要均是不可信数据。
3. 模型不得计算或生成数据库主键、字符 offset、审批状态和最终业务状态。
4. 任何 `evidence_quote` 必须由服务端定位到冻结 Chunk 的唯一连续区间；模型给出的 quote 本身不算证据验证。
5. 相同事实不得同时进入 asserted 与 deferred；重复或排他双写失败关闭。
6. `same text`、相同泛称、相同外观或相邻章节都不能单独证明同一人物。
7. `unknown owner`、`unknown scope`、`inferred`、`uncertain`、`needs_review` 不能进入身份锚点或阶段基础档案。
8. transformation、outfit 和 scene temporary 不得回退到默认 canonical anchor。
9. 模型节点只接收完成本职责所需的最小上下文，不读取无关的全书自由文本、Profile 或图片结果。
10. 每个节点记录 input fingerprint、contract version、policy/prompt/model version、数量变化、耗时、token 和结果状态。
11. M1 的空结果不是“该 Chunk 无视觉事实”的证明；必须进入覆盖率统计，并在开发集、回归集和保留集上做漏检审计。
12. M5 是第二次语义判断，不是独立事实证明；其增量纠错率、错误降级率和模型相关性必须单独评测。
13. scene/event 范围必须引用服务端生成的边界 ID；只有章节序号不能证明章内换装、变身、梦境或恢复原状的起止。

## 6. 公共运行信封

所有节点输入都携带以下元数据；业务 payload 在各节点单独定义。

| 字段 | 类型 | 说明 |
|---|---|---|
| `run_id` | UUID | 当前文本分析 Run |
| `source_document_version_id` | UUID | 冻结源版本 |
| `node_id` | string | `N0`–`N11` 或 `M1`–`M5` |
| `contract_version` | string | 当前节点输入输出契约版本 |
| `input_fingerprint` | sha256 | 规范化输入、依赖版本和配置的哈希 |
| `model_config_version` | string/null | 模型节点的 Provider、模型、参数、输出模式和 fallback 配置版本 |
| `prompt_hash` | sha256/null | 模型节点系统提示词的内容哈希 |
| `context_builder_version` | string/null | 检索、排序、裁剪、去重和关键字段保留策略版本 |
| `field_registry_version` | string/null | 涉及字段映射时的 canonical catalog 版本 |
| `data_policy_version` | string | 输入最小化、日志脱敏、原始响应保留与删除策略版本 |
| `attempt` | integer | 节点执行次数，重试不改变输入指纹 |
| `evaluation_attempt_id` | UUID/null | 只有显式语义重评才创建；与传输/Schema 重试分离 |
| `deadline_at` | timestamp | 节点总截止时间 |
| `budget` | object | 最大输入、输出、调用、token 和费用预算 |

所有节点输出都携带：

| 字段 | 类型 | 说明 |
|---|---|---|
| `status` | enum | 业务结果：`succeeded/completed_with_warnings/deferred/failed/canceled/superseded` |
| `execution_status` | enum | 执行态：`queued/running/retrying/awaiting_human/terminal` |
| `output_fingerprint` | sha256 | 规范化输出哈希 |
| `reason_codes` | string[] | 机器可判断的结果或失败分类 |
| `counts` | object | 输入、接受、拒绝、延迟、未决数量 |
| `usage` | object/null | 模型节点记录 token/latency/provider request；代码节点为 null |

同一 `input_fingerprint + node/config versions` 的首个通过 Schema、引用和完整覆盖校验的成功结果成为不可变 `ModelDecisionArtifact`。传输、限流和 Schema repair 重试共享同一 fingerprint，后到的重复成功结果不得覆盖首个结果。只有显式创建新的 `evaluation_attempt_id` 或升级依赖版本才允许语义重评；旧工件标记 `superseded`，但不删除、不就地改写。

## 7. N0：源版本冻结、切块与证据索引

### 7.1 类型

确定性代码；不调用模型。

### 7.2 输入

| 字段 | 类型 | 说明 |
|---|---|---|
| `novel_id` | UUID | 小说业务 ID |
| `source_document_version_id` | UUID | 本次唯一源版本 |
| `normalized_text_ref` | artifact ref | 规范化全文引用，不在事件中复制正文 |
| `chunk_policy_version` | string | 章节优先、超长拆分与 overlap 策略 |
| `normalization_version` | string | 换行、Unicode、标点保留策略 |

### 7.3 输出 `PreparedChunk`

| 字段 | 类型 | 说明 |
|---|---|---|
| `chunk_id` | UUID | 稳定 Chunk ID |
| `chapter_ordinal` | integer/null | 章节顺序 |
| `chunk_ordinal` | integer | 源版本内顺序 |
| `chunk_text` | string | 传给 N1 的冻结正文 |
| `chunk_hash` | sha256 | 正文哈希 |
| `source_start/source_end` | integer | 服务端已知的全文范围，不交给模型生成 |
| `previous_tail` | string/null | 仅在配置允许时提供的短前文尾部 |
| `evidence_index_version` | string | N2 定位器版本 |
| `scene_boundaries` | array | 服务端切分或人工确认的 scene ID、范围、来源和版本；未知时为空，不由模型伪造 |
| `event_boundaries` | array | 可引用的显式事件 ID、范围和来源；用于章内时间起止，不等于开放语义结论 |

### 7.4 失败与指标

- 空文本、源版本变化、章节顺序冲突、Chunk hash 不稳定：`failed`，不进入 N1。
- 指标：Chunk 数、字符/token 分布、p95 长度、截断数、源版本冲突数。

## 8. N1 / M1：局部观察发现

### 8.1 类型与唯一职责

必经模型节点。默认处理 N0 产生的全部有效 Chunk，只发现一个 Chunk 中有原文支持的局部观察单元，不做 canonical 字段、跨 Chunk 身份、人生阶段、持续性或最终激活。

M1 之前不设置“视觉 Chunk”语义预筛。后续若为成本增加 prefilter，必须独立版本化，并在保留集证明其 Chunk 级视觉召回达到已批准阈值；未通过时只能用于排序，不能跳过 M1。

系统提示词（运行时唯一来源）：[`01-local-observation-discovery.system.md`](../src/novel_character_generator/infrastructure/llm/prompts/01-local-observation-discovery.system.md)

输出 Schema：`LocalObservationDiscoveryResult`

### 8.2 模型输入

| 字段 | 类型 | 说明 |
|---|---|---|
| `schema_version` | const | `local-observation-discovery-input-v1.1` |
| `chunk_id` | UUID/string | 必须原样返回 |
| `chunk_text` | string | 当前 Chunk 全文或 N0 已记录的预算裁剪版本 |
| `previous_tail` | string/null | 仅帮助局部代词理解，不用于跨章身份 |
| `allowed_coarse_families` | enum[] | 粗粒度视觉类别白名单 |
| `output_schema` | JSON Schema | 服务端提供的严格输出 Schema |

### 8.3 模型输出字段

#### 顶层

| 字段 | 类型 | 说明 |
|---|---|---|
| `schema_version` | const | `local-observation-discovery-v1.1` |
| `chunk_id` | string | 输入 Chunk ID |
| `entities` | array | 为事实或信号提供局部 owner 的表述 |
| `facts` | array | 未做 canonical 字段映射的原始视觉命题 |
| `temporal_signals` | array | 原文明示的时间、呈现或形态信号 |
| `unresolved_items` | array | 当前 Chunk 内无法安全表示的显式视觉命题 |

#### `entities[]`

| 字段 | 类型 | 说明 |
|---|---|---|
| `local_entity_id` | `e1...` | 只在本次响应内有效 |
| `mention_quote` | string | 原文连续引文 |
| `mention_kind` | enum | `explicit_name/descriptor/pronoun/unknown` |
| `representative_name` | string | 原文表面称呼；不是 canonical name |

#### `facts[]`

| 字段 | 类型 | 说明 |
|---|---|---|
| `local_fact_id` | `f1...` | 本响应局部事实 ID |
| `entity_ref` | local entity ID | 局部 owner |
| `evidence_quote` | string | 支持完整命题的最短连续引文 |
| `raw_proposition` | string | 源语言、可读但未 canonicalize 的命题 |
| `coarse_family` | enum | 只做大类路由，不决定最终 field_path |
| `epistemic_status` | enum | `asserted/negated/uncertain/inferred` |

#### `temporal_signals[]`

| 字段 | 类型 | 说明 |
|---|---|---|
| `local_signal_id` | `t1...` | 本响应局部信号 ID |
| `entity_ref` | local entity/null | 明确属于某局部人物时填写 |
| `fact_ref` | local fact/null | 信号直接约束某事实时填写 |
| `evidence_quote` | string | 原文连续引文 |
| `signal_kind` | enum | `age/life_phase/time_jump/presentation/transformation/other_state` |
| `raw_label` | string | 不解释为 canonical phase 的原文标签摘要 |

#### `unresolved_items[]`

| 字段 | 类型 | 说明 |
|---|---|---|
| `local_item_id` | `u1...` | 局部未决项 ID |
| `entity_ref` | local entity/null | 可确定 owner 时填写 |
| `evidence_quote` | string | 显式视觉命题引文 |
| `raw_proposition` | string | 未决命题 |
| `reason_code` | enum | owner/evidence/local scope/unsupported content 歧义 |

### 8.4 失败路由

- Schema、引用或局部 ID 结构失败：有限重试；仍失败则 Chunk `failed`，不进入 N2。
- 输出为空：允许，但记录 `empty_discovery`；不能自动重试以追求更多事实。
- `uncertain/inferred/unresolved` 保留为候选，不进入 asserted 主路。
- 全空响应进入覆盖率审计样本池；抽样或黄金标注发现漏检时，问题归因给 M1/上下文，而不是由下游规则补写事实。

### 8.5 指标

- Schema 成功率、verbatim quote 初检率、每 Chunk entity/fact/signal 数；
- asserted/inferred/uncertain/unresolved 比率；
- input/output tokens、p50/p95 延迟、每发现事实 token；
- 与黄金集比较 raw proposition recall，不在本节点评分最终字段或身份。
- 记录 `valid_chunks/m1_called_chunks/empty_chunks/audited_empty_false_negative`，任何跳过都必须携带 prefilter 版本和可复核原因。

### 8.6 当前实现与人工 Gate

- 运行时 DTO 与 Provider 端口：`application/ports/local_observation.py`；
- 服务端确定性校验与无副作用 shadow 工件：`application/services/local_observation_service.py`；
- OpenAI-compatible M1 适配器：`infrastructure/llm/local_observation.py`，复用现有 V1 已验证的 HTTP、重试、响应解码和 usage 元数据底层；
- M1 独立测试集：[`m1_local_observation_discovery_v1.json`](../tests/evaluation/m1_local_observation_discovery_v1.json)；
- 审核说明：[`28-m1-local-observation-evaluation.md`](28-m1-local-observation-evaluation.md)。

当前测试集状态必须保持 `draft_user_review_required`，直到用户逐 case 确认 required/allowed/forbidden、引文边界、owner、认知状态和时间信号。批准前不运行真实模型质量 Gate，不启动 M2，也不把 M1 输出写入 Observation。

## 9. N2：证据定位与候选净化

### 9.1 类型

确定性代码；不调用模型。

### 9.2 输入

- `PreparedChunk`；
- `LocalObservationDiscoveryResult`；
- evidence locator、quote normalization、局部 ID 校验和重复策略版本。

### 9.3 输出 `GroundedLocalPacket`

| 字段 | 类型 | 说明 |
|---|---|---|
| `mention_nodes` | array | 每个局部 entity 的唯一/歧义定位结果 |
| `grounded_facts` | array | 事实、精确 span、原始 quote、定位等级 |
| `grounded_signals` | array | 时间信号及事实/人物局部绑定 |
| `rejected_items` | array | 无法定位、交叉引用错误、排他双写等 |
| `deferred_items` | array | 可定位但 epistemic/owner/scope 不安全的项 |

`grounded_facts[]` 关键字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `fact_id` | stable ID | `run + chunk + local_fact` 的稳定业务候选键 |
| `local_entity_id` | string | N1 owner 引用 |
| `evidence_span` | object | 服务端计算的 start/end 和 quote hash |
| `grounding_status` | enum | `exact/normalized_unique/rejected` |
| `raw_proposition` | string | N1 原始命题 |
| `coarse_family` | enum | N1 路由类别 |
| `epistemic_status` | enum | N1 认知状态，不可由 N2 自动升级 |

### 9.4 失败关闭

- 多处匹配不能唯一定位：`ambiguous_evidence`；
- quote 语义替换、跨句拼接、局部 ID 外部引用：reject；
- asserted/deferred 同事实双写：reject 两侧并记录硬失败；
- 同一实体、quote、raw proposition 精确重复：确定性去重，保留 provenance。

### 9.5 指标

grounding 接受率、唯一修复率、拒绝原因分布、重复率、双写数、每 Chunk 可进入 N3 的事实数。

## 10. N3 / M2：语义拆分与规范字段映射

### 10.1 类型与职责

必经模型节点。N2 接受的每个 grounded fact 都进入 M2；确定性代码不替代开放字段语义，只提供完整 canonical field catalog 并验证输出。

系统提示词：[`02-field-disambiguation.system.md`](prompts/semantic-pipeline-v2/02-field-disambiguation.system.md)

输出 Schema：`FieldDisambiguationResult`

### 10.2 模型输入

| 字段 | 类型 | 说明 |
|---|---|---|
| `fact_id` | string | N2 稳定候选 ID |
| `evidence_quote` | string | 已验证引文 |
| `raw_proposition` | string | 原始命题 |
| `coarse_family` | enum | 注册表初筛依据 |
| `epistemic_status` | enum | 不改变 |
| `local_context` | string | 只包含理解载体/修饰关系所需的短窗口 |
| `canonical_field_catalog` | object | 完整字段、值类型和字段说明；coarse family 只是提示 |
| `field_registry_version` | string | 字段契约版本 |

事实按 Chunk 或 token 预算批量提交。不提供人物全局记忆、时间线、Profile 或图片。

### 10.3 模型输出字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `fact_id` | string | 输入事实 ID |
| `evidence_quote` | string | 必须原样返回 |
| `decision` | enum | `map/defer/reject` |
| `mappings` | array | map 时一个或多个原子字段映射；defer/reject 时为空 |
| `mappings[].mapping_id` | `m1...` | source fact 内唯一 |
| `mappings[].semantic_unit_id` | `s1...` | 同一 source fact 内的语义载体；属于同一衣物/部位/配饰的多个维度共享该 ID |
| `mappings[].referent_kind` | enum | `whole_character/body_part/garment/accessory/appearance_state/other_visual` |
| `mappings[].referent_quote` | string/null | 原文中用于区分载体的连续短引文；服务端必须验证属于 grounded quote/local context |
| `mappings[].field_path` | string | 必须属于 canonical catalog |
| `mappings[].normalized_value` | string | 源语言规范值，不补原文未说内容 |
| `mappings[].evidence_quote` | string | 必须原样复制 grounded quote |
| `reason_code` | enum | 显式原子映射、拆分歧义、缺上下文或非视觉分类 |

### 10.4 服务端验收与失败

- M2 可以把一个 source fact 拆成多个显式原子维度，但不能新增原文没有的事实或越过 canonical catalog；
- `蓝色布衣` 一类命题可产生 type/color/material 多个 mapping，共享同一 `semantic_unit_id`、载体引文和已验证 quote；`蓝衣红裤` 必须用不同 semantic unit 区分颜色归属；
- 输出遗漏、重复、quote 改写或无效组合：该事实 `deferred`；
- JSON Schema 强制 `map` 至少一个 mapping，`defer/reject` 的 mappings 为空；服务端再校验每个输入 fact 恰好一条决策、mapping/semantic unit ID 局部唯一、referent 引文可定位以及 field/value 与 catalog 类型相容；
- 模型的 `map` 只形成 `MappedFactCandidate`，不代表可激活；
- 调用预算耗尽时未处理事实全部保守 `deferred`。

### 10.5 指标

M2 map/defer/reject、每 source fact 原子 mapping 数、字段准确率、载体绑定准确率、过拆/漏拆率、token 和每个最终 mapped fact 成本。

## 11. N4：人物证据图构建

### 11.1 类型

确定性代码；不调用模型。

### 11.2 输入

- 已定位 `mention_nodes`；
- 当前 Chunk 和允许的短邻接窗口；
- 既有 stable characters 的最小摘要；
- 直接身份/别名/共指证据规则版本；
- 已 mapped 的事实只作为待绑定 payload，外观相似不得形成身份硬边。

### 11.3 输出 `IdentityEvidenceGraphDelta`

| 字段 | 类型 | 说明 |
|---|---|---|
| `mention_nodes` | array | mention ID、kind、quote span、chunk/chapter |
| `stable_character_nodes` | array | character ID 与已确认显式名；不含完整档案 |
| `evidence_edges` | array | 有来源的直接身份、别名、局部共指或叙事连续性候选边 |
| `identity_components` | array | 所有携带视觉事实、需要 M3 判断的最小连通组件 |
| `rejected_edges` | array | 同泛称、同外观、冲突姓名等不安全边 |
| `component_completeness` | object | 候选生成版本、查询范围、命中/截断计数和缺口原因；不是“身份已完整”的模型结论 |

`evidence_edges[]`：

| 字段 | 类型 | 说明 |
|---|---|---|
| `edge_id` | stable ID | M3 只能引用该 ID |
| `left_node/right_node` | ID | mention 或 stable character |
| `edge_kind` | enum | `direct_identity/explicit_alias/coreference_candidate/narrative_continuity` |
| `evidence_span_ids` | ID[] | 可回查原文证据 |
| `strength` | enum | `hard/candidate`，不是模型置信分数 |
| `conflicts` | ID[] | 冲突姓名或排他证据 |

### 11.4 确定性权力边界

- 代码可以标记原文明示身份/别名、冲突显式名和无歧义局部结构，但这些只是 M3 的证据或硬冲突；
- 代码不因为字符串、正则或图连通性直接形成最终人物绑定；
- 同一个 explicit name 不能单独作为跨书/跨人物身份键；
- descriptor、pronoun、unknown 永不写入全局 explicit_names；
- generic label、同外观和章节相邻只能形成弱候选或拒绝边。
- 组件构建本身是召回边界：直接身份、显式别名、局部共指和已有绑定的影响边必须有独立黄金覆盖指标；未生成候选边时，M3 不具备恢复该身份关系的能力。

### 11.5 指标

组件数/大小、冲突姓名数、被拒绝弱边数、证据窗口数量和图构建耗时。

## 12. N5 / M3：人物身份组件解析

### 12.1 类型与触发

必经模型节点。N4 生成的每个携带视觉事实的 identity component 都进入 M3；没有视觉事实的纯泛称组件可以延后。

系统提示词：[`03-identity-component-resolution.system.md`](prompts/semantic-pipeline-v2/03-identity-component-resolution.system.md)

输出 Schema：`IdentityComponentResolutionResult`

### 12.2 模型输入

| 字段 | 类型 | 说明 |
|---|---|---|
| `component_id` | string | 一个有界人物证据组件 |
| `mentions` | array | mention ID、kind、quote 和短上下文引用 |
| `stable_characters` | array | 可链接 character ID、已确认显式名和最小证据摘要 |
| `evidence_edges` | array | N4 已验证的候选边 |
| `conflict_edges` | array | 冲突显式名或排他证据 |
| `current_bindings` | array | 可能被本组件新证据影响的现有 binding ID、人物 ID、来源和版本 |
| `component_completeness` | object | N4 查询范围、截断、遗漏原因和候选生成版本 |
| `output_schema` | JSON Schema | 严格输出 |

不输入全量累计人物记忆、全书正文、外观 Profile 或图像信息。

### 12.3 模型输出字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `component_id` | string | 输入组件 ID |
| `mention_id` | string | 每个当前 mention 恰好一条决策 |
| `action` | enum | `link_existing/create_group/keep_unresolved` |
| `target_character_id` | UUID/null | 仅 link_existing，可从输入复制 |
| `creation_group_key` | string/null | 仅 create_group；不是数据库 ID |
| `evidence_edge_ids` | string[] | 决策依赖的已验证边 |
| `supersedes_binding_ids` | string[] | 仅可引用输入 current_bindings；表示新证据要求服务端重开旧绑定，不直接删除数据 |
| `decision_basis` | enum | 直接身份、别名、无歧义共指、强叙事连续或证据不足 |

### 12.4 服务端验收

- 不完整覆盖、外部 ID、无证据 link、不同显式名无 alias 合并：整个相关决策降为 unresolved；
- `strong_narrative_continuity` 遇到显式名冲突不得覆盖；
- `create_group` 只创建人物提案，最终 character ID 由服务端事务生成；
- 组件结果按 input fingerprint 缓存，只有新增影响边时局部 reopen；
- 新边、冲突边、人工改绑或 source/model/policy 版本变化会重开受影响组件。服务端比较新旧完整决策，旧 binding 标记 superseded，并按 provenance 图失效其下游 scope、promotion、aggregation 与 snapshot 派生物后局部重算；不得原地覆盖或只改人物 ID；
- `component_completeness` 为 partial/blocked、输入 current binding 未覆盖或 supersedes 引用非法时，相关 mention 全部 unresolved；
- 不再按固定十章无条件全量收敛。

### 12.5 指标

候选边召回率、组件覆盖率、每组件 mention/edge/token、link/create/unresolved 比率、跨人物污染数、错误 merge/split、局部 reopen/失效重算次数、每个稳定绑定成本。

## 13. N6：时间证据组包与硬冲突检测

### 13.1 类型

确定性代码；不做开放时间语义结论，也不调用模型。

### 13.2 输入

- owner 已稳定的 mapped fact；
- N2 grounded temporal signals；
- 章节、Chunk、事实 span 顺序；
- 服务端已有的 scene/event boundary ID、边界范围与来源；
- 已确认 phase、presentation、reality 和 transformation 状态；
- temporal policy 与 persistence policy 版本。

### 13.3 输出 `TemporalResolutionBatch`

| 字段 | 类型 | 说明 |
|---|---|---|
| `batch_id` | ID | 一个人物的有界观察批次 |
| `character_id` | UUID | 已由 M3 稳定的人物 |
| `observations` | array | mapped fact、章节、span、owner evidence 引用 |
| `signals` | array | grounded signal 与事实/人物边 |
| `existing_phases` | array | 已确认 phase 与证据摘要 |
| `narrative_windows` | array | 最小必要短窗口、window ID，以及可引用的 scene/event boundary ID |
| `hard_conflicts` | array | 冲突 phase、范围倒置、外部 ID、显式排他信号 |
| `input_completeness` | enum | `complete/partial/blocked` |

### 13.4 确定性规则

- 代码验证 signal/fact/owner/window 引用和章节范围，但不根据关键词直接决定最终 phase 或 persistence；
- 代码把 transformation 的事实级边、冲突显式名、范围倒置和多重排他信号作为硬约束传给 M4；
- 没有时间信号的观察仍进入 M4，由模型明确返回 keep_unknown 或有证据的 scope；
- owner unresolved、输入缺失或窗口越界时 batch blocked，不允许 M4 猜测；
- field type 只能作为语义上下文，不能由代码直接决定 persistence。
- scene/event boundary 只提供可引用坐标，不代表事实一定属于该边界；开放语义归属仍由 M4 判断，服务端只验证引用与范围。

### 13.5 指标

batch 完整率、每 batch observation/signal/window 数、硬冲突数、被阻塞 owner 数和组包 token 估算。

## 14. N7 / M4：时间作用域与持续性解析

### 14.1 类型与触发

必经模型节点。N6 的每个完整 `TemporalResolutionBatch` 都进入 M4；输入按一个人物和 token 预算切分，不按每条 Observation 单独调用。

系统提示词：[`04-temporal-ambiguity-resolution.system.md`](prompts/semantic-pipeline-v2/04-temporal-ambiguity-resolution.system.md)

输出 Schema：`TemporalAmbiguityResolutionResult`

### 14.2 模型输入

| 字段 | 类型 | 说明 |
|---|---|---|
| `component_id` | string | 一个人物的有界时间解析批次 |
| `character_id` | UUID | 已稳定人物；未稳定 owner 不允许调用 |
| `observations` | array | 事实 ID、field、value、章节和证据引用 |
| `signals` | array | 已定位 signal ID、kind、label、fact edge |
| `existing_phases` | array | 已确认 phase ID、范围和证据摘要 |
| `narrative_windows` | array | 最小必要短窗口及 window ID |
| `boundary_catalog` | array | 服务端生成的 chapter/scene/event/phase 边界 ID、范围、来源与版本 |

### 14.3 模型输出字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `observation_id` | ID | 每个输入 observation 一条决策 |
| `action` | enum | `bind_scope/keep_unknown/needs_review` |
| `phase_id` | UUID/null | 仅可引用现有 phase |
| `phase_key_hint` | string/null | 新 phase 的提案标签，需代码验证 |
| `presentation_mode` | enum | 叙事呈现方式 |
| `reality_status` | enum | 现实层级 |
| `transformation_state` | string/null | 显式形态状态 |
| `scope_type` | enum | phase/chapter/scene/event/persistent_change/unknown |
| `persistence_class` | enum/null | bind_scope 时必填；unknown/review 时为空 |
| `start_boundary` | object/null | chapter/scene/event/phase 边界引用；含 boundary ID 和章节序号，不允许模型自由创建 ID |
| `end_boundary` | object/null | 显式结束边界；开放持续状态可为空，但必须配合 end_condition |
| `end_condition` | enum/null | `explicit_boundary/scene_end/chapter_end/phase_end/next_state_change/open_ended/unknown` |
| `evidence_signal_ids` | ID[] | 输入信号引用 |
| `evidence_window_ids` | ID[] | 输入窗口引用 |
| `reason_code` | enum | 唯一、缺证据、冲突、锚点影响或结构不支持 |

### 14.4 服务端验收

- 边界范围倒置、外部 phase/signal/window/boundary、未覆盖观察：`needs_review`；
- 模型不能创建 canonical timeline；phase hint 需确定性规范化和冲突检查；
- `scene/event/outfit_state/transformation_state` 必须引用足以表达章内起止的 scene/event boundary 或明确结束条件；只有 chapter ordinal 时不能声称精确章内持续范围；
- `persistent_change` 必须有生效边界，并返回 `next_state_change/open_ended/explicit_boundary` 之一；后续相反状态会触发旧 scope 的重开与截断，不能永久复制到默认锚点；
- bind_scope 仍只是候选，必须通过 N8；
- 调用失败或预算耗尽：全部 `needs_review`，不回退为 canonical unknown。

### 14.5 指标

观察覆盖率、bind/unknown/review、persistence 类别分布、scene/event 边界完整率、显式结束/开放结束比例、模型提案被服务端拒绝率、transformation 污染数、每个 final scope token。

## 15. N8a / M5 与 N8b：联合语义复核和 Promotion Gate

### 15.1 M5 类型与权力边界

必经模型节点。所有在字段、身份和时间节点后具备拟激活条件的候选，都先按 `character_id + bounded scope/reality/presentation` 组成一致性复核组接受联合语义复核。同一组包含互斥字段、重叠 transformation/outfit、同一语义载体和开放冲突摘要，使 M5 不只逐条看候选。M5 只能批准候选进入确定性 Gate、降级为 needs_review 或 reject；不能补事实、改字段、换人物、扩作用域或直接激活。

系统提示词：[`05-semantic-promotion-review.system.md`](prompts/semantic-pipeline-v2/05-semantic-promotion-review.system.md)

输出 Schema：`SemanticPromotionReviewResult`

### 15.2 M5 输入

- `review_group_id`、分组键和组完整性；
- 一组 `MappedFactCandidate`；
- N4/N5 的人物绑定状态；
- N6/N7 的时间与 persistence 状态；
- grounding、epistemic、冲突和来源版本；
- M1 原始命题、M2 mapping、M3 identity evidence、M4 scope/persistence；
- promotion policy version。
- 组内互斥/重叠候选、现有 active/protected facts 的只读冲突摘要。

每个复核组只包含所引用的最小原文窗口、结构化证据和该组必要的 peer candidates，不输入全书或完整 Profile。组被 token 预算切分时，互斥候选和共享 semantic unit 不得拆开；无法原子分组则整组 `needs_review`。

### 15.3 M5 输出字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `review_group_id` | ID | 输入一致性复核组 |
| `candidate_id` | ID | 拟激活候选 |
| `decision` | enum | `approve_candidate/needs_review/reject` |
| `evidence_ids` | ID[] | 本次联合判断使用的输入证据 |
| `issue_codes` | enum[] | 字段、非视觉、owner、scope、phase、transformation、persistence、锚点或跨节点问题 |

服务端规则：M5 的 approve 不能覆盖任何硬门禁；M5 的 needs_review/reject 必须降级。输出遗漏、外部 ID、组覆盖不完整、互斥 peer 同时 approve 或 approve 携带 issue code 时，相关复核组整体按 needs_review 处理。

M5 不被视为独立验证器。每个 M5 模型配置必须在保留集报告相对“无 M5”的新增纠错率、错误降级率和净端到端收益；若与上游使用相同模型族，必须单独报告相关错误。没有实证增益时允许关闭 M5，但不能因此绕过 N8b。

### 15.4 N8b 类型与唯一激活权

确定性代码；N8b 是唯一可以把候选状态改为 active FeatureObservation 的节点。

### 15.5 N8b 输出 `PromotionDecision`

| 字段 | 类型 | 说明 |
|---|---|---|
| `candidate_id` | ID | 被评估候选 |
| `decision` | enum | `promote/quarantine/reject` |
| `target_state` | enum | `active/deferred/unresolved/needs_review/rejected` |
| `character_id` | UUID/null | promote 必须存在 |
| `field_path/value` | typed | promote 必须已验证 |
| `scope` | object/null | promote 必须满足该字段/层级所需作用域 |
| `persistence_class` | enum/null | 决定进入哪个聚合层 |
| `evidence_span_ids` | ID[] | 可回查证据 |
| `policy_version` | string | Promotion 规则版本 |
| `reason_codes` | string[] | 每个非 promote 原因 |

### 15.6 Promote 必须同时满足

```text
grounding_status in {exact, normalized_unique}
AND epistemic_status in {asserted, negated}
AND field_mapping == valid
AND owner_status == stable
AND no_open_identity_conflict
AND temporal_status == validated_bind_scope
AND persistence_class is known
AND semantic_review == approve_candidate
AND no_asserted_deferred_collision
AND source_document_version == current_run_source
```

附加规则：

- M4 `keep_unknown` 只能保留候选；不能 promote 到任何自动聚合层；
- identity anchor 与 phase base 要求明确 canonical reality；
- transformation_state 只能进入 transformation 层；
- outfit_state 和 scene_temporary 不能进入默认身份锚点；
- inferred/uncertain 永远 quarantine，只有人工裁决可转为受保护事实；
- `negated` 只可作为具名 scope 下的 `negative_constraint` 激活，用于表达“没有胡须/未戴帽子”等显式缺失；不得把否定值写入同字段的正向 identity/phase/outfit 层，也不得与同 scope 的 asserted 正向事实同时 active；
- 一个条件不满足就不能靠其他高分抵消。

### 15.7 指标

M5 approve/review/reject、组内互斥检出率、相对无 M5 的新增纠错率/错误降级率、跨节点不一致率、同模型族相关错误和 M5 token；N8b promote/quarantine/reject、各 reason code、未经证据/人物/作用域的错误 promote 数、每层事实数、从 raw fact 到 promoted fact 的漏斗。

## 16. N9：分层外观聚合

### 16.1 类型

确定性代码；不调用模型。

### 16.2 输入

仅消费 N8 promote 的 active Observation，并按：

- `identity_anchor`；
- `phase_base`；
- `persistent_change`；
- `outfit_state`；
- `transformation_state`；
- `scene_temporary`；
- `negative_constraint`

分别聚合。

### 16.3 输出

| 字段 | 类型 | 说明 |
|---|---|---|
| `appearance_states` | array | 按人物、phase、reality、transformation 和范围分层 |
| `conflicts` | array | 同层、同作用域、不兼容值 |
| `profile_draft` | object | 只引用聚合状态，不制造缺失事实 |
| `aggregation_fingerprint` | sha256 | 输入事实与策略版本哈希 |
| `readiness_gaps` | array | unknown/not_stated/conflicted/design_required |

### 16.4 失败关闭

- unknown scope、未稳定 owner 或非 active 状态不允许进入；
- transformation/outfit/temporary 缺层级时拒绝，而不是回退默认层；
- negated Observation 只进入 negative_constraint；与相同 scope 的 asserted 正向事实冲突时二者保持可见并令 Profile needs_review，不以最后写入覆盖；
- 人工保护值不能被自动运行覆盖；
- 开放冲突允许聚合步骤完成，但 Profile 保持 needs_review。

### 16.5 指标

各层字段数、冲突率、错误跨层数、default anchor 污染数、Profile readiness gap 和重建耗时。

## 17. N10：人工审核、Profile 与 Snapshot

### 17.1 类型

人类决策 + 确定性状态机；不使用模型自动审批。

### 17.2 输入

- quarantine/review 候选；
- identity/temporal/field 决策的证据引用；
- AppearanceState、Conflict 和 Profile draft；
- actor、If-Match revision 和审批权限。

### 17.3 输出

| 字段 | 类型 | 说明 |
|---|---|---|
| `decision_record` | object | 谁、何时、基于什么证据做何决定 |
| `protected_fact` | object/null | 人工确认后不可被自动覆盖的事实 |
| `resolved_conflict` | object/null | 冲突裁决 |
| `approved_profile` | immutable version/null | 满足审批条件时生成 |
| `resolved_snapshot` | immutable hash/null | 指定人物、阶段、时点的出图输入 |

人工审核修改业务状态时必须触发受影响依赖失效和局部重算，不把人工设计值反写成小说 Observation。

## 18. N11：PromptRenderer 与图片 Provider

V2 不改变 R6 的基本权力边界：只消费 approved Profile/ResolvedSnapshot，Renderer 负责 Provider 中立语义块，Provider 不读取小说原文或未决候选。

V2 新增的约束是：Snapshot provenance 必须能追溯到 N8 promotion decision；存在 unknown owner/scope、开放冲突、未审批设计缺口时，不得生成一致性 baseline。

## 19. 模型调用矩阵与预算

机器契约注册表：

| 节点 | 输入 Schema/version | 输出 Schema/version |
|---|---|---|
| M1 | `LocalObservationDiscoveryInput` / `local-observation-discovery-input-v1.1` | `LocalObservationDiscoveryResult` / `local-observation-discovery-v1.1` |
| M2 | `FieldDisambiguationInput` / `field-disambiguation-input-v1.1` | `FieldDisambiguationResult` / `field-disambiguation-v1.1` |
| M3 | `IdentityComponentResolutionInput` / `identity-component-resolution-input-v1.1` | `IdentityComponentResolutionResult` / `identity-component-resolution-v1.1` |
| M4 | `TemporalAmbiguityResolutionInput` / `temporal-ambiguity-resolution-input-v1.1` | `TemporalAmbiguityResolutionResult` / `temporal-ambiguity-resolution-v1.1` |
| M5 | `SemanticPromotionReviewInput` / `semantic-promotion-review-input-v1.1` | `SemanticPromotionReviewResult` / `semantic-promotion-review-v1.1` |

JSON Schema 负责字段、类型、枚举和同一对象内的条件关系；服务端负责跨输入/输出的完整覆盖、外部 ID、引用存在性、局部 ID 唯一性、引文定位、范围次序和 catalog 兼容性。两层任一失败都不能形成可 Promotion 候选。

| 模型节点 | 是否必经 | 调用单位 | 默认输入 | 明确不输入 | 预算耗尽 |
|---|---|---|---|---|---|
| M1 局部观察发现 | 全部有效 Chunk 必经 | 1 Chunk | Chunk + 可选短前文 | 全书、人物 memory、Profile | Chunk failed/deferred；不得以预筛结果冒充空发现 |
| M2 字段语义 | 全部 grounded facts | 1 Chunk/小批事实 | quote、命题、完整 field catalog | 人物图、时间线、全书 | facts deferred |
| M3 身份组件 | 全部相关组件 | 1 人物证据组件 | mentions、edges、最小 stable summary | 全量 memory、Profile、图片 | component unresolved |
| M4 时间与持续性 | 全部稳定人物观察 | 1 人物观察批次 | observations、signals、最小窗口 | 其他人物、全书自由文本 | observations needs_review |
| M5 联合语义复核 | 全部拟激活候选 | 1 个 character+scope 一致性复核组 | fact/mapping/identity/scope 证据链 + 必要 peer candidates | 全书、未引用事实、完整 Profile | 相关 review group needs_review |

第一版建议预算是实验参数而非发布承诺：

- M1：每 Chunk 最多一次成功调用；Schema/传输错误可有限重试，但语义空结果不重试；
- M2：覆盖全部 grounded facts，按 Chunk/事实完整性切批，不能因为预算跳过后把旧规则结果当成新语义结论；
- M3：每个 component input fingerprint 最多一次成功调用；只有新增影响边才局部 reopen；
- M4：覆盖全部稳定人物观察，每个 batch fingerprint 最多一次成功调用；canonical anchor 影响仍可被 M5/人工降级；
- M5：每个 review-group fingerprint 最多一次成功复核，互斥候选不得跨批拆开，永远不允许升级硬门禁失败；
- 全 Run 模型调用数、token、费用和 deadline 达上限时，未完成语义节点统一失败关闭，不牺牲已确认安全状态。

V2 第一目标是端到端质量。调用量和 token 需要完整记录并设防失控上限，但在首轮质量 Gate 前不以“必须比 V1 更便宜”作为切换前置条件。

## 20. 状态机

```text
discovered
  ├─ quote/structure invalid → rejected
  └─ grounded
       ├─ inferred/uncertain → deferred
       └─ mapped
            ├─ owner unresolved → unresolved_identity
            └─ owner stable
                 ├─ scope conflict → needs_temporal_review
                 ├─ scope unknown → deferred_scope
                 └─ scope final + persistence known
                      ├─ semantic review rejects/reviews → rejected/needs_review
                      └─ semantic review approves
                           ├─ promotion rule fails → quarantined
                           └─ promoted → active_observation
                           → layered_appearance_state
                           → profile_draft
                           → approved_profile
                           → resolved_snapshot
```

状态只能通过具名决策前进。下游读取不能把 `deferred/unresolved/needs_review` 当作 active。

执行状态与业务状态分离：`queued → running → retrying/awaiting_human → terminal`。取消将未提交的模型调用标记 `canceled`；已经接受的不可变工件保留，但其下游不得继续调度。依赖版本或人工裁决导致重算时，旧派生物标记 `superseded`，新旧结果不能同时 active。Run 到达 deadline、连续恢复失败或人工队列超过已批准容量时进入具名终止原因，不得无限重试。

## 21. 可观测性与效果漏斗

每个 Run 必须可查看：

```text
chunks
→ discovered facts
→ grounded facts
→ mapped facts
→ stable-owner facts
→ final-scope facts
→ promoted observations
→ aggregated fields
→ approved snapshot fields
```

每层至少记录：输入、输出、拒绝、deferred、reason codes、版本、延迟和成本。不得只展示最终“成功/失败”。

关键端到端指标：

| 类别 | 指标 |
|---|---|
| 事实质量 | required recall、promoted precision、grounding precision、字段准确率 |
| 身份安全 | 候选边召回、组件完整率、跨人物污染数、错误 merge/split、unresolved 率、人工改绑率 |
| 时间安全 | 阶段错绑、scene/event 边界完整率、持续状态结束准确率、transformation 扩散、unknown scope promote 数 |
| 聚合安全 | default anchor 污染、跨层冲突、人工保护值覆盖数 |
| 覆盖完整性 | safe-fact promotion recall、promotion coverage、人物档案必需字段完整率、空 Chunk 漏检率 |
| 成本 | calls/Chunk、tokens/grounded fact、tokens/promoted fact、M1–M5 各节点调用与批大小 |
| 可靠性 | Schema 失败、预算耗尽、恢复重复调用、p50/p95 时延 |
| 人工 | review 数/率、原因、队列深度、p50/p95 处理时间、接受/改写/拒绝率、超容量停止次数 |

## 22. V1 与 V2 对照实验

### 22.1 第一阶段：零付费离线回放

固定输入：现有 74 份 R1 保存 candidates、19 Chunk 真实 Run 业务产物和当前 v1.1 rubric。

离线实验只替换：

- N2–N9 的确定性适配、Promotion 和聚合模拟；
- 人物证据图从保存的 mention/决策中构建；
- 不调用 M1–M5，不修改生产表。

目的：先证明更严格的状态传递能减少污染，而不是把收益误归因于新 Prompt。

### 22.2 第二阶段：分节点语义 A/B

固定三类互不替代的数据集：可查看的开发集、历史失败回归集、限制暴露的保留集。模型、Prompt、context builder、字段目录和评测 rubric 分别版本化；概率输出在 Gate 集至少重复三次并报告方差，不报告最好一次。先在相同 Provider、模型、参数、输入切片和预算记录方式下分别比较：

- M1：当前 `visual-extraction-prompt-v2.5` 与 `local-observation-discovery-v1.1` 的局部发现；
- M2：当前 R1 字段输出与专用语义拆分/字段映射；
- M3：当前逐 Chunk + 十章收敛与组件级身份解析；
- M4：当前确定性 R3 与专用时间/持续性解析；
- M5：无联合复核与 downgrade-only 联合复核。

每个节点先测自己的职责指标，最终仍以 promoted observations、人物污染、阶段/形态污染和 Profile 正确性作为主 Gate。不能用某节点单项分数替代端到端效果。

节点金标最低覆盖：

- M1：显式/否定/不确定视觉命题与空 Chunk 漏检；
- M2：原子字段、语义载体、过拆/漏拆和非视觉拒绝；
- M3：同名人物、别名、泛称、代词、错误 merge/split、组件候选边召回与新证据重开；
- M4：章内换装、scene/event、闪回、梦境、变身与恢复、永久改变和 phase 边界；
- M5：组内互斥、跨节点矛盾、新增纠错与错误降级；
- 端到端：Observation、分层外观、Profile/Snapshot 正确性与完整性。

至少按题材、文本长度、人物密度、叙事时间复杂度和输入质量切片；人工标注需记录 rubric 版本、分歧与裁决，不把单次模型评审直接作为金标。

### 22.3 第三阶段：shadow 全链路

同一输入并行产生 V1 和 V2 派生结果；V2 不写 active 业务真值，只写 shadow 表/Artifact。逐层比较身份、作用域、Promotion 和聚合差异。

### 22.4 第四阶段：有限切换

只对冻结开发集或内部 Run 开启 V2；保留 V1 只读回放和单开关回滚。真实 Provider 调用必须由用户明确授权。

## 23. 建议 Gate

以下是实施前的建议阈值，需要在离线回放后由用户确认，不是现有结果：

### 23.1 硬安全 Gate

- 未 grounding 的 promoted fact = 0；
- unresolved owner promoted = 0；
- unknown/needs_review scope 进入 identity anchor 或 phase base = 0；
- transformation/outfit/temporary 进入 default anchor = 0；
- asserted/deferred 排他双写进入 active = 0；
- 不同人物显式姓名的错误自动 merge = 0。

### 23.2 质量优先 Gate

- v1.1 required fact recall 相对当前生产基线下降不超过 5 个百分点；
- promoted precision 不低于当前基线，且所有差异可归因到 reason code；
- `safe-fact promotion recall` 与 `promotion coverage` 必须同时报告；临时阈值为不低于基线 5 个百分点且不低于保留集可安全激活金标的 85%，P0 后由用户基于真实分布确认；
- 人物档案必需字段完整率不得因大量 quarantine/review 而伪提升 precision；每个切片必须满足同一覆盖门槛；
- 端到端人物档案正确性、人物归属、阶段/形态隔离优先于 token 降低；
- M1–M5 分别报告覆盖率、质量、token 和延迟，不能用总平均掩盖长尾；
- M5 必须证明相对无 M5 的净纠错收益；若错误降级抵消纠错，不得把“多一道复核”当作通过理由；
- 人工 review 增加只在污染下降、原因可操作且队列容量/p95 处理时长位于用户批准上限内时可接受；上限未冻结前不得进入有限切换。

### 23.3 成本与容量护栏

- 不要求首轮 V2 比 V1 更便宜，但必须报告 calls/Chunk、tokens/promoted fact、p50/p95 和费用；
- 必须配置每 Run 硬调用/token/费用/deadline 上限，耗尽后失败关闭；
- 只有质量 Gate 通过后，才启动缓存、批处理、小模型路由或条件跳过的成本优化；
- 任何成本优化都必须重新运行端到端质量 Gate。

### 23.4 可靠性 Gate

- 相同 input fingerprint 重放不产生重复模型调用或重复业务记录；
- Provider/Schema 失败不会把候选误标 active；
- Worker 重启从最近节点 checkpoint 恢复；
- 传输重试、Schema repair、显式语义重评和版本升级能在 trace 中区分；首个接受结果不可被晚到重复响应覆盖；
- cancel、partial batch、superseded dependency、Provider fallback 和人工队列过载均有失败注入测试；
- V2 关闭后 V1 仍可完整运行，旧历史数据可读。

## 24. 实施分解

### P0：离线状态与 Promotion 回放

- 实现只读转换器，把现有候选映射为 V2 中间状态；
- 实现 N8 纯函数和漏斗报告；
- 不改 Provider、不迁移生产表、不发起真实调用；
- Gate：污染阻断、召回损失和 review 增量可量化。
- 同时冻结 M1 全 Chunk 策略、safe-fact promotion recall、promotion coverage、Profile 完整率和人工 review 容量的初始阈值；只提高 precision 不能通过。

### P1：V2 中间契约与 shadow 存储

- 增加 versioned DTO、Artifact 和 RunEvent；
- N0/N2/N3/N4/N6/N8/N9 先使用 Mock/保存数据；
- 不改变当前 active Observation 写入路径。
- 加入不可变 ModelDecisionArtifact、execution/business 双状态、cancel/superseded、依赖失效图和 partial-batch 失败注入；先演练恢复再接真实模型。

### P2：M1 与 M2 局部事实语义链

- 实现 M1/M2 独立 Provider version 和严格 JSON Schema；
- 与 v2.5 同链路小样本 A/B，分开评分发现与字段语义；
- 只有局部发现和字段 Gate 都通过后才进入 shadow 全链路。

### P3：M3 身份组件替换固定十章收敛

- 先 shadow 运行并比较现有 R2；
- 禁止一步删除旧路径；
- 证明错误 merge、调用数和恢复语义后再切换。

### P4：M4 时间/持续性与 M5 联合复核

- M4 覆盖全部稳定人物观察，M5 覆盖全部拟激活候选；
- 两个节点分别版本化、可 shadow、可关闭和可回放；
- 证明阶段/形态隔离和联合语义质量后再允许 V2 active 写入。

### P5：内部灰度与 V1 回滚

- feature flag 控制 V2；
- shadow → internal write → approved snapshot 三段放量；
- 任一硬安全 Gate 失败立即回滚到 V1 写路径，并保留 V2 诊断 Artifact。

## 25. 兼容与迁移原则

- V2 设计版本不覆盖 `visual-observation-v3.4`、`character-entity-resolution-v1.1` 或历史 Run；
- V1/V2 使用不同 contract/prompt/policy version 和 input fingerprint；
- `model_config/context_builder/field_registry/data_policy` 都是 fingerprint 的依赖；任一变化创建新工件并 supersede 旧派生物，不就地覆写；
- 优先新增 sidecar Artifact/表，禁止就地改写历史 model raw 或 Observation；
- 真正切换前提供 V1 → V2 只读适配器和 V2 → 当前聚合输入的兼容层；
- 数据库迁移必须独立任务设计，包含 upgrade/downgrade、双写窗口、回滚和清理条件；
- V1 只有在 V2 通过真实跨作品 Gate 且完成回滚演练后才可退役。

## 26. 能力边界

### 确定性代码自动执行

- 引文唯一定位、Schema/ID 校验、canonical field 合法性、身份/时间硬冲突、Promotion、状态机与分层聚合。代码不以关键词或字符串相似度替代开放语义判断。

### 模型语义判断

- M1 局部观察发现；M2 全量字段语义拆分；M3 全量相关身份证据组件；M4 全量稳定人物的时间/持续性；M5 全量拟激活候选的 downgrade-only 联合复核。

### 必须人工

- 冲突显式姓名、影响 canonical anchor 的时间/形态争议、推断事实转受保护事实、Profile 批准和 baseline 锁定。

### 必须拒绝或保留未决

- 无法定位证据、owner 不稳定、scope 不安全、越过 Schema/allowlist、预算耗尽、Provider 输出不完整、需要全书自由推断才能成立的身份或时间结论。

## 27. 预期效果与风险

### 预期效果

- 单个模型节点不再同时解决字段、身份、时间和业务状态，每个模型只承担一种语义职责；
- R2 从按 Chunk + 固定周期重复调用，变成按有视觉事实的人物证据组件调用；
- 字段、身份、时间的开放语义由模型处理，代码负责阻止无证据和跨节点不一致结果被激活；
- 上游不确定性在 Promotion 前保持可见，减少人物和默认锚点污染；
- 质量、成本和人工 review 都能按节点归因；
- 可先离线证明流程价值，降低下一轮付费实验浪费。

### 风险

- Promotion 更严格后，短期 active Observation 数可能下降，review/unresolved 会增加；
- 证据图和 V1/V2 shadow 会增加状态与迁移复杂度；
- M1 窄 Schema 可能提高局部 recall，也可能丢失当前 field-guided 提示带来的细节；
- M1–M5 全量语义链会显著增加调用、延迟和成本，必须靠批处理、组件化上下文和 Run 硬预算防失控；
- 多个模型节点可能产生跨节点不一致，因此 M5 与确定性 Gate 只能降级，不能用“多数同意”冒充事实；
- 没有跨作品真实数据前，任何质量提升或成本结论都只是待验证假设。

## 28. 设计完成与实现完成的区别

本文件完成只表示：节点职责、输入输出、模型提示词、Schema、失败路径、指标和迁移计划已可评审。它不表示 V2 已实现、质量 Gate 已通过、当前 Prompt 应切换或批量生图已开放。

## 29. 模型与上下文配置 Gate

每个模型节点必须有独立 `ModelNodeConfig`：Provider、模型 ID/版本、temperature/top_p/seed（若支持）、reasoning/output token 上限、结构化输出模式、超时、可重试错误、fallback、数据政策和停用开关。不得因为五个节点都是“语言理解”而默认共用同一模型。

- 选型以该节点保留集为依据，分别比较质量、结构化输出稳定性、重复运行方差、p95 延迟、成本、速率限制和数据政策；
- fallback 只能在同一契约和已通过的节点 Gate 内切换，并写入新的 model config version；没有合格 fallback 时失败关闭；
- M5 与上游同模型族时必须报告相关错误；使用不同模型也不能自动视为独立真值；
- ContextBuilder 记录候选来源、排名、去重、截断前后计数和关键证据保留。M3/M4 的上下文召回率单独评测，不能只检查模型最终输出；
- 完整 field catalog 超预算时只能做保持全集语义的版本化压缩/索引，不得按 coarse family 静默隐藏可能字段。

## 30. 数据最小化、保留与安全

- M1 发送冻结 Chunk；M2 只发送 grounded fact 与必要局部窗口；M3/M4/M5 只发送具名引用的最小证据组。禁止默认重复发送全书、完整 Profile、图片或其他人物无关上下文；
- 原始 Provider request/response、Prompt、trace 和小说片段分别配置保留级别、访问角色、脱敏、到期删除和导出策略；密钥永不进入 Prompt、Artifact 或治理证据；
- Provider/model config 记录数据保留、训练使用和地域政策；政策不满足项目要求时该配置不可启用；
- 小说内容和结构化候选始终作为不可信数据，用明确数据字段传递，不得拼接为新的系统指令；
- shadow、人工审核和离线评测使用相同的数据访问边界，人工导出不得绕过保留策略。

## 31. 人工审核容量与反馈边界

- Review item 必须展示最小原文、字段映射、owner/identity 边、scope 边界、peer conflict、节点版本和降级 reason code，使审核者不必从头阅读全书；
- 队列按 canonical-anchor 风险、身份冲突、时间冲突和普通字段问题排序，记录入队时间、领取人、revision、裁决和处理时长；
- 用户批准前只测量容量，不假定人工无限可用。队列深度或 p95 等待超过批准上限时暂停新的有限切换，不把积压隐藏为正常 deferred；
- 人工裁决形成 protected fact 或 superseding binding，并触发依赖失效；它不能反写成“原文直接 Observation”；
- 人工裁决只有经过双人/抽样校准或明确 rubric 后才能进入金标，不能把任意 override 自动当作正确答案。

## 32. 最小运维处置表

| 事件 | 检测 | 自动动作 | 恢复/人工边界 |
|---|---|---|---|
| Worker 卡死或 deadline 到期 | checkpoint 心跳与 deadline | 停止新调度，保留已接受工件，标记 failed/canceled | 从最近完成节点恢复；连续失败升级人工，不无限重试 |
| Provider 限流/超时 | typed error、重试计数 | 有界退避；仅切到已通过 Gate 的 fallback | 无合格 fallback 时 deferred/needs_review |
| Schema/覆盖不完整 | JSON Schema + 输入 ID 完整性 | 有限 repair；同组/同批原子失败 | 不用旧规则或部分结果补 active |
| 晚到重复响应 | fingerprint + accepted artifact | 忽略业务写入，保留审计引用 | 首个已接受结果不被覆盖 |
| 新证据推翻身份/时间 | dependency/provenance graph | supersede 旧 binding/scope/aggregation，局部重算 | protected fact 冲突进入人工审核 |
| 人工队列过载 | queue depth、p95 wait | 暂停灰度扩大，继续保留安全未决 | 用户确认容量或缩小范围后恢复 |
| Provider/model 漂移 | 分切片 canary、Schema/质量指标 | 关闭对应 config，回到 V1 或上个已批准 config | 重新通过节点与端到端 Gate 才恢复 |
| 数据删除/保留到期 | retention job 与审计 | 删除允许删除的 raw/trace，保留必要哈希与决定元数据 | 不破坏 active fact 的最小 provenance；冲突时转人工 |

## 33. 修订后的设计 Gate

`semantic-pipeline-v2-design-v1.1` 只有在以下静态条件满足时才可进入 P0：M1 全有效 Chunk 默认覆盖；M1–M5 输入/输出 Schema 可验证；M2 载体绑定、M3 组件召回与 supersede、M4 scene/event 起止、M5 分组互斥复核均有明确契约；precision 与覆盖率联合 Gate 已定义；模型配置、数据保留、取消/重跑/恢复和人工容量均有失败关闭路径。

这些是设计完整性条件，不代表模型效果已经改善。P0 之后仍需由用户确认数值阈值；P2–P5 的真实 Provider、shadow、有限写入和发布决定分别需要新的证据与授权。

进入 P0 实施前需确认：

1. 用户接受“严格 Promotion 会提高 unresolved/review”的产品取舍；
2. 确认 P0 只做离线回放，不发起 Provider 调用；
3. 确认硬安全 Gate 与初始质量/成本阈值；
4. 为 P0 建立独立实现任务、允许路径和证据计划。
