# 检索增强的角色视觉精提取实现设计

> [← 上一篇](20-api-cookbook-and-error-catalog.md) · [文档索引](README.md) · [下一篇 →](01-project-overview-and-principles.md)
>
> 文档版本：1.6 · 修订日期：2026-08-26
>
> 当前状态：**产品基础闭环已实现**。系统已建立版本化 `retrieval_passages`、SQLite FTS5 中文预分词、OpenAI-compatible EmbeddingPort、Qdrant Local、批量断点续建、BM25/vector RRF、同章邻居扩展、确定性 QueryPlan、query/hit 审计、结构化精提取 Provider、passage→`text_chunk` 唯一回映、Observation/Suggestion 分流、Suggestion 审核 API 与外观重聚合。角色页面已接入索引状态、阶段选择、字段缺口自动规划、精提取任务、证据和 Suggestion 审核。Embedding 未配置时 build 保持 `degraded_lexical_only`，visual-enrichment API 返回 `retrieval_index_not_ready`。黄金集保留数据与扩展接口，Runner 和发布门禁在功能契约稳定后再实现。

## 21.1 目标与边界

目标是在不重新把整本小说发送给大模型的前提下，为选定的重要角色补充有原文证据、可追溯的视觉信息。它提高小说事实覆盖率，但不负责补齐最终出图所需的全部设计、场景、美术和 Provider 字段；完整字段桥梁见[视觉优先的出图字段与全文抽取重构方案](23-visual-first-extraction-refactor.md)。

本能力能解决“人名和外貌描述不在同一句或同一小段”的召回问题，但不允许把小说未写的脸型、瞳色、服装纹样伪装为原文事实。

| 输出层 | 含义 | 能否自动进入 AppearanceState |
|---|---|---|
| `asserted` + `exact` | 原文直接、可精确定位地支持的字段 | 可以 |
| `inferred` / `uncertain` | 由职业、行为、比喻、关系或上下文得到的候选 | 不可以；仅供审核 |
| `style_default` | 原文没有答案时的设计候选 | 不可以；须人工接受后作为角色设计或工作流决策 |

`FeatureObservation` 仍是唯一的原文事实载体；`FeatureSuggestion` 是候选和设计建议载体。现有聚合器只采纳 `asserted` Observation，这一规则保持不变。检索缺口回答“原文证据是否覆盖”，设计缺口回答“要生成这类图还缺哪些已批准决定”，二者不得使用同一状态或同一个自动补齐循环。

非目标：本阶段不接入图像 Provider、不训练 LoRA、不自动把推断写入 RenderProfile，也不取代当前大块文本分析中的角色、别名、场景和时间线发现。

## 21.2 总体流程

```text
上传不可变源版本
  → 后台 build_retrieval_index（不阻塞上传成功）
  → 规范化/章节识别/细粒度 passage 构建/中文检索索引发布
  → 现有文本分析 Run：人物、别名、阶段、基础 Observation
  → 用户选择角色与待补字段，创建 visual_enrichment Run
  → QueryPlan：别名 + 阶段 + 字段词典 + 语义扩展
  → BM25 与向量并行召回 → 融合 → 邻居扩展 → 去重、重排、上下文预算
  → LLM 精提取与人物归属确认
  → 证据精确校验并回映到原 text_chunk
  → asserted Observation / 候选 Suggestion / 未归属待审
  → 重跑现有 aggregate_appearance，进入既有审核流程
```

上传后建索引与“开始分析角色”解耦：上传 API 在源文档版本和 Artifact 持久化成功后立即返回；索引 Run 在后台领取。用户在索引未就绪时仍可运行当前全文提取，但视觉精提取只能等待与该源版本一致的索引处于 `ready`。

## 21.3 分块与索引构建

### 21.3.1 细粒度 Passage

首个 PoC 参数采用 **目标 1,000 估算 tokens、相邻 100 tokens 重叠**。这是待验证的初始值，不是永久生产常量；切分必须优先遵守章、段、句边界，不能在句中硬切。

每个 passage 保存规范化文本区间、原文区间映射、章节序号、token 估算、前后邻居和内容哈希。切分器按以下顺序工作：

