# 视觉优先的出图字段与全文抽取重构方案

> [← 上一篇](22-general-novel-decomposition-quality-plan.md) · [文档索引](README.md) · [下一篇 →](01-project-overview-and-principles.md)
>
> 文档版本：2.0 · 修订日期：2026-08-26
>
> 当前状态：**目标设计、待分阶段实施和多作品评测**。本文同时定义“真正出图需要什么”和“小说抽取怎样为这些字段提供有证据的输入”。当前已实现的是 Observation、外观聚合、人工档案与 Mock 生成基础链路；角色设计补全、场景简报、Prompt 编译和稳定出图门禁仍未形成闭环，现状以[当前实现状态](00-current-status.md)为准。

## 23.1 先用一句话说明我们要做什么

我们不是要让模型一次读完一段小说后，把人物、代词、别名、外貌、表情、场景、时间线和关系全部判断完；也不是要让抽取模型把小说没有写出的镜头、画风和服装细节补成“事实”。

我们真正要完成的是：

```text
真实出图需求
  → 可提取字段目录与来源分类
  → 有证据的小说视觉事实
  → 人物、人生阶段和持续性解析
  → 目标时点事实快照
  → 人工批准的角色设计补全
  → 场景渲染简报
  → Provider 中立的渲染规格
  → Provider 请求与一致性审计
```

因此，全文扫描阶段应优先回答“原文写了谁、长什么样、证据在哪里、在什么时候有效”，而不是同时建立完整人物关系图、替用户做造型设计或直接拼最终 Prompt。

## 23.2 为什么现在要改

### 23.2.1 当前调用实际要求模型做什么

当前 `ChunkExtractionResult` 在一次调用中要求八类结果：

1. `mentions`：名字、称谓、亲属称谓和代词；
2. `alias_hypotheses`：别名候选；
3. `observations`：人物事实和视觉事实；
4. `expression_observations`：神情与内外情绪；
5. `scene_hypotheses`：场景范围；
6. `timeline_hypotheses`：时间线候选；
7. `relations`：人物关系；
8. `unresolved_references`：未解析指代。

每条结果还要求模型给出零基 `start/end`。这意味着模型既要理解小说，又要做实体识别、共指、视觉分类、时间推理、关系归一化、字符计数和严格 JSON 生成。

### 23.2.2 本次真实诊断说明了什么

2026-08-25 的单作品诊断只用于发现问题，不代表完整评测结论。样例中每块正文约 2,040 个汉字，前两个成功块出现了以下结果：

| 指标 | 结果 |
|---|---:|
| 两块 prompt tokens | 6,466 |
| 两块 completion tokens | 95,545 |
| 归一化结果条数 | 137 |
| 平均每条结果 completion tokens | 约 697 |
| 两个成功请求延迟 | 约 210 秒、398 秒 |
| 第三个请求 | 约 243 秒后断流 |
| exact grounding rate | 55.47% |
| grounded rate（含 fuzzy） | 99.27% |

原始响应显示，大部分 completion 消耗来自模型推理内容，而不是最终 JSON。第三块发生 `RemoteProtocolError: incomplete chunked read`。

这说明主要瓶颈不是正文放不进上下文，而是一次请求承担了过多互相耦合的判断。Schema 过长会增加负担，但只压缩 Schema 不能解决八类任务同时推理的问题。

诊断结果还有三个重要信号：

- 第 2 个成功块产生了 76 条 mention，其中大量是重复名字和代词；
- 模型为整块文本生成一个大场景，场景粒度没有真正帮助视觉状态定位；
- 模型把“前世”作为 canonical timeline 候选，而它更可能是人生阶段或回忆语义，不应由块级模型直接建成独立时间线。

### 23.2.3 当前代码中的成本和正确性空档

1. `response_format={"type":"json_object"}` 只约束 JSON，不替项目校验完整 Pydantic Schema；Schema 仍以大段文本发送。
2. 请求没有显式控制 thinking/reasoning；按 DeepSeek 当前官方行为，`deepseek-v4-flash` 默认开启 thinking，默认 reasoning effort 为 `high`。
3. 请求没有最大 completion token，推理可能持续数万 tokens。
4. `temperature=0` 不能代替推理预算；DeepSeek thinking 模式下 temperature 不产生控制效果。
5. `httpx` timeout 是网络操作超时，不是严格的整次墙钟截止时间；持续接收数据时总耗时可以超过配置值。
6. 所有结果数组都有空列表默认值，`{}` 也能成为技术上有效的结果。
7. `unresolved_references` 和模型 `warnings` 当前不进入生产持久化，却占用每次调用的理解和输出预算。
8. 非视觉字段会被保存，但外观聚合只消费视觉字段；这部分模型工作不会直接改善一期角色出图。
9. Provider usage、reasoning/output tokens、finish reason 和请求延迟目前主要由本地检查器保存，生产 Run 尚未形成完整成本记录。

### 23.2.4 外部实践核验

本节记录 2026-08-25 对官方仓库、官方文档和原始论文的核验结果。外部项目只能验证架构方向和常见风险，不能证明本项目 v3 已达到发布质量。

