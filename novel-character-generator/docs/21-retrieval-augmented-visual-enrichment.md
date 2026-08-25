# 检索增强的角色视觉精提取实现设计

> [← 上一篇](20-api-cookbook-and-error-catalog.md) · [文档索引](README.md) · [下一篇 →](01-project-overview-and-principles.md)
>
> 文档版本：1.3 · 修订日期：2026-08-25
>
> 当前状态：**产品基础闭环已实现**。系统已建立版本化 `retrieval_passages`、SQLite FTS5 中文预分词、OpenAI-compatible EmbeddingPort、Qdrant Local、批量断点续建、BM25/vector RRF、同章邻居扩展、确定性 QueryPlan、query/hit 审计、结构化精提取 Provider、passage→`text_chunk` 唯一回映、Observation/Suggestion 分流、Suggestion 审核 API 与外观重聚合。角色页面已接入索引状态、阶段选择、字段缺口自动规划、精提取任务、证据和 Suggestion 审核。Embedding 未配置时 build 保持 `degraded_lexical_only`，visual-enrichment API 返回 `retrieval_index_not_ready`。黄金集保留数据与扩展接口，Runner 和发布门禁在功能契约稳定后再实现。

## 21.1 目标与边界

目标是在不重新把整本小说发送给大模型的前提下，为选定的重要角色补充可出图的、可追溯的视觉信息。系统先从全文召回可能相关的细粒度段落及相邻上下文，再以结构化模型调用确认人物归属和字段。

本能力能解决“人名和外貌描述不在同一句或同一小段”的召回问题，但不允许把小说未写的脸型、瞳色、服装纹样伪装为原文事实。

| 输出层 | 含义 | 能否自动进入 AppearanceState |
|---|---|---|
| `asserted` + `exact` | 原文直接、可精确定位地支持的字段 | 可以 |
| `inferred` / `uncertain` | 由职业、行为、比喻、关系或上下文得到的候选 | 不可以；仅供审核 |
| `style_default` | 原文没有答案时的设计默认值 | 不可以；须人工接受后作为渲染决策 |

`FeatureObservation` 仍是唯一的原文事实载体；`FeatureSuggestion` 是候选和设计默认值载体。现有聚合器只采纳 `asserted` Observation，这一规则保持不变。

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

创建精提取任务前，系统根据当前源版本和所选阶段的有效 asserted Observation 计算缺失字段组；自动规划只为仍缺失的组固化 QueryPlan，避免为已有事实重复调用模型。当前 `visual-field-gap-v1` 按七个字段组判断覆盖：核心组为 hair、face、body、clothing，可选组为 accessories、marks_injuries、disguise_cleanliness；组内已有任意一个有效字段即视为该组已覆盖。更细的原子字段完整度和单次 Run 内自动多轮追加暂不启用，待真实使用验证后再细化。

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

最小事件为：`retrieval.index.started|ready|failed`、`visual_enrichment.planned|retrieved|packet_built|extracted|evidence_persisted|suggested|completed`。事件记录 run/step、源版本、索引/词典/Prompt/Provider 版本、计数、哈希、耗时和成本，不记录正文。

黄金集执行当前暂缓，只保留既有 Evaluation Repository/ORM 和后续 Runner/Grader 接入边界，不把尚未稳定的字段组与交互规则固化为发布门禁。功能契约稳定后，PoC 至少比较：仅现有大块提取、1K/100 BM25-only + 邻居、1K/100 vector-only + 邻居、1K/100 hybrid + RRF + 邻居，以及至少一个不同 passage/overlap 参数。主指标为字段组证据 precision/recall、人物归属准确率、精确 span 准确率、每角色新增的已确认视觉字段、每正确字段成本、p95 延迟和“无依据推断进入 Observation”的零容忍率。

索引构建、中文词典、人名/别名扩展、跨块 offsets、重试/取消、旧源版本隔离、多人代词歧义和 Suggestion 审批都必须有自动测试。PoC 还必须覆盖：两字人名和专名分词、FTS/Qdrant passage ID 对齐、Embedding API 批处理及 429/5xx 恢复、部分批次成功后的断点续建、向量维度不匹配拒绝、模型切换强制新 collection、Qdrant Local 数据目录恢复，以及远程 Provider 请求/日志不泄漏正文和密钥。

## 21.9 实施顺序与完成定义

1. Migration、领域/ORM、版本化切分器、中文 search-term builder 和项目词典；
2. `EmbeddingPort` 的远程 API 适配器、SQLite FTS5、Qdrant Local 适配器，以及批量编码/断点续建；
3. 后台 `source_indexing` 与两路索引的原子发布、重建、版本隔离和恢复测试；
4. RetrievalPort、QueryPlan、BM25/vector 并行召回、RRF、邻居扩展和 query/hit 审计；
5. `visual_enrichment` Run、精提取 Schema、证据回映和 Observation/Suggestion 分流；
6. 角色页面的索引状态、字段缺口、证据包和 Suggestion 审核入口（已实现）；
7. 功能契约稳定后实现黄金集 PoC、成本/延迟基线和发布门禁；需要多进程并发时再迁移 Qdrant Server。

完成不等于“建了 FTS 表”。当前阶段的产品闭环要求用户能上传小说后看到索引状态、对选定角色自动规划或手选缺口字段、创建精提取任务、查看新增事实的原文证据、审核推断建议，并重新聚合得到可追溯档案；这些入口与恢复/安全测试已经形成基础闭环。黄金集 Runner、报告和发布门禁是后续独立验收阶段，不阻塞当前功能迭代。

---

[← 上一篇](20-api-cookbook-and-error-catalog.md) · [文档索引](README.md) · [下一篇 →](01-project-overview-and-principles.md)