1. 先按章节、段落、句子建立边界；
2. 累积到接近 1,000 tokens 时在最近安全边界切分；
3. 从上一个 passage 的末尾回取不超过 100 tokens 的完整句子作为重叠；
4. 若单句超过上限，保持单句完整并记录 `oversized_sentence=true`；
5. 记录每个 passage 到一个或多个现有 `text_chunks` 的子区间映射。

`text_chunks` 继续服务当前大块提取、pipeline cursor 和既有证据契约，**不得**被 1K passage 替换或改变其 ordinal。`retrieval_passages` 是可按版本重建的派生检索层。

### 21.3.2 中文 BM25 与向量混合索引

SQLite FTS5 的默认 `unicode61` 分词按 Unicode 分隔符划分连续字符，不能被假定为适合无空格的中文小说；原文不得直接作为唯一 FTS 输入。PoC 先使用中文分词库生成以空格分隔的版本化 `search_terms`，基线可用 `jieba`，但必须加载项目词典并锁定库版本。项目词典至少包括：人名、接受的别名、称谓、门派、武器、标志性物件，以及头脸、发型、体态、服装、饰物、伤势、表情、姿态和环境的视觉词与文学化变体。

`retrieval_passages.content` 保存未分词原文；FTS 表只保存派生检索字段，不能反向成为正文真值。例如：

```text
content:    她微微垂首，乌黑的长发沿着白衣滑落，腰间悬着一柄细剑。
body_terms: 她 微微 垂首 乌黑 长发 白衣 滑落 腰间 悬着 一柄 细剑
```

两个字的人名和专名必须通过自定义词典保持完整。可将 FTS5 `trigram` 作为子串召回对照，但它对少于三个 Unicode 字符的全文查询有限制，不能作为中文角色检索的唯一分词方案。词典更新、分词器更新或 `search_terms` 生成规则更新都必须提升 `lexical_profile_version` 并重建 FTS 索引。

一期检索基线固定为 **BM25 + 向量混合召回**，两路均为必需能力：

- BM25 负责精确人名、别名、称谓、专有名词、视觉关键词和罕见词；
- 向量召回负责无共同关键词的同义表达、文学化描写、隐喻和语义相近段落；
- 两路各自保留 top-K，先取并集，再使用 Reciprocal Rank Fusion（RRF）融合排名；
- 精确实体命中只作为可解释的重排加分，不能删除向量召回的无实体候选；
- 融合召回只负责提高 recall，最终人物归属、字段和值仍必须经过 LLM 判断与证据校验。

索引 build 只有在 BM25 和向量两部分都完成后才可标记为 `ready`。Embedding Provider 失败时记录 `degraded_lexical_only` 并重试，默认不得静默把精提取降级为纯 BM25；如运维人员显式允许降级，Run 必须记录降级状态，结果不得计入正式召回率基线。

Embedding Provider 通过独立 `EmbeddingPort` 接入并记录供应方、模型、模型 revision、维度、归一化方式和版本。**PoC 默认先接远程 Embedding API**，以减少本机显存、模型下载和推理服务维护成本；BGE-M3、GTE 等本地中文/多语模型是后续可替换实现，不硬编码为业务依赖。远程 embedding 会向外部 Provider 发送小说 passage，必须显式配置、获得数据处理授权，并遵守 21.8 和数据治理文档的脱敏、保留及删除要求。

### 21.3.3 PoC 物理实现：SQLite FTS5 + Qdrant Local + Embedding API

三部分各自只承担一种职责：

| 组件 | 保存/处理内容 | 不承担的职责 |
|---|---|---|
| SQLite 普通表 | passage 原文、章节、offset、邻居、内容哈希和业务状态 | 不执行语义相似度计算 |
| SQLite FTS5 | 预分词 `body_terms/entity_terms/visual_terms`，使用 BM25 排序 | 不保存业务真值，不理解隐喻和近义表达 |
| Embedding API | 将 passage 或查询文本转换为固定维度向量 | 不持久化项目检索状态，不做最终人物归属 |
| Qdrant Local | passage 向量、point ID 和最小过滤 payload，执行余弦相似度检索 | 不作为正文、Run 状态或证据的唯一存储 |