| 外部实践 | 已核验做法 | 对本项目的含义 |
|---|---|---|
| [Microsoft GraphRAG](https://microsoft.github.io/graphrag/index/architecture/) | 先把文档切成 TextUnit，再逐块抽取实体和关系，随后全局合并；chunk token 数、overlap 和 workflow 可配置 | 保留“分块发现、全局收敛”，但 chunk 应按 token、章节边界和验证集调节，不冻结为固定汉字数 |
| [GraphRAG Dataflow](https://microsoft.github.io/graphrag/index/default_dataflow/) | 每个 TextUnit 产生局部子图，再合并同名同类型实体和同源目标关系 | 块级结果应是候选，不应直接成为全书最终 Character/Relation |
| [GraphRAG Methods](https://microsoft.github.io/graphrag/index/methods/) | 标准模式质量高但成本高；Fast 模式以 NLP 替代部分 LLM 工作，便宜但更嘈杂；claim extraction 可选 | 混合确定性/NLP/LLM 是有效降本方向，但任何替代都必须通过视觉质量门禁 |
| [BookNLP](https://github.com/booknlp/booknlp) | entity、quote、event、coref 等是可选择模块；先做人物姓名聚类，再谨慎做代词共指；全量共指容易错误合并人物 | 支持拆分实体发现与全书解析，也支持不穷举全部代词；但 BookNLP 主要面向英文，不能直接证明中文小说效果 |
| [DocRED](https://aclanthology.org/P19-1074/) | 文档级关系抽取基于实体 mention 集合、共享 entity ID 和支持证据句 | 跨句关系应视为专项问题；关系必须绑定稳定实体与证据，不应只依赖自由文本人物名 |
| [OneKE](https://github.com/zjunlp/OneKE) / [DeepKE](https://github.com/zjunlp/DeepKE) | 中英双语、Schema-guided；NER、RE、Event、Triple 等作为不同任务和可组合能力；长文本建议较直接的抽取模式以降低注意力分散与时间 | 支持使用任务相关小 Schema 和能力开关，不支持把全部小说理解任务长期塞进同一主调用 |
| [NuExtract](https://github.com/numindai/nuextract) | 使用文档加专用 JSON 模板，并支持逐字返回 `verbatim-string` | 支持“模型返回原文证据，程序负责定位和规范化”的分工 |

外部实践同时给出一个反例：GraphRAG 标准模式会在同一 TextUnit 中联合抽取实体和关系。因此“所有任务都必须拆成独立调用”不是通用定律。本项目将关系改为条件执行，是因为一期产品目标是证据化角色视觉档案，而不是完整知识图谱；若未来把完整人物关系图列为核心产品，则应建立独立、可评测的文档级关系流水线。

目前没有找到一个成熟开源项目能够直接完成“中文长篇小说 → 人物身份收敛 → 人生阶段外观 → 证据审核 → 阶段形象生成”的完整链路。因此本文方案是多个已验证模式的组合设计，仍需本项目黄金集证明端到端效果。

### 23.2.5 外部核验后的修正结论

1. 每块约 2,000 汉字不是本次失控的首要原因，但固定字符数分块仍需改成 token/自然边界/overlap 可配置。
2. Schema 文本较大确实增加任务复杂度，但诊断中的 prompt 大量命中缓存；95,545 completion tokens 才是更直接的成本和时延来源。
3. 按当前 DeepSeek API 语义，代码未显式关闭 thinking，很可能让结构化抽取使用默认 `high` reasoning；该推断与原始响应中大规模 reasoning 内容一致。
4. 因此实施顺序必须先治理 Provider，再判断 v3 Schema 本身带来的收益，避免把“关闭失控推理”的改善错误归因于“视觉优先”。
5. 服务端 offset 是工程推断，不是外部项目给出的绝对结论；它必须配合唯一证据短句、前后锚点和歧义门禁。

## 23.3 先理解五个不同的问题

这些问题相关，但不能让同一个模型在同一时刻全部解决。

### 23.3.1 找到证据

原文有没有写“黑色短发”“古铜色皮肤”“左眉有疤”？这是视觉事实发现。

### 23.3.2 确认属于谁

“男孩”“他”“小三”“唐三”是否指同一个人物？这是实体链接与局部共指。

### 23.3.3 确认属于什么时候

该描述属于前世、转生幼年、成年后，还是梦境或伪装？这是人生阶段与时间定位。

### 23.3.4 整理成可用状态

多条证据是否能合并，还是代表变化或冲突？这是确定性外观聚合。

### 23.3.5 决定能不能出图

证据是否完整，冲突是否解决，档案是否人工批准？这是质量门禁和渲染决策。

当前问题在于：23.3.1 到 23.3.3 被塞进一次块级调用，而 23.3.4 和 23.3.5 又缺少对前面结果完整性的正式评价。

## 23.4 出图目标、字段分层与抽取桥梁

### 23.4.1 真正被生图流程消费的不是一袋 Observation

可复用的人物图通常至少需要六个可独立控制的 Prompt/工作流块：

| 块 | 回答的问题 | 典型内容 |
|---|---|---|
| 角色身份 | 画的是谁，哪些特征跨图不能漂移 | 人物 ID、外观类型、脸部锚点、固有标记、基准图 |
| 目标阶段外观 | 这个时间点长什么样 | 年龄/年龄阶段、体型、肤色、发型、长期伤势、阶段性变化 |
| 当前造型 | 这一次穿戴什么 | 服装分件、颜色/材质、配饰、发饰、武器或手持物 |
| 表演与场景 | 这一帧在做什么、在哪里 | 姿势、动作、视线、可见表情、环境、时间、天气 |
| 美术与镜头 | 图要怎样呈现 | 媒介、画风、构图、景别、视角、灯光、色彩、背景复杂度 |
| 一致性与排除 | 哪些内容必须保持或不得混入 | 阶段基准图、姿态参考、错误年龄/旧服装/其他角色等负向约束 |

小说全文抽取只能可靠提供这些块中的一部分。把其余字段也塞进抽取 Schema，只会迫使模型猜测；把所有内容都留到最终 Prompt 临时发挥，又无法审核和复现。

### 23.4.2 六类来源必须分开保存

每个进入生成的字段都必须有 `source_kind`，不能只保存最终字符串：

| `source_kind` | 含义 | 能否写入小说事实层 |
|---|---|---|
| `novel_asserted` | 原文直接陈述且证据、人物、阶段均可定位 | 可以 |
| `novel_inferred` | 基于原文的推断或不确定候选 | 不可以；只进入审核建议 |
| `human_decision` | 用户明确选择或补全的角色设计 | 不可以；进入已批准设计层 |
| `approved_suggestion` | 系统/Agent 给出的非事实方案，经用户批准 | 不可以；进入已批准设计层 |
| `workflow_default` | 画风、镜头、质量和 Provider 工作流默认值 | 不可以；只进入场景简报或渲染规格 |
| `reference_asset` | 已批准基准图、姿态图、遮罩、ControlNet 等资产 | 不可以；作为生成约束引用 |

同一个最终 Prompt 可以同时包含原文事实和人工设计，但审计时必须能反向区分。例如“黑色短发”可以来自小说，“蓝色束腰童装”可以是用户批准的设计；二者不能都显示为“原著设定”。

### 23.4.3 字段目录按消费目的分层

字段注册表不应是一张无限扩张的扁平白名单。目标目录分为四个领域：

1. `character_appearance`：可跨场景复用的人物外观，包括 `subject.*`、`age`、`age_stage`、`body.*`、`skin.*`、`face.*`、`eyes.*`、`hair.*`、`facial_hair.*`、`distinctive_marks.*`、`injuries.*`、`clothing.*`、`accessories.*`、`disguise.*`、`cleanliness`。
2. `scene_performance`：只服务目标画面的瞬时信息，包括 `pose.*`、`action.*`、`gaze.*`、`expression.visible_*`、`held_objects.*` 和 `temporary_conditions.*`。
3. `scene_environment`：地点、时段、天气、环境物件和原文明确的光照；它属于场景，不进入角色基础外观。
4. `art_direction`：媒介、画风、构图、景别、视角、镜头、设计性灯光、调色、宽高比和质量参数；它不是小说事实，默认由用户、模板或 Visual Director 提供。

`subject.presentation` 只能由“男孩、中年女子”等直接文本或人工决定产生，不能根据姓名、代词、职业自行推断。`clothing` 应逐步从单一 `style` 演进为可选的分件结构，例如上装、下装、鞋靴、外层、头饰、主色、辅色和材质；原文只写“衣服朴素”时，不得自动补成具体款式。

### 23.4.4 出图字段如何匹配提取方法

| 出图所需内容 | 首选来源 | 获取方法 | 小说没写时怎样处理 |
|---|---|---|---|
| 人物身份、别名、外观类型 | 全文事实 | 候选实体发现 → 小说级实体收敛；类别只接受直接证据 | 保持 unknown，必要时人工确认 |
| 年龄、人生阶段、前世/转生/变身 | 全文事实 | `TemporalSignal` → 人生阶段 resolver → 绑定 Observation | 标记阶段歧义，禁止跨阶段借值 |
| 脸、眼、发、体型、肤色 | 全文事实 | 视觉候选发现 → 证据定位 → 人物/阶段绑定；有明确缺口时检索增强 | 结束检索后记为 `not_stated`，转为设计缺口 |
| 伤势、标记、伪装、清洁度 | 全文事实 | 同上，并由持续性 resolver 判断作用区间 | 未提及不等于“没有”；不得生成否定事实 |
| 当前服装与配饰 | 全文或目标场景事实 | 全文抽取阶段性造型；出图前按目标场景窄抽取瞬时换装 | 转为待批准的造型设计，不从职业猜衣服 |
| 姿势、动作、视线、可见表情、手持物 | 目标场景事实 | 用户选定场景后按需抽取，不在全文主调用中穷举 | 由用户/Visual Director 决定，标记为设计指令 |
| 地点、时段、天气、环境物件 | 故事场景事实 | 场景/事件解析或目标段落按需抽取 | 可选人工场景设计 |
| 画风、构图、镜头、灯光设计、调色 | 设计决策 | 用户选择、版本化模板或 Visual Director | 使用显式工作流默认；不回写 Observation |
| 负向约束 | 确定性派生 + 设计 | 从非目标阶段、冲突值、用户排除项和工作流安全规则编译 | 只生成可证明或用户明确要求的排除项 |
| 身份/姿态/结构参考图 | 资产 | 人工锁定的阶段基准图或受控参考资产 | 首轮概念图可为空；一致性量产前应补齐 |
| Provider 参数与语法 | Provider 契约 | `ImageRenderSpec` 编译器/Adapter | 不污染上游领域模型 |

桥梁的核心不是“抽更多字段”，而是为每个下游字段明确：它能否从小说得到、在哪一步得到、证据如何绑定、缺失时由谁决定。

### 23.4.5 聚合之后还需要一组分层产物

```text
FeatureObservation（小说事实）
  → ResolvedAppearanceFacts（指定时间点成立的事实视图）
  → CharacterRenderProfile（事实状态 + 已批准的角色设计决定）
  → ResolvedCharacterSnapshot（指定时间点的已批准角色快照）
  → SceneRenderBrief（本次姿势、表情、场景、美术与镜头）
  → ImageRenderSpec（Provider 中立的正向块、负向块、参考资产和输出参数）
  → Provider Adapter Request
```

- `ResolvedAppearanceFacts` 是聚合器对小说事实的只读结果，可作为 Profile 草稿输入；它不包含设计补全。
- `CharacterRenderProfile` 是人工批准的可复用角色设计档案；它可以补小说未写的服装配色或造型细节，但每个字段保留来源，不伪装成原著事实。
- `ResolvedCharacterSnapshot` 从已批准 Profile 中解析指定时间点的人物外观与可选场景人物状态；它可以包含已批准设计，但不填充画风默认值。
- `SceneRenderBrief` 描述“这张图”；同一个角色档案可用于角色正视设定图、动作场景或环境肖像。
- `ImageRenderSpec` 是编译结果，不是业务真值。它按 Provider 能力生成结构化 Prompt 块、负向 Prompt、参考图/权重、seed、尺寸和工作流参数。

这样一来，抽取 Schema 不需要知道某个 Provider 喜欢怎样写 Prompt，Provider Adapter 也不需要重新解释小说。

### 23.4.6 缺失、明确无、冲突和设计缺口不是一回事

至少区分四种状态：

| 状态 | 含义 | 后续动作 |
|---|---|---|
| `unknown` | 尚未搜索或作用域不明确 | 继续解析或检索 |
| `not_stated` | 已达到证据覆盖预算，小说未找到描述 | 停止反复检索，进入设计缺口 |
| `explicitly_absent` | 原文明说“没有胡须/没有伤疤”等 | 作为 `negated` 证据保存，可编译为约束 |
| `conflicted` | 同一有效作用域存在不兼容值 | 人工解决，不能用默认值掩盖 |

设计缺口也要结构化，例如：`field_path`、`importance`、`reason=not_stated`、允许的候选、是否阻断角色设定图、审批记录。系统可以提出方案，但只有 `human_decision` 或 `approved_suggestion` 能进入已批准角色设计。

### 23.4.7 抽取质量与出图就绪度分开报告

`DecompositionQualityReport` 只评价证据发现、人物归属、阶段解析和字段冲突，`ready` 仅表示可以进入人工档案确认。另建 `RenderReadinessReport`：

| 标志 | 成立条件 | 允许做什么 |
|---|---|---|
| `concept_ready` | 目标人物/阶段可解析，有至少一组有证据的核心视觉锚点，缺口和冲突已显式列出 | 生成探索性概念候选，不宣称稳定角色 |
| `character_design_ready` | 关键身份、阶段基础外观和默认造型已经人工批准，无阻断冲突 | 生成并选择角色设定图/阶段基准图 |
| `consistent_scene_ready` | 上述条件成立，且本次 `SceneRenderBrief`、负向约束、工作流和所需参考资产均已冻结 | 进入可审计的一致性场景生成 |

证据少不必永远禁止出图；它应阻止系统把猜测伪装成原著事实，并迫使产品明确“这是探索候选还是已批准设计”。

### 23.4.8 唐三幼年样例怎样穿过这座桥

以当前测试文本中的“转生幼年、清晨上山”时点为例，事实层可以稳定形成：

```text
人物：唐三
阶段：reincarnated_childhood / 转生幼年
原文事实：五、六岁；男孩；瘦小；健康小麦色皮肤；黑色短发；衣服朴素且干净
场景瞬时事实：清晨山顶；坐姿；注视东方；修炼时眼眸短暂出现淡淡紫意
```

它仍缺少脸型、常态瞳色、五官细节、衣服具体分件/颜色/材质、鞋、发饰等。系统应把这些列为设计缺口，而不是让抽取模型补出“蓝色劲装、棕色腰带”等常见同人印象。用户批准一套造型后，角色档案才可以成为 `character_design_ready`。

若生成“清晨山顶修炼”画面，`SceneRenderBrief` 再加入坐姿、视线、日出环境、构图与画风；若生成角色正视设定图，则不应把“紫色眼眸”永久写入身份锚点。两张图共享同一个幼年 Profile，但使用不同场景简报和瞬时状态。

## 23.5 抽取侧目标流程：一块小说会经历什么

目标流程如下：

```text
normalize_and_chunk
  → extract_visual_candidates
  → locate_evidence_spans
  → resolve_entities
  → resolve_character_phases
  → bind_observations
  → identify_evidence_gaps
  → enrich_visual_evidence（条件执行）
  → optional_relation_extraction
  → aggregate_appearance
  → evaluate_decomposition_quality
  → identify_design_gaps
```

这里仍坚持“一块一次主要调用”，但这次主要调用只完成角色视觉主链需要的候选发现。专项步骤不是默认执行“块 × 角色”调用。

### 23.5.1 调度频率不是“每块都重算全书”

人物收敛和人生阶段解析采用分层调度。`batch` 优先等于一个自然章节；章节过大时按版本化 `resolver_batch_max_chunks` 拆分，不能把固定批量数字硬编码为领域语义。

| 时机 | 实体处理 | 阶段/故事时间处理 | 是否调用全书 LLM | 产物状态 |
|---|---|---|---|---|
| 每个 Chunk 候选落库后 | 用姓名、已确认别名和局部互斥规则做低成本 local link | 只保存 `TemporalSignal`，允许绑定明显局部年龄/场景信号 | 否；只有块级视觉候选调用 | `local/provisional` |
| 每章或每批 Chunk 完成 | 合并本批候选，更新别名和待审核实体提案 | 结合已解析人物、章节顺序和邻批信号形成 provisional phase/scope | 默认否；歧义项才条件调用 Agent/模型 | `provisional` |
| 首次全文候选扫描完成 | 对全书候选索引做一次最终收敛和高影响重复检查 | 对全书时间信号、阶段顺序、回忆/梦境/分支和变身边界做一次最终解析 | 不发送整本原文；resolver 读取结构化候选摘要和证据引用 | `final/needs_review` |
| 新增章节或源版本局部变化 | 只处理新增候选及受影响人物闭包 | 只重算受影响人物、阶段边界和相邻事件窗口 | 否 | 新 resolver revision |
| 人工合并/拆分人物或修正阶段后 | 重绑受影响 mention/Observation | 重算受影响人物的 scope，不重抽无关 Chunk | 否 | 新 revision + 审计记录 |
| 每次准备出图 | 不重新收敛人物 | 确定性解析目标 timeline/event/scene 的有效状态 | 否 | `ResolvedCharacterSnapshot` |

“全文最终解析”表示对全书范围的结构化候选图做一致性检查，不表示把整本小说再次发送给模型。长篇任务中间可以展示 provisional 结果，但只有 `final` 或已人工确认的实体/阶段才能进入自动外观聚合和角色档案审批。

### 23.5.2 失效与重算边界

每个解析产物保存 `input_fingerprint`、resolver version、source document version 和依赖 ID。变更通过依赖图决定最小重算范围：

```text
新 Chunk
  → 新候选 + 可能命中的已有角色
  → 相关 TemporalSignal/阶段边界
  → 相关 Observation 绑定
  → 相关角色外观聚合与质量报告

人物合并/拆分
  → 相关 mention/candidate/Observation
  → 相关人物阶段
  → 相关 Profile 草稿和质量报告

阶段人工修正
  → 相关 Observation scope
  → 相关 AppearanceState/Snapshot
  → 质量报告和出图依赖失效
```

若无法安全计算最小闭包，允许回退为“整角色保守重算”，但仍不默认重调全文抽取 Provider。每次回退必须记录 reason code，便于后续优化。

### 第 0 步：规范化和分块

输入是 TXT 原文，输出是章节和 `TextChunk`。

这一层继续由确定性代码完成：

- 规范换行和 Unicode；
- 保存原文与规范化文本的偏移映射；
- 优先按章、段落和句子切分；
- 保存 chunk hash；
- 不把多个章节拼成一个语义块。

分块大小不是这次问题的唯一根因。即使约 2K 字符的块，八类联合任务仍产生了数万 completion tokens。因此应先缩小任务，再通过评测选择 1K–3K 或其他块大小。

### 第 1 步：视觉候选发现

这是每个块唯一必需的主要 LLM 调用。它只回答：

- 当前块有哪些值得保留的人物候选；
- 有哪些直接或明确不确定的视觉事实；
- 哪些局部时间词可能影响这些视觉事实的作用域。

它不再要求：

- 穷举每一个“他、她、我”；
- 为整块创建场景名称；
- 直接创建小说级 timeline；
- 抽取所有人物关系；
- 抽取职业、能力和一般行为；
- 逐字符计算所有 offset。

建议的候选契约：

```python
class VisualEntityCandidate(BaseModel):
    local_id: str
    representative_name: str
    mention_quote: str
    mention_kind: Literal[
        "explicit_name", "descriptor", "pronoun", "unknown"
    ]
    confidence: float


class VisualTemporalSignal(BaseModel):
    kind: Literal[
        "age", "life_phase", "time_jump", "presentation", "transformation"
    ]
    label: str
    evidence_quote: str


class VisualFactCandidate(BaseModel):
    entity_ref: str
    field_path: str
    value: JsonValue
    evidence_quote: str
    epistemic_status: Literal[
        "asserted", "negated", "inferred", "uncertain"
    ]
    confidence: float
    temporal_signals: list[VisualTemporalSignal]


class VisualDeferredCandidate(BaseModel):
    reason_code: Literal[
        "ambiguous_entity", "ambiguous_evidence",
        "uncertain_scope", "unsupported_visual_field",
        "inferred_visual_fact", "uncertain_visual_fact"
    ]
    evidence_quote: str | None
    detail: str | None


class VisualCandidateExtractionResult(BaseModel):
    entities: list[VisualEntityCandidate]
    visual_candidates: list[VisualFactCandidate]
    deferred_items: list[VisualDeferredCandidate]
```

`local_id` 只在当前块内使用，例如 `c1`、`c2`。视觉候选引用 `entity_ref`，避免模型在每条结果里重复生成自由文本人物名，也防止 Repository 因拼写变化创建新人物。

`explicit_name` 只表示原文明确出现的人名；少女、少年、老者、青年、称谓和亲属称呼统一属于 `descriptor`。代词只有在承载有效视觉候选或时间信号时才保留为 `pronoun`，无法安全分类时使用 `unknown`。历史 `name/title/kinship/disguise/nickname` 输入在边界层保守归一化，但只有 `explicit_name` 能进入 R2 的 `explicit_names`。

### 第 2 步：代码定位证据区间

模型只需要抄写足够完整的 `evidence_quote`，offset 由代码计算。

定位顺序固定为：原文精确匹配；忽略空格和软标点的唯一匹配；仅修复一个被遗漏的低信息字符且候选位置唯一。多位置、语义替换或跨句硬标点均失败关闭。接受修复时仍保存原文中的精确片段，并在候选包 warning 中记录 `normalized` 或 `repaired` 类型。

字段门禁只允许规范 `age`/`age_stage`，`age.age` 和 `age.age_stage` 可安全归一化，其他 `age.*` 拒绝。所有 `clothing.*` 必须有衣物、鞋履或明确覆盖状态证据；书籍、武器、药物、工具、乘骑和手持物也不能借 `accessories.*` 进入人物外观，只有原文明示佩戴的徽章/标志等例外。服务端同时拒绝外貌估龄、把目光当眼睛、把审美/气质/瞬时表情当面部物理特征，以及无纹身语义的 `distinctive_marks.tattoo`；这些线索由 deferred、动作/物品或后续专用契约承载。当前确定性字段契约为 `visual-observation-v3.4`。

```text
在 chunk 中精确查找 quote
  → 唯一命中：生成 start/end
  → 多次命中：结合人物 mention 和前后锚点消歧
  → 仍不唯一：标记 deferred
  → 找不到：拒绝或执行一次窄范围重试
```

这样做不是放松证据要求，而是把字符计数从概率模型交回确定性代码。

模型必须优先返回能够唯一定位的完整短句，而不是只返回“黑发”“他”等高重复片段。若必须支持重复短句，可增加可选的 `before_anchor`、`after_anchor`，但不让模型计算数字 offset。

### 第 3 步：小说级实体收敛

块级结果只产生候选人物，不直接完成高风险合并。

实体解析读取的是候选摘要和证据，不是整本原文：

```text
精确姓名与规范化
  → 已确认别名
  → 同场景共现和互斥约束
  → 亲属称谓和说话对象
  → 跨章节连续性
  → 高置信自动链接
  → 中置信审核建议
  → 低置信保持分离
```

视觉候选在此阶段从 `entity_ref` 绑定到稳定 `character_id`。所有权不能唯一确定时，候选仍可保存，但不能进入自动外观聚合。

### 第 4 步：小说级人生阶段解析

块级模型只提取“前世”“五六岁”“多年后”“梦中”等时间信号。小说级 resolver 再决定四个正交维度：

| 维度 | 回答的问题 |
|---|---|
| `timeline_id` | 属于主线、平行分支还是假设世界 |
| `presentation_mode` | 当前叙述、回忆、预叙、梦境还是传闻 |
| `life_phase_key` | 人物处于幼年、成年、重生后等哪个人生阶段 |
| `transformation_state` | 是否处于伪装、变身、附体或临时特殊形态 |

“前世”通常先作为 phase/presentation 信号，不由块级模型自动创建 canonical timeline。无法唯一判断时生成候选作用域并等待审核。

### 第 5 步：把视觉候选绑定成 Observation

一条自动 `FeatureObservation` 只有满足以下条件才能进入自动聚合：

1. 证据精确定位到 source document version 和 chunk；
2. 字段路径属于版本化视觉字段注册表；
3. 绑定到明确 `mention_span_id` 和 `character_id`；
4. 时间作用域没有高风险歧义；
5. `epistemic_status=asserted`；
6. grounding 满足自动聚合门禁。

不满足条件的结果进入 candidate、suggestion 或 deferred，不直接污染角色外观档案。

### 第 6 步：按需处理关系和神情

关系和神情仍然有价值，但不应占用每块主调用的大部分预算。

关系抽取只在以下情况下运行：

- 段落包含稳定关系证据；
- 实体解析需要亲属、称谓或身份约束；
- 用户启用关系分析功能。

关系类型使用封闭 ontology。攻击、递交、观察等一次性行为写入事件，不创建无限扩张的 relation type。

神情抽取优先在用户选择目标场景或准备出图时运行。这样系统不必为整部长篇穷举每一次皱眉和叹气。只有可见线索进入图像上下文，内心情绪不自动变成笑、哭等视觉指令。

### 第 7 步：识别证据缺口并进行有界自主检索

`identify_evidence_gaps` 回答“原文证据还缺什么”，不是“最终角色设计还缺什么”。当前固定 `visual_enrichment` 流水线可以继续作为直接模式；在多轮检索确有质量收益时，增加可选 `VisualEvidenceAgent`：

```text
character_id + life_phase_key + evidence gaps + 已有 Observation
  → 读取人物/阶段摘要
  → 生成或调整检索查询
  → BM25 + vector + neighbor 检索
  → 判断命中是否属于目标人物、阶段和字段
  → 必要时在预算内再次检索
  → 提交 EvidenceCandidate / deferred / coverage conclusion
  → 确定性校验和持久化分流
```

Agent 只允许使用只读检索、上下文读取、证据验证和候选提交工具。它不能直接写正式 Observation、合并人物、修改阶段、批准 Profile 或自行扩大预算。Application Orchestrator 强制 `max_turns`、`max_tool_calls`、`max_provider_calls`、passage/token/cost/deadline 上限；结果高度重复、证据充分、达到预算或索引不可用时立即停止。

Agent 负责语义提案，确定性代码仍负责：quote/offset 校验、字段注册表、值 Schema、人物/阶段门禁、重复与冲突检测。只有 `asserted + exact + ownership/scope resolved` 才进入 Observation；推断进入 Suggestion；歧义进入 deferred。`not_stated` 必须同时保存查询、别名、字段词、覆盖范围、读取 passage 和预算终止原因，不能只凭模型一句“没找到”。

Direct结果诊断模型、稳定原因码、决策顺序和最小验收用例以[视觉精提取设计 21.5.2](21-retrieval-augmented-visual-enrichment.md)为唯一契约；本页只定义它在全文主链中的位置。

### 第 8 步：聚合外观、评价质量并识别设计缺口

确定性代码先把已绑定 Observation 整理为事实快照：

```text
稳定身份锚点
  + 人生阶段基础外观
  + 持久变化
  + 伪装/变身状态
  + 目标场景已批准的临时状态（可选）
  = ResolvedAppearanceFacts
```

这里不加入画风、镜头、设计性灯光或未经批准的服装补全。事实视图先形成 Profile 草稿；用户解决冲突和设计缺口并批准后，Snapshot Resolver 才生成 `ResolvedCharacterSnapshot`，随后单独构造 `SceneRenderBrief` 和 `ImageRenderSpec`。

`PipelineRun.status=succeeded` 只说明技术步骤执行完，不代表结果可以出图。首版 `DecompositionQualityReport` 由确定性 `QualityEvaluator` 生成，统计 grounding、人物绑定、阶段覆盖、跨阶段污染、冲突、检索覆盖和成本，区分：

- `ready`：证据分解结果可以进入人工档案确认，不等于出图就绪；
- `needs_review`：存在可修正歧义；
- `insufficient`：关键人物、阶段或证据覆盖不足，需要继续提取或明确标为 `not_stated`。

是否允许探索图、角色设定图或一致性场景图，由 23.4.7 的 `RenderReadinessReport` 决定。

`Review Agent` 不是质量报告的唯一生成者。只有确定性报告产生人物误合并疑点、阶段语义歧义、冲突分类困难或 `not_stated` 覆盖争议时，才把最小证据包交给 Review Agent。Agent 输出带证据的审核建议；最终 `quality_status`、阻断代码、数据库写入和是否转人工仍由版本化策略决定。

## 23.6 哪些内容留在主调用，哪些移走

| 信息 | 主调用是否保留 | 原因 |
|---|---|---|
| 重要人物候选 | 保留 | 视觉事实必须知道可能属于谁 |
| 代表性姓名/称谓证据 | 保留 | 支持后续实体链接 |
| 所有代词 mention | 移走 | 数量大、价值低、offset 易错 |
| 原子视觉事实 | 保留 | 一期核心产物 |
| 与视觉事实直接相关的时间信号 | 保留 | 防止跨阶段污染 |
| 完整 Scene | 移到时间解析 | 块级整段场景价值低 |
| 完整 Timeline | 移到小说级 resolver | 需要跨章节判断 |
| 稳定人物关系 | 条件执行 | 服务实体解析，但不是每块必需 |
| 一次性事件行为 | 移到事件抽取 | 不属于稳定关系 |
| 全文神情 | 改为按需 | 不为长篇穷举瞬时状态 |
| 未解析指代列表 | 由 resolver/质量报告产生 | 当前生产链路未持久化模型列表 |
| 模型 warnings | 改为系统生成 | 质量问题应由确定性门禁产生 |
| 职业、能力、身份背景 | 移到其他 domain/suggestion | 不进入一期外观聚合 |

## 23.7 调用预算和故障边界

### 23.7.1 必须增加的硬边界

每种调用至少配置：

```python
wire_api
structured_output_mode
thinking_enabled
reasoning_effort
max_output_tokens
total_deadline_seconds
max_items_per_result
max_retries
max_cost
```

候选起点而非最终冻结值：

| 调用 | 总生成上限候选（含 reasoning） | 总墙钟候选 |
|---|---:|---:|
| 块级视觉候选 | 8,192 | 120 秒 |
| 实体歧义解析 | 4,096 | 90 秒 |
| 人生阶段解析 | 4,096–8,192 | 120 秒 |
| 条件关系抽取 | 4,096 | 90 秒 |
| 目标场景神情 | 2,048–4,096 | 60 秒 |

不同 Provider 对 reasoning tokens 和 output tokens 的统计与限制语义可能不同，Adapter 必须显式记录。若 Provider 支持独立推理预算，应分别限制；若只支持总 completion 上限，应把隐藏推理计入预算。最终数值只能通过 validation 集冻结。

### 23.7.2 DeepSeek v4-flash Adapter 契约

按 2026-08-25 的 [DeepSeek Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)、[Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/) 和 [Responses API](https://api-docs.deepseek.com/api/create-response/)：

- Chat Completions 默认开启 thinking，默认 reasoning effort 为 `high`；
- Chat 的 `json_object` 只保证输出是合法 JSON，不保证符合项目完整 Schema；
- Responses API 当前支持 `deepseek-v4-flash`、`text.format=json_schema`、`reasoning.effort` 和 `max_output_tokens`；
- Responses 的 `max_output_tokens` 同时覆盖 reasoning 和可见输出；
- Responses 可能以 `incomplete` 结束，Chat 可能以 `finish_reason=length` 结束，两者都不能当成功结果持久化。

推荐主路径：

```python
wire_api = "responses"
request = {
    "model": "deepseek-v4-flash",
    "input": chunk_prompt,
    "reasoning": {"effort": "none"},
    "max_output_tokens": 8192,
    "text": {
        "format": {
            "type": "json_schema",
            "name": "visual_candidate_extraction",
            "schema": VisualCandidateExtractionResult.model_json_schema(),
        }
    },
}
```

`reasoning.effort=none` 是块级候选抽取的起始实验值，不是未经评测的永久默认。A/B 必须比较 `none` 和 `low`；若 `none` 造成视觉召回或人物归属下降，再升到 `low`，不能直接回到无上限的默认 `high`。

兼容路径仍可使用 Chat Completions，但必须显式设置 thinking、reasoning effort 和 `max_tokens`，并检查 `finish_reason`。不能只保留当前的 `temperature=0`。

无论使用哪种 wire API，Provider 返回后仍必须经过：

1. JSON/Pydantic 校验；
2. 数组数量上限；
3. 字段注册表校验；
4. evidence grounding；
5. 实体和时间作用域门禁。

JSON Schema 约束解决的是输出形状，不解决事实幻觉、错误归属和跨阶段污染。

### 23.7.3 真正的总墙钟截止时间

在 `httpx` 网络 timeout 之外，Provider 调用外层必须增加总截止时间，例如：

```python
async with asyncio.timeout(total_deadline_seconds):
    response = await client.post(...)
```

这样持续返回很小网络分片的超长推理也不能无限延长任务。

### 23.7.4 有界重试

建议策略：

1. 网络失败或截断：同一输入重试一次；
2. 第二次仍失败：缩小到自然段边界再重试一次；
3. 仍失败：记录 deferred chunk，停止继续收费；
4. 已成功的阶段结果必须有 checkpoint，后续失败不能让前面调用重复收费；
5. 恢复时从失败的 `step_key + chunk_ordinal` 继续。

## 23.8 Worker 与版本设计

### 23.8.1 推荐 Step 图

```text
normalize_and_chunk
extract_visual_candidates
resolve_entities
resolve_character_phases
bind_observations
identify_evidence_gaps
enrich_visual_evidence（条件执行，可使用 Direct 或 Agent 模式）
aggregate_appearance
evaluate_decomposition_quality
identify_design_gaps
```

可选关系、事件和神情步骤由能力开关或业务请求触发，不阻塞最小视觉档案主链。

### 23.8.2 为什么不能在一个 Step 中偷偷多调几次模型

当前 cursor 主要记录 `current_chunk_ordinal`。如果一个 chunk 内先完成实体调用、再执行视觉调用，而第二次失败，恢复时可能重复第一次收费调用。

因此应该使用独立 Step，或至少把 cursor 升级为：

```json
{
  "schema_version": "v3",
  "stage": "visual_candidates",
  "current_chunk_ordinal": 12,
  "completed_artifact_hash": "..."
}
```

独立 Step 更符合现有 `PipelineRun/PipelineStep`、租约、attempt 和 fencing 设计。

### 23.8.3 拆分版本号

当前单一 extractor version 同时代表所有类别。以后应拆为：

```text
entity_extractor_version
visual_extractor_version
temporal_resolver_version
relation_extractor_version
quality_evaluator_version
```

这样只修改关系 Prompt 时，不需要 supersede 全部视觉事实；只升级人生阶段 resolver 时，也不需要重新调用全文视觉抽取。

### 23.8.4 Scene 迁移风险

现有视觉 Observation 可以通过 extractor version 失效旧自动结果，但 Scene 使用稳定 narrative slot 更新。若新版主调用不再返回 Scene，旧自动 Scene 不会仅因“新结果为空”自然消失。

迁移必须增加以下之一：

- Scene 的 resolver version 和有效状态；
- 按 source chunk 清理/失效旧自动 Scene 的确定性步骤；
- 新旧 temporal resolver 并行写入后做差异切换。

不能只把 `scene_hypotheses` 从 Schema 删除就结束迁移。

## 23.9 兼容实施路线

本节 P0–P3 表示兼容迁移的大里程碑，不是周排期。实际从当前代码基线拆成 R0–R6，包含工期、阶段效果和验收门禁，见[路线图 17.6](14-roadmap.md#176-从当前代码基线实施视觉重构的增量排期)。

### P0：先止住失控推理和成本

不改数据库主结构，先完成：

1. Provider 配置显式声明 wire API、thinking 开关和 reasoning effort；
2. 对块级抽取 A/B 测试 `reasoning=none` 与 `low`，禁止继续隐式使用默认 `high`；
3. Provider 请求增加覆盖 reasoning 与可见内容的输出上限；
4. 优先试用 Responses API 的 `json_schema`，同时保留受控 Chat 兼容路径；
5. 增加真正的总墙钟截止时间；
6. 保存 input/cache/reasoning/output tokens、完成状态、finish/incomplete reason、延迟和请求 ID；
7. `length`、`incomplete`、空 content 和 Schema 校验失败不得写成成功 Chunk；
8. 限制每类最大结果数量；
9. 不再要求穷举代词；
10. `unresolved_references` 和模型 `warnings` 退出生产主 Schema；
11. 未知或非视觉字段进入 suggestion/rejection；
12. 空结果触发质量 warning，而不是静默等同于“原文没有事实”。

P0 的目的不是证明新方案质量更好，而是让调用有预算、有截止时间、有可观察数据。P0 必须先于 v3 结论评测完成，否则无法区分收益来自 Provider 治理还是 Schema 重构。

### P1：引入视觉候选 Schema v3

1. 新建 `VisualCandidateExtractionResult`；
2. 使用 `local_id/entity_ref`；
3. 模型只返回 evidence quote，不返回数字 offset；
4. 新增确定性 evidence locator；
5. 使用 Adapter 转换为最小 `GroundedVisualExtractionResult`，Repository 只写 mention 和视觉 Observation；
6. 开发环境直接将远程抽取切换为 v3，不执行付费 v2/v3 Shadow，也不自动回退 v2；
7. 使用已保存的 v2 fixture/usage 做离线成本与质量参照，真实调用只运行 v3；
8. extractor schema 同步升级为 `visual-observation-v3`。

Adapter 是过渡手段，不能长期掩盖候选实体和最终实体的区别。

### P2：拆分实体、阶段和绑定步骤

1. 增加候选实体和候选 Observation 的稳定存储或 Artifact；
2. 实现 `resolve_entities`；
3. 实现 `resolve_character_phases`；
4. Observation 强制绑定 `mention_span_id`；
5. 拆分 resolver/extractor version；
6. 增加 Scene 迁移和失效策略；
7. 人工修正后只重跑绑定、聚合和质量评价，不默认重调全文模型。

### P3：按需关系、神情与质量闭环

1. 稳定关系使用封闭 ontology；
2. 一次性行为进入 StoryEvent/EventParticipant；
3. 神情改为目标场景抽取；
4. Direct visual-enrichment 保持默认基线，在 A/B 证明净收益后条件启用 `VisualEvidenceAgent`；
5. 上线确定性 `DecompositionQualityReport`，复杂问题才调用 Review Agent；
6. 上线设计缺口、`RenderReadinessReport`、`SceneRenderBrief` 和 `ImageRenderSpec`；
7. 一致性图像生成只接受 approved/locked Profile、可解析 Snapshot 和冻结的场景/渲染规格；探索性概念图必须带非稳定产物标记。

## 23.10 必须怎样评测，才能决定方案有效

不能只观察新 Prompt 是否更短。至少比较：

| 组别 | 方案 |
|---|---|
| A | 已保存的 v2 八类联合 Schema 响应与 usage（离线历史基线） |
| B | 已保存的 v2 + Provider 治理结果（如已有则离线复用） |
| C | v3 视觉优先 + 服务端 offset（唯一真实调用组） |
| D | v3 + 不同 chunk/邻块上下文候选 |

开发阶段不为 A/B 重新发起付费调用，也不运行在线 v2/v3 Shadow。若历史 v2 样本不足，只把结论标记为“缺少同文成本基线”，不能用再次承担已知不可接受开销的方式补齐。v3 的正确性由种子集、定位器/Adapter 边界测试和真实失败回填 case 共同推进；发布前再冻结 80–120 个多作品黄金 case。

每组报告：

- 视觉事实 precision、recall、macro-F1；
- 主要角色 mention F1 和实体严重误合并数；
- exact evidence rate、token span F1；
- 跨人物、跨阶段、跨时间线污染；
- 每块 P50/P95 延迟；
- input/cache/reasoning/output tokens；
- 超时、断流、Schema 失败率；
- 每个正确视觉字段成本；
- deferred 数和人工审核量。

继续使用项目已定义的最低发布门禁：

- 字段证据定位准确率不低于 95%；
- 外貌字段 precision 不低于 90%；
- 规范字段路径率 100%；
- 主要角色 mention F1 不低于 0.90；
- 高影响自动误合并数为 0；
- critical slice 不得出现跨人物、跨阶段污染回归。

降低 tokens 和延迟只有在这些质量门禁仍通过时才算成功。

## 23.11 代码修改地图

| 目标 | 主要位置 |
|---|---|
| 新候选 Schema 和 Provider Protocol | `application/ports/extraction.py` |
| wire API、thinking/reasoning、JSON Schema、输出预算、总截止时间、usage | `infrastructure/llm/openai_compatible.py`、`settings.py` |
| 确定性证据定位 | `domain/policies/grounding.py` |
| 视觉字段注册和 domain 门禁 | `domain/policies/visual_fields.py` |
| 分阶段 Worker 编排和 cursor | `workers/handlers/extraction.py`、`workers/main.py` |
| 候选、绑定和版本持久化 | `infrastructure/db/repositories/extraction.py`、ORM、migration |
| 外观聚合资格 | `domain/policies/appearance_aggregation.py` |
| 设计缺口与出图就绪度 | 新的 render readiness policy + Profile application service |
| Direct → Agent 精提取路由 | 新的 `VisualEnrichmentRoutingPolicy` + visual-enrichment Worker/API |
| 场景简报与 Provider 中立 Prompt 编译 | Visual Director/Prompt compiler + `GenerationContextBuilder` |
| 正式质量报告 | evaluation domain/repository + 新 quality evaluator |
| 本地 v3 诊断 | `tests/测试/inspect_visual_candidates.py` |

## 23.12 这次不做什么

- 不针对某一部小说硬编码角色名、门派、力量体系或阶段表；
- 不因为当前样例慢就直接更换模型并宣布问题解决；
- 不默认执行“每块 × 每角色”调用；
- 不删除关系、神情和时间线能力，只改变它们的执行时机；
- 不让职业、性格、能力或行为推断自动补全外貌；
- 不把画风、镜头、灯光设计和 Provider 语法写入小说事实或目标时点事实快照；
- 不把“检索没有找到”自动改写成“角色明确没有该特征”；
- 不把 Pipeline 技术成功等同于角色档案已经可以出图；
- 不在缺少多作品黄金集时冻结 chunk 大小和 token 上限。

## 23.13 最终完成定义

本重构完成时，应能清楚回答以下问题：

1. 每个 chunk 的主要 LLM 调用是否有明确任务、预算和截止时间？
2. Provider 是否显式设置 wire API、thinking/reasoning 和总输出上限？
3. `length`、`incomplete`、空 content 或 Schema 失败是否会被拒绝而非误记成功？
4. 每条自动视觉事实能否回到精确原文证据和人物 mention？
5. 实体、人生阶段和时间线是否由独立版本化步骤解析？
6. 单个步骤失败后能否从 checkpoint 恢复而不重复已完成收费调用？
7. 关系和神情是否只在需要时运行？
8. 模型使用量、延迟、失败和每个正确字段成本是否可查询？
9. 质量报告是否能阻止阶段污染，并把证据不足明确转成设计缺口或探索性生成限制？
10. 多作品冻结测试集是否证明质量没有因降本而回归？
11. 每个出图字段是否能追溯到小说事实、人工决定、已批准建议、工作流默认或参考资产之一？
12. 小说未写的关键字段是否形成设计缺口，而不是由抽取模型补成事实？
13. `ResolvedAppearanceFacts`、`CharacterRenderProfile`、`ResolvedCharacterSnapshot`、`SceneRenderBrief` 和 `ImageRenderSpec` 是否职责分离且可独立版本化？
14. 系统是否分别报告 `concept_ready`、`character_design_ready` 和 `consistent_scene_ready`？

如果这些问题中任意一个仍无法回答，就不能把“Prompt 变短了”视为重构完成。

---

[← 上一篇](22-general-novel-decomposition-quality-plan.md) · [文档索引](README.md) · [下一篇 →](01-project-overview-and-principles.md)