PoC 使用 `qdrant-client` 的 on-disk local mode，不启动 Docker 或独立 Qdrant Server。建议路径为 `data/qdrant/`；point ID 与稳定 `retrieval_passage_id` 一致，payload 只保存 `source_document_version_id`、`retrieval_index_build_id`、章节/ordinal 和内容哈希。召回后始终按 passage ID 回 SQLite 读取正文，避免正文出现两个可冲突的副本。

```text
后台建索引：passage → FTS search_terms → SQLite FTS5
                    └→ batch Embedding API → Qdrant Local

在线精提取：QueryPlan → FTS5/BM25 top-K
                    └→ Embedding API(query) → Qdrant top-K
                    → RRF/邻居扩展 → evidence packet → LLM
```

当前 API 进程与 Worker 是独立进程。PoC 中只有单写 Worker 打开 Qdrant Local：它既执行后台建索引，也执行 `visual_enrichment` 的向量查询；API 只创建 Run，并从 SQLite 读取已经落库的索引状态、命中审计和提取结果，不直接打开 Qdrant Local。不得让多个进程各自直接打开同一个 local path。若需要 Web 请求内实时向量查询、多个 Worker 并发访问，或数据量超过 PoC 范围，则把适配器连接目标切换为独立 Qdrant Server，业务层、passage ID 和 RetrievalPort 保持不变。

Embedding API 必须支持批量编码、超时、429/5xx 有界重试和断点续建。已经成功写入且 `content_hash + embedding_profile_version` 相同的 passage 不重复计费。查询向量和文档向量必须来自同一 embedding profile；更换模型、revision、维度、归一化规则或 query/document 前缀时，创建新的 Qdrant collection 和 index build，禁止把不同向量空间写入同一 collection。

建议 collection 名只使用受控标识，例如：

```text
novel_passages__<embedding_profile_version>__d<dimension>__<index_version>
```

### 21.3.4 发布与版本

索引只对不可变 `source_document_version_id` 建立。建成后在单事务中将 build 标为 `ready`；检索端只读取完整、同一 `retrieval_index_version` 的 build。源版本、切分算法、分词器、词典或同义词规则改变时创建新 build，不覆盖旧 build。新版本上传后旧索引和历史 Run 保留用于重放。

## 21.4 数据模型与迁移

实施至少需要一条 Alembic migration，并新增或扩展如下持久化契约：

| 对象 | 关键字段/约束 | 用途 |
|---|---|---|
| `retrieval_index_builds` | `source_document_version_id`、`index_version`、`status`、`pipeline_run_id`、配置哈希、错误摘要；`(source_document_version_id, index_version)` 唯一 | 管理可重建索引的发布状态 |
| `retrieval_passages` | build ID、chapter ID、ordinal、normalized/original start/end、content、token_count、content_hash、previous/next passage ID | 存放 1K 细粒度上下文和可追溯位置 |
| `retrieval_passages_fts` | 外部内容 FTS5 表：`body_terms`、`entity_terms`、`visual_terms`、passage ID | 预分词中文 BM25 检索；不作为业务真值 |
| `retrieval_passage_embeddings` | passage ID、embedding profile/version、维度、Qdrant collection/point ID、content hash、状态 | 向量召回引用和断点续建状态；不在 SQLite 重复保存完整向量 |
| `retrieval_query_runs` | enrichment run、character ID、阶段目标、字段组、query plan/hash、索引/词典版本 | 重放检索和审计“为什么读到这些文本” |
| `retrieval_query_hits` | query run、passage ID、source channel、BM25/vector 分数、各路 rank、RRF 分数、扩展原因、final rank、selected 标志 | 保存混合召回、邻居扩展、去重和截断决策 |
| `feature_observations` 扩展 | 可空 `retrieval_passage_id` 或等价 evidence-link | 事实仍以 `source_chunk_id` 为最终证据锚点，同时保留召回来源 |
| `feature_suggestions` 扩展 | source version、enrichment run、evidence links、suggestion provenance/version | 让 `inferred`/`style_default` 可审核、可重放 |

证据锚点规则：LLM 返回 `retrieval_passage_id` 和 passage 内 offsets。Repository 必须先验证引用文本，再将区间映射到包含该证据的既有 `text_chunk`；只有映射唯一且 `validate_evidence` 成功时，才写入 `FeatureObservation.source_chunk_id`。跨 `text_chunk` 的证据不猜测拼接，要求模型拆成单一可定位证据或降级为 Suggestion。

## 21.5 QueryPlan、召回与上下文构造

一个精提取 Run 面向“角色 × 目标阶段 × 待补字段组”。QueryPlan 由确定性代码构造并持久化，不让模型自行扩大检索范围：

```text
实体词 = canonical name + 已接受别名 + 有范围的称谓
阶段词 = life phase/年龄/事件/章节范围（若存在）
字段词 = 目标字段的视觉词典、同义词、文学化词
查询组 = 实体精确查询、实体+字段查询、无实体字段候选查询
```

建议初始配额：每个查询组 BM25 top 40、向量 top 40；两路取并集后按 `RRF(k=60)` 融合，再执行实体命中加分、章节去偏和近重复折叠。每个字段组最多保留 16 个主命中 passage，每个命中自动加入前后各一个邻居；最终证据包按原文顺序截断到 Provider 的上下文预算。参数必须通过黄金集冻结，不能只凭经验长期固定。`100` token overlap 不是解决共指的唯一机制，**命中 passage 的双向邻居扩展是强制项**。

向量查询不能只嵌入“角色名 + 字段名”。QueryPlan 应分别构造人物身份查询、目标视觉字段的自然语言查询、人生阶段查询和无实体描述查询。例如“描写该角色发型轮廓、头发颜色、束发方式或凌乱状态的段落”作为语义查询；各查询的候选再统一融合，避免单个宽泛向量查询淹没少见证据。

无实体字段查询用于找“一个瘦小的身影、黑发凌乱”这类名字稍后才出现的描写。它只能生成候选；模型必须根据证据包明确绑定人物，否则写为 `unresolved`，不得强行分配给查询目标角色。

### 21.5.1 Direct 与 Agent 两种执行模式

当前已实现的是 `direct`：确定性 QueryPlan → 一次混合检索 → evidence packet → 一次结构化精提取。目标新增的 `agent` 模式复用同一索引、QueryPlan、hit 审计和持久化门禁，只允许在预算内根据首轮结果调整查询、读取邻居或受控相邻章节，再提交候选。

```text
direct：稳定、便宜、容易重放，默认基线
agent：只在别名/间接描写/阶段歧义导致 Direct 不足时条件启用
```

Agent 不能绕过 `retrieval_query_runs/hits` 直接读取未审计全文，也不能直接写 Observation。两种模式必须在同一黄金集比较新增有效字段、错误 asserted、人物/阶段误归属、人工查找时间、调用数、延迟和每正确字段成本；没有稳定净收益时继续使用 Direct。详细工具和停止边界见[Agent 增强架构](07-agent-architecture.md)。

### 21.5.2 Direct → Agent 确定性路由契约

本节是**目标契约，当前尚未实现**。是否调用 Agent 由版本化 `VisualEnrichmentRoutingPolicy` 决定，不能让 Direct 模型或 Agent 自行选择执行模式。路由输入必须来自已持久化的 gap、query/hit 审计、精提取结果和人物/阶段 resolver 状态。

Direct 完成后形成：

```python
class DirectEnrichmentOutcome(BaseModel):
    run_id: UUID
    character_id: UUID
    life_phase_key: str | None
    requested_field_groups: list[str]
    gaps_before: list[str]
    gaps_after: list[str]

    exact_asserted_count: int
    suggestion_count: int
    unresolved_count: int
    rejected_count: int

    canonical_name_hit_count: int
    confirmed_alias_hit_count: int
    semantic_only_hit_count: int
    neighbor_context_needed_count: int
    unbound_character_count: int
    unbound_phase_count: int
    conflicting_phase_count: int

    query_coverage_status: Literal[
        "incomplete", "complete", "evidence_exhausted"
    ]
    retrieval_index_status: str
    budget_remaining: bool
    routing_decision: Literal[
        "complete", "run_visual_evidence_agent",
        "entity_review", "phase_review", "not_stated", "stop"
    ]
    reason_codes: list[str]
    routing_policy_version: str
    input_fingerprint: str
```

`gaps_after` 必须在新 asserted Observation 持久化后，使用同一字段缺口策略重新计算。命中数和 unresolved 数不能由模型自由报告，必须由保存的 query hits、evidence packet 和持久化分流结果确定性统计。

#### 决策顺序

```text
无 gaps_before
  → complete

运行 Direct
  → 新 exact asserted 已关闭目标缺口
      → complete
  → 索引未就绪、预算/功能关闭或结果不可重放
      → stop
  → 人物归属需要改变实体真值
      → entity_review
  → 阶段归属需要改变阶段/时间线真值
      → phase_review
  → 缺口仍存在 + 有可利用语义线索 + 可由补查上下文解决 + 仍有预算
      → run_visual_evidence_agent
  → 已完成规定查询覆盖且没有可利用线索
      → not_stated
  → 其他情况
      → stop/人工检查
```

调用 Agent 必须同时满足：

```text
gaps_after 非空
AND retrieval_index_status = ready
AND budget_remaining = true
AND agent capability enabled
AND 至少存在一个 agent_eligible reason code
AND 不存在 entity/phase hard-review reason code
```

Agent用于“继续搜索或读取局部上下文可能解决”的问题，不用于裁决人物或时间业务真值。

#### 稳定原因码

| reason code | 观察信号 | 路由 |
|---|---|---|
| `direct_sufficient` | 新增 exact asserted 且目标缺口已关闭 | `complete` |
| `indirect_description_candidate` | 视觉命中没有目标姓名，但存在描述性人物或相邻上下文线索 | Agent eligible |
| `visual_hit_without_canonical_name` | 主要命中来自无实体/语义查询，字段相关但人物未绑定 | Agent eligible |
| `neighbor_context_needed` | 当前 passage 不足，前后邻居可能给出姓名、代词先行项或时间词 | Agent eligible |
| `confirmed_alias_hit_without_context` | 命中已确认别名/称谓，但当前 packet 不足以绑定该视觉描述 | Agent eligible |
| `local_temporal_context_needed` | 外观命中缺少局部阶段信号，相邻段落可能补足 | Agent eligible |
| `multi_phase_hits_locally_resolvable` | 命中横跨多个阶段，但章节邻域和显式时间词可能消歧 | Agent eligible |
| `only_inferred_or_uncertain` | Direct 只产生 Suggestion，仍存在可追查证据线索 | Agent eligible；无可利用线索时停止 |
| `unconfirmed_alias_ownership` | 称谓/别名可能属于多个角色，需要建立或修改 AliasAssertion | `entity_review` |
| `entity_merge_or_split_required` | 需要合并/拆分人物才能决定归属 | `entity_review` |
| `ambiguous_life_phase` | 一个年龄/标签映射到多个正式阶段 | `phase_review` |
| `timeline_or_branch_ambiguous` | 需要改变 timeline/branch/reality truth | `phase_review` |
| `hard_observation_conflict` | 同作用域存在不兼容的已绑定事实 | 转冲突审核，不调用证据 Agent |
| `evidence_exhausted` | 规定的姓名、已确认别名、字段、语义和邻居覆盖完成，仍无相关证据 | `not_stated` |
| `retrieval_index_not_ready` | 当前源版本索引未 ready | `stop` |
| `agent_budget_unavailable` | Agent 被关闭或调用/成本/时间预算不足 | `stop` |

`confirmed_alias_hit_without_context` 与 `unconfirmed_alias_ownership` 必须分开：前者只补查上下文，后者会改变人物身份真值，必须交给 Entity Resolution/人工。类似地，`local_temporal_context_needed` 可以由证据 Agent读取邻居，而 `ambiguous_life_phase`、时间线分支裁决必须交给阶段 resolver/人工。

#### `not_stated` 的覆盖门禁

只有以下计划内查询都已执行或被版本化策略明确裁剪，才能把 `query_coverage_status` 标为 `evidence_exhausted`：

- canonical name + 目标字段组；
- 所有已接受别名/有范围称谓 + 目标字段组；
- 目标字段的自然语言语义查询；
- 无实体视觉描述查询；
- 目标人生阶段/年龄/事件查询（存在目标阶段时）；
- 选中高分命中的强制双向邻居；
- 查询、命中、裁剪、章节范围、索引版本和停止原因全部已持久化。

“零命中”本身不能直接等于 `not_stated`。若索引降级、查询被预算提前裁剪或人物/阶段仍有未解决歧义，只能 `stop`、`deferred` 或转审核。

#### 最小验收用例

| 场景 | 预期路由 |
|---|---|
| Direct 找到唐三幼年“黑色短发”，证据、人物、阶段均明确 | `complete/direct_sufficient` |
| “瘦小身影”先出现，后邻居才写“正是唐三” | `run_visual_evidence_agent/neighbor_context_needed` |
| 命中已确认昵称“小三”，需要扩大邻居确认视觉句归属 | `run_visual_evidence_agent/confirmed_alias_hit_without_context` |
| “小三”可能指两个不同角色，AliasAssertion 未确认 | `entity_review/unconfirmed_alias_ownership` |
| 紫色眼眸命中需要读取修炼上下文判断瞬时状态 | `run_visual_evidence_agent/local_temporal_context_needed` |
| 同一年龄对应两个已存在人生阶段 | `phase_review/ambiguous_life_phase` |
| 全部规定查询和邻居覆盖完成，仍没有常态瞳色证据 | `not_stated/evidence_exhausted` |
| 当前源版本检索索引未完成 | `stop/retrieval_index_not_ready` |

路由结果按 `input_fingerprint + routing_policy_version` 幂等。相同输入不得因为重复 Worker 执行改变决定；Agent 关闭时 Direct 主链仍可完成，Agent eligible 项转为 `stop/deferred`，不得静默扩大调用。

创建精提取任务前，系统根据当前源版本和所选阶段的有效 asserted Observation 计算缺失字段组；自动规划只为仍缺失的组固化 QueryPlan，避免为已有事实重复调用模型。当前实现使用 `visual-field-gap-v2`，按七组及组内维度评分：hair 要覆盖 color 与 form；face、body 按维度阈值；clothing 要覆盖 form 与 color/material；accessories、marks_injuries、disguise_cleanliness 仍使用组级存在性规则。具体版本以 `FIELD_GAP_POLICY_VERSION` 为准。

这只是“是否值得继续找原文”的召回启发式，不是“是否已经足够出图”的判定。尤其：

- accessories 或 marks/injuries 没有 Observation 只表示尚未发现描述，不表示角色明确没有配饰、伤痕；
- `presence_or_absence` 是当前维度名，不代表系统已证明 absence；只有直接否定证据才能形成 `negated` Observation；
- 某组达到 v2 阈值不代表该组所有原子字段完整，也不代表角色设计或一致性场景已经 ready；
- 一个字段组在有界 QueryPlan 后仍无证据时，目标设计应记录 `not_stated/evidence_exhausted`，停止重复检索并转成设计缺口。当前 API 尚未完整持久化该终止状态。

## 21.6 LLM 精提取契约

LLM 输入是带稳定 ID 的 evidence packet，而不是整本书。每段携带 `passage_id`、章节、相对顺序、文本、邻居关系和可见的角色/别名候选。输出至少包含：角色 ID（可为空）、source passage ID、原子 `field_path`、值、精确引用和 offsets、`evidence_kind`、`epistemic_status`、置信度与时间作用域提示。

规则如下：

- 直接描述、可精确映射、人物归属明确的事实才可成为 `asserted` Observation；
- “铁匠”“握锤”“炉火旁”等可成为职业、道具、动作或场景事实；不得无证据推出“皮围裙”“粗糙双手”等服装或身体事实；
- 文学化词可经版本化词典拆为原子字段，但必须保留原句、映射规则版本和中等以下置信度；
- 多人同段、代词指向不唯一、仅内心情绪或否定描述时，输出 `uncertain`/`inferred`；
- 内心情绪不能直接变成表情；只有外显线索可作为可视化线索；
- `inferred` 与 `uncertain` 写入带 evidence link 的 `FeatureSuggestion`，默认 `candidate`，不触发自动聚合。

## 21.7 Worker、API 与恢复

新增目标 Step 和 Run 类型：

| Run/Step | 触发 | 幂等边界 | 说明 |
|---|---|---|---|
| `source_indexing / build_retrieval_index` | 上传新源版本后后台创建 | `(source_document_version_id, retrieval_index_version)` | 构建/发布细粒度索引；不阻塞上传 |
| `visual_enrichment / plan_visual_retrieval` | 用户选择角色/字段组 | request hash + source/index version | 固化 QueryPlan 与预算 |
| `visual_enrichment / retrieve_visual_evidence` | 上一步成功 | query plan hash | 召回、邻居扩展、重排并保存 hits |
| `visual_enrichment / extract_visual_evidence` | evidence packet 就绪 | packet hash + provider/prompt version | 外部 LLM 调用及可恢复 checkpoint |
| `visual_enrichment / persist_visual_evidence` | 结构化结果返回 | evidence fingerprint | 校验证据、分流 Observation/Suggestion |
| `visual_enrichment / evaluate_direct_outcome`（目标） | Direct 持久化完成 | input fingerprint + routing policy version | 重算 gaps，生成 `DirectEnrichmentOutcome` 和确定性路由决定 |
| `visual_enrichment / run_visual_evidence_agent`（条件目标） | 决定为 `run_visual_evidence_agent` | Direct outcome hash + AgentSpec/tool/budget version | 有界自主补查并提交候选；不是默认必经步骤 |
| `visual_enrichment / persist_agent_evidence`（条件目标） | Agent 候选返回 | agent result hash + evidence fingerprint | 复用相同 grounding/人物/阶段门禁和分流规则 |
| `visual_enrichment / aggregate_appearance` | 有新 asserted Observation | 复用现有聚合指纹 | 只重算受影响角色 |

每个外部 LLM 调用通过现有 `model_calls` 记录 Provider、模型、请求哈希、用量与费用；Worker 仍遵守 claim、lease generation、checkpoint 和取消语义。不得用 Web 请求线程执行索引或 Provider 调用。

已注册 API 为：

```text
GET  /api/v1/characters/{character_id}/visual-field-gaps
POST /api/v1/characters/{character_id}/visual-enrichment-runs
GET  /api/v1/characters/{character_id}/visual-enrichment-runs
GET  /api/v1/visual-enrichment-runs/{run_id}/evidence
POST /api/v1/feature-suggestions/{suggestion_id}/resolve
```

创建请求包含可选目标 `field_groups`、`auto_plan`、可选 `life_phase_key`、最大调用/上下文预算和 `Idempotency-Key`。`field_groups=[]` 且 `auto_plan=true` 时，服务端按当前缺口策略选择字段组并将策略版本写入 Run 游标；没有缺口时返回 `visual_field_gaps_empty`。响应返回 `202` 和 Run ID；索引未就绪时返回稳定的 `retrieval_index_not_ready`，而不是退化成全文隐式调用。

目标请求增加 `routing_mode: "direct_only" | "auto_after_direct"`。当前和 R4 验收前默认必须为 `direct_only`；`auto_after_direct` 也必须先执行 Direct，再由 21.5.2 的策略决定是否运行 Agent，调用方不能用该参数强制跳过证据门禁或强制 Agent 改写结果。响应和 evidence API 暴露 routing policy version、decision、reason codes、Direct outcome hash 和可选 AgentRun ID。

## 21.8 配置、观测、评测与验收

新增配置须版本化并暴露在受保护的运行诊断中；以下都是**目标配置，当前 Settings 尚未实现**：

```ini
RETRIEVAL_PASSAGE_TARGET_TOKENS=1000
RETRIEVAL_PASSAGE_OVERLAP_TOKENS=100
RETRIEVAL_LEXICAL_PROVIDER=sqlite_fts5
RETRIEVAL_LEXICAL_PROFILE_VERSION=zh-jieba-visual-v1
RETRIEVAL_VECTOR_STORE=qdrant_local
QDRANT_LOCAL_PATH=./data/qdrant

EMBEDDING_PROVIDER=openai_compatible
EMBEDDING_BASE_URL=
EMBEDDING_API_KEY=
EMBEDDING_MODEL=
EMBEDDING_DIMENSION=
EMBEDDING_PROFILE_VERSION=
EMBEDDING_BATCH_SIZE=16
EMBEDDING_TIMEOUT_SECONDS=60
```

还须版本化 BM25/vector top-K、RRF 参数、邻居数、每角色最大 packet/call 数和 enrichment Provider timeout。`EMBEDDING_API_KEY` 只能来自 Secret/环境变量；受保护诊断可以显示 provider、model、dimension 和 profile version，但密钥、全文、完整向量和完整 prompt 不进入日志或 Metrics 标签。

最小事件为：`retrieval.index.started|ready|failed`、`visual_enrichment.planned|retrieved|packet_built|extracted|evidence_persisted|suggested|completed`。路由落地后增加 `visual_enrichment.direct_evaluated|routed|agent_started|agent_stopped`，记录 outcome/routing policy hash、decision、reason codes、预算与停止原因，不在事件中记录正文。所有事件记录 run/step、源版本、索引/词典/Prompt/Provider 版本、计数、哈希、耗时和成本。

黄金集执行当前暂缓，只保留既有 Evaluation Repository/ORM 和后续 Runner/Grader 接入边界，不把尚未稳定的字段组与交互规则固化为发布门禁。功能契约稳定后，PoC 至少比较：仅现有大块提取、1K/100 BM25-only + 邻居、1K/100 vector-only + 邻居、1K/100 hybrid + RRF + 邻居，以及至少一个不同 passage/overlap 参数。主指标为字段组证据 precision/recall、人物归属准确率、精确 span 准确率、每角色新增的已确认视觉字段、每正确字段成本、p95 延迟和“无依据推断进入 Observation”的零容忍率。

索引构建、中文词典、人名/别名扩展、跨块 offsets、重试/取消、旧源版本隔离、多人代词歧义和 Suggestion 审批都必须有自动测试。路由测试必须覆盖 21.5.2 的最小用例、相同 input fingerprint 幂等、Agent capability 关闭、预算耗尽、Worker 在 Direct/Agent 边界崩溃恢复、实体/阶段 hard-review 优先于 Agent，以及“零命中但覆盖不完整”不得写 `not_stated`。PoC 还必须覆盖：两字人名和专名分词、FTS/Qdrant passage ID 对齐、Embedding API 批处理及 429/5xx 恢复、部分批次成功后的断点续建、向量维度不匹配拒绝、模型切换强制新 collection、Qdrant Local 数据目录恢复，以及远程 Provider 请求/日志不泄漏正文和密钥。

## 21.9 实施顺序与完成定义

1. Migration、领域/ORM、版本化切分器、中文 search-term builder 和项目词典；
2. `EmbeddingPort` 的远程 API 适配器、SQLite FTS5、Qdrant Local 适配器，以及批量编码/断点续建；
3. 后台 `source_indexing` 与两路索引的原子发布、重建、版本隔离和恢复测试；
4. RetrievalPort、QueryPlan、BM25/vector 并行召回、RRF、邻居扩展和 query/hit 审计；
5. `visual_enrichment` Run、精提取 Schema、证据回映和 Observation/Suggestion 分流；
6. 角色页面的索引状态、字段缺口、证据包和 Suggestion 审核入口（已实现）；
7. 实现 `DirectEnrichmentOutcome`、`VisualEnrichmentRoutingPolicy`、原因码、路由 API/事件和纯策略单元测试，保持 `direct_only` 默认；
8. 接入有界 VisualEvidenceAgent、恢复测试和 Direct/Agent A/B，达成 R4 门禁后才允许 `auto_after_direct` 成为可选默认；
9. 功能契约稳定后实现黄金集 PoC、成本/延迟基线和发布门禁；需要多进程并发时再迁移 Qdrant Server。

完成不等于“建了 FTS 表”。当前阶段的产品闭环要求用户能上传小说后看到索引状态、对选定角色自动规划或手选缺口字段、创建精提取任务、查看新增事实的原文证据、审核推断建议，并重新聚合得到可追溯档案；这些入口与恢复/安全测试已经形成基础闭环。黄金集 Runner、报告和发布门禁是后续独立验收阶段，不阻塞当前功能迭代。

---

[← 上一篇](20-api-cookbook-and-error-catalog.md) · [文档索引](README.md) · [下一篇 →](22-general-novel-decomposition-quality-plan.md)
