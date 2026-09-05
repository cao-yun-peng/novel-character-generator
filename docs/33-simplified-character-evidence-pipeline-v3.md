# 简化人物证据流水线 V3 契约

> 状态：运行时增量契约；用于 `v3-simplified-character-evidence` 分支。M1—N3、文档事实层、跨 Chunk 人物身份层和确定性人物档案组装均已建立代码边界；真实模型质量仍需单独评测。

## 1. 目标

V3 优先建立一条容易解释和验证的三段流水线：

```text
M1：识别人物提及，标记 type（exact / describe / null）与 scope（individual / collective / null），并归拢相关外貌原文
  ↓
N2：用代码验证人物称呼和外貌原文，并执行 exact evidence 优先去重
  ↓
M2：以一个 individual exact 人物为目标，一次携带本轮全部 individual describe 块解析
  ↓
N3：验证证据、汇总 describe 归属、消费已唯一归属片段并回送剩余 describe
```

M1 可以把同一段 `evidence_quote` 提案到多个提及块。N2 Grounding 后 exact 对相同 raw quote 具有优先权，所有 describe 中的同文副本会被删除；exact↔exact 和 describe↔describe 仍可重复。第一轮只有 `exact + individual` 提及可以作为归属目标；过滤后的 `describe + individual` 作为待归属证据池。N3 仲裁后仍未被任何 exact 消费的 individual describe 可再次进入 M2，并被建立为新的 Chunk 内独立正式人物；collective 始终隔离。

## 2. 稳定来源身份

每个输入 Chunk 至少保留：

- `source_document_version_id`：小说来源版本；
- `chunking_policy_version`：分块长度、边界和重叠策略版本；
- `chunk_id`：同一来源版本和分块规则下稳定；
- `chunk_hash`：Chunk 正文的内容哈希；
- `chunk_source_span`：Chunk 在来源文档中的绝对半开字符区间；
- `chunk_text`：本次处理的完整正文。

`chunk_id` 不能单独证明内容未变化。来源版本、分块规则或正文变化时，必须生成新的来源/Chunk 版本关系。

### 2.1 重叠分块

长文本使用版本化重叠分块，降低人物或证据恰好位于 Chunk 边缘时的漏召回。重叠只提高召回，不证明两个 Chunk 中的提及属于同一个人物。

每个 Chunk 在清单中记录：

- `chunk_source_span`；
- `overlap_left_characters`；
- `overlap_right_characters`；
- 原始 `chunk_hash`。

同一原文可能因重叠同时进入相邻 Chunk。N2 保持每个 Chunk 的局部包不可变，不在本层跨 Chunk 合并；后续汇总先按 `absolute = chunk_source_span.start + local` 换算文档位置，再以来源类型、人物标签、原文事实、文档事实 span 和事实结构组成的确定性键去重，不能仅按 quote 字符串去重。每个合并结果必须保留全部来源 Chunk occurrence。

### 2.2 文档覆盖清单与显式截断

每次文档处理先生成 `DocumentChunkManifest`，至少记录 `document_hash`、`total_characters`、全部 Chunk、`processed_source_end` 和：

- `coverage_status=complete`：已覆盖完整来源文档，`truncation_reason=null`；
- `coverage_status=truncated`：因最大 Chunk 数、最大字符数、Provider 限制、人工停止或读取错误只处理了前段，并给出明确 `truncation_reason`。

不得静默丢弃尾部，也不得把 `truncated` 运行的召回率、人物总数或“未发现人物”结论当作完整文档结果。Manifest 属于确定性服务层，不发送给模型。

Manifest 还必须通过以下代码校验：

- `complete` 时 `processed_source_end == total_characters`；
- `truncated` 时 `processed_source_end < total_characters`；
- Chunk 按 `chunk_source_span.start` 升序排列，区间全部位于 `[0, total_characters)`；
- 首个 Chunk 从 0 开始，最后一个 Chunk 的 `end` 等于 `processed_source_end`，相邻 Chunk 不得留下未声明的空洞；
- `overlap_left_characters`、`overlap_right_characters` 必须与相邻 Chunk 的真实交集长度一致；
- 每个 `chunk_hash` 必须由对应文档原文切片逐字计算，且该切片长度必须等于 `chunk_source_span.end - chunk_source_span.start`。

JSON Schema 只能约束字段形状和 `complete/truncated` 与原因的组合，以上跨字段关系由 Manifest 校验器负责。

### 2.3 所有模型调用的统一边界

只要某阶段调用模型，就必须拆成四层：

1. **代码编排信封**：保存来源版本、Chunk ID、原文位置、hash、缓存键、运行轮次等系统信息；
2. **模型输入**：只包含完成当前语义任务真正需要阅读的正文、人物称呼和候选证据；
3. **模型输出**：只返回当前语义任务需要的逐字事实，不生成系统 ID、短引用、状态、hash 或来源位置；
4. **代码回填与验证**：代码把模型结果重新绑定到编排信封，回填原文 span、packet hash、cache key 和 trace，再交给下一确定性阶段。

`source_document_version_id`、`chunk_id`、`chunk_hash`、`packet_hash`、缓存键、版本号、时间戳、run ID 以及 `t1`、`d1`、`d1-f1` 等内部短引用都不进入模型输入输出。

当前 V3 中 M1、M2 是模型阶段，必须遵守此边界；N2、N3 是代码阶段，不调用模型。未来新增模型阶段时沿用同一规则。

### 2.4 模型提示词的统一组成

每个模型阶段的 Provider 请求固定由三部分组成：

1. `system instruction`：只描述该阶段职责、禁止事项、证据边界和输出规则；
2. `user payload`：只放对应 Schema 定义的最小模型输入 JSON；
3. `response schema`：强制结构化 JSON 输出，拒绝 Schema 之外字段。

提示词不得拼入代码编排信封，也不得要求模型“记住”或回传系统字段。M1 提示词只负责提及发现和逐字 evidence；M2 提示词只针对当前 individual exact，从允许证据中返回肯定属于该人物的最小 `fact_quote` 和结构化事实。Provider 原始输出必须先过 Schema、原文绑定和唯一性校验，不能直接进入 N2、N3 或人物记忆。

## 3. M1：局部候选人物与证据归拢

### 3.1 唯一职责

M1 从一个 Chunk 中识别人物提及表达，并把模型认为与该提及有关的连续原文证据放进同一个结构块，同时输出 `mention_type` 与 `mention_scope`。

M1 不做字段分类、外貌原子化、跨 Chunk 身份、时间作用域、持续性或人物记忆写入。

### 3.2 模型输入

```json
{
  "chunk_text": "青衫老者身形高瘦，留着花白胡须。白衣女子眉目清秀。"
}
```

来源版本、分块规则、`chunk_id`、hash 和 `chunk_source_span` 保存在 `M1OrchestrationEnvelope`，不发送给模型。

### 3.3 模型输出

```json
{
  "candidate_mentions": [
    {
      "mention_type": "describe",
      "mention_scope": "individual",
      "mention_quote": "青衫老者",
      "evidence_quotes": [
        "青衫老者身形高瘦，留着花白胡须"
      ]
    },
    {
      "mention_type": "describe",
      "mention_scope": "individual",
      "mention_quote": "白衣女子",
      "evidence_quotes": [
        "白衣女子眉目清秀"
      ]
    }
  ]
}
```

JSON 中同名字段不能重复，因此一个人物的多条证据必须放在 `evidence_quotes` 数组中。

模型不输出 `chunk_id`。代码依据本次调用对应的 `M1OrchestrationEnvelope`，把输出绑定回正确 Chunk；禁止相信模型自行回传的系统身份字段。

`local_mention_id` 不由模型生成。服务端按验证后的数组顺序物化为 `m1`、`m2` 等 Chunk 局部提及编号。第一轮只有 `mention_type=exact` 的块形成 `local_character_ref`；describe 在 N3 后若仍有未消费证据，可通过 M2 独立建人形成 `promoted_character_ref`。`null` 不形成独立人物。

没有任何人物称呼、只能发现人物相关证据时，进入 `null` 块：

```json
{
  "mention_type": null,
  "mention_scope": null,
  "mention_quote": null,
  "evidence_quotes": ["只见一双手苍白瘦削"]
}
```

### 3.4 mention_type 判定

`mention_type` 只有三种值：

- `exact`：提及表面形式本身就是稳定、封闭的人物指称，而不是用开放属性临时拼出的描述。包括正式姓名，以及已经词汇化、像名字一样使用的稳定昵称或称号，例如“张三”“林黛玉”“唐三”“凤姐”“宝二爷”。只有这类提及可以作为确切目标人物。
- `describe`：`mention_quote` 只是泛称、身份描述或外貌描述，不能唯一指向一个人物。例如“人”“老者”“老人”“女孩”“少女”“男人”“女子”“女人”“红衣女子”“月袍老人”“青衫老者”“白衣女子”都属于 `describe`。
- `null`：原文证据里没有可抽取的人物称呼，此时 `mention_quote` 必须为 JSON `null`，不是字符串 `"null"`。

判定优先看提及本身是否含有明确人物名称。单纯由颜色、衣着、年龄、性别、职业、身份、亲属排行或人物类别词组成的短语一律是 `describe`，不能因为描述很具体就升级为 `exact`。

V3 对称号采用保守策略：

- 已经词汇化、通常直接当名字使用的昵称/称号，例如“凤姐”“宝二爷”，可以是 `exact`；
- 仍可由不同人物担任的开放角色或排行称谓，例如“二小姐”“教皇”“太子”“宗主”“大师兄”，默认是 `describe`；
- 只有当前 Chunk 存在逐字、明确的同位或命名关系，例如“王熙凤，人称凤姐”这类局部绑定证据时，代码才可把称号作为该 exact 的局部 alias；V3 不靠跨 Chunk 记忆猜测；
- 无法稳定判断时降级为 `describe`，不得冒进标为 `exact`。

### 3.5 mention_scope 与 collective 隔离

- `individual`：称呼指向一个人物；`exact` 必须是此范围，单人泛称也使用此范围。
- `collective`：称呼指向一组人物，例如“十七道白色的身影”“众人”“一群侍卫”；只能与 `describe` 搭配。
- `null`：仅与 `mention_type=null` 搭配。

collective 块可以保留 approved evidence 供审计或未来群像处理，但必须进入 quarantine；不得送入单人物 M2 解析，也不得 promotion 成一个人物。代码只通过 `single_character_mentions` 暴露可进入单人物后续流程的块，通过 `quarantined_collective_mentions` 单独保留群体块。

### 3.6 describe 泛称后缀规则

M1 提取 `mention_quote` 后，代码使用版本化的泛称后缀表 `describe-suffix-v1` 复核 `mention_type`。写成 `*女子` 表示“以女子结尾”，实际实现使用 `mention_quote.endswith("女子")`，不是把 `*女子` 直接当正则表达式。

首版后缀至少包括：

```text
*人、*老者、*老人、*男子、*男人、*女子、*女人、
*女孩、*少女、*姑娘、*妇人、*老妇、*少年、*青年、*孩童
```

示例：

```text
红衣女子  -> 命中 *女子 -> describe
白衣女子  -> 命中 *女子 -> describe
月袍老人  -> 命中 *老人 -> describe
青衫老者  -> 命中 *老者 -> describe
```

匹配顺序：

1. `mention_quote=null` 时结果为 `null`；
2. 提及是已识别出的最小正式名称或稳定词汇化别名时结果为 `exact`；
3. 否则只要命中泛称后缀表，就强制归一为 `describe`；
4. 其余提及保留 M1 的语义分类，等待评测完善后缀表。

M1 应优先拆成最小提及，避免把名字和泛称粘成一个块。例如“林黛玉这女子”应拆出 exact“林黛玉”和 describe“这女子”；相关 evidence 允许同时进入两个块。若模型将“红衣女子”错误标为 `exact`，N2 代码归一为 `describe` 并记录 `mention_type_normalized_by_suffix` trace，不直接丢弃其 evidence。

### 3.7 mention 与 evidence 的关系

`evidence_quote` 不要求逐条包含 `mention_quote`。以下两类都允许：

- `contains_mention`：evidence 内逐字包含 mention，例如“林黛玉眉目清秀”；
- `contextual`：evidence 不含 mention，但可通过当前 Chunk 的代词、邻句或局部叙事关系与该 mention 建立候选关联，例如“林黛玉进屋。她眉目清秀”中的“她眉目清秀”；
- `no_mention`：仅用于 `mention_type=null`。

该关系不由 M1 增加新字段。N2 根据字符串包含关系确定性派生 `relation_to_mention`，用于调试和评测；`contextual` 只说明 M1 建立了候选关联，不代表语义归属已经正确。

## 4. N2：最小确定性原文验证

### 4.1 验证范围

N2 只做来源存在性、结构验证和确定性的 exact evidence 优先过滤：

1. M1 输出必须由代码绑定到发起调用的 `M1OrchestrationEnvelope`；模型输出中不接受 `chunk_id` 等系统字段；
2. `mention_type` 只能是 `exact`、`describe` 或 JSON `null`，`mention_scope` 只能是 `individual`、`collective` 或 JSON `null`；
3. `exact` 必须配 `individual`；`describe` 必须配 `individual` 或 `collective`；null type 必须配 null scope 和 null quote；
4. 使用 `describe-suffix-v1` 复核并归一 mention type，归一必须写 trace；
5. 非空 `mention_quote` 必须逐字存在于 `chunk_text`，只记录原文 hash，不输出其出现次数或位置；
6. 每条 `evidence_quote` 先做严格匹配；失败后仅允许删除两边全部 Unicode 空白后字符序列完全一致的安全恢复；任何非空白字符增加、删除、替换或调序均拒绝；
7. 安全恢复后必须保存正文中的真实原文切片，而不是模型版本；记录每条 evidence 的出现次数、span、原文 hash、`match_mode` 和确定性 `relation_to_mention`；
8. 同一提及块内完全相同的 evidence 去重；
9. 无效 evidence 单独拒绝，不因一条无效 evidence 丢弃该块内其他有效 evidence。
10. 汇总当前 Chunk 所有 grounded exact 的 raw `evidence_quote`；从所有 describe 删除逐字相同项，describe 被删空时删除整个 grounded block，并基于过滤结果重算 `packet_hash`。

### 4.2 有意不做

- 不判断同一 evidence 在语义上属于哪个人物；exact 优先只是一条用户确认的确定性去冗余规则；
- 不删除 exact↔exact 或 describe↔describe 的重复 `evidence_quote`；
- 不做跨 Chunk 人物身份合并；
- 不判断外貌字段或语义是否正确。

跨提及重复证据仍是允许的 M1 提案。N2 只删除“任一 exact 已持有且 raw quote 完全相等”的 describe 副本，不由此推断 describe 属于哪个 exact 人物。

### 4.3 approved_evidence

`approved_evidence` 就是 N2 已确认存在于当前 Chunk 的 M1 `evidence_quote`。

```json
{
  "chunk_id": "chunk-001",
  "grounded_mentions": [
    {
      "local_mention_id": "m1",
      "mention_type": "describe",
      "mention_scope": "individual",
      "mention_quote": "青衫老者",
      "approved_evidence": [
        {
          "evidence_quote": "青衫老者身形高瘦，留着花白胡须",
          "occurrence_count": 1,
          "source_spans": [{"start": 0, "end": 19}],
          "relation_to_mention": "contains_mention",
          "match_mode": "exact"
        }
      ],
      "packet_hash": "..."
    }
  ],
  "rejected_evidence": []
}
```

`match_mode=exact` 表示模型 quote 与正文逐字一致；`whitespace_equivalent` 表示只在空白上有差异，且 `evidence_quote` 与 span 均已回填为正文真实切片。exact 优先过滤完成后，只要一个提及块仍保留至少一条 approved evidence，就可进入 grounded packet；但只有 `mention_scope=individual` 可进入单人物后续组包。collective 留在 quarantine，null 不进入 exact 携带的 describe 集合。

### 4.4 exact evidence 优先过滤

策略版本为 `exact-evidence-precedence-v1`，执行顺序固定在原文 Grounding 与 mention type 归一之后、最终 packet 物化之前：

1. 从全部 grounded `mention_type=exact` 块建立 raw `evidence_quote -> exact local_mention_id[]` 索引；
2. 按原顺序扫描全部 `mention_type=describe` 块（individual 与 collective 都包括）；
3. describe evidence 的 raw quote 在 exact 索引中时删除该 evidence，并写 `describe_evidence_shadowed_by_exact` trace；
4. describe 仍有 evidence 时保持剩余顺序并重算 packet hash；被删空时删除整个块并写 `describe_removed_after_exact_dedup` trace；批处理把这些事件单独保存到 `n2-grounding-traces.json` 并在 summary 汇总计数；
5. M1 `model_output` 保持原样，只有 N2 `grounded_mentions` 被过滤。

例如，萧熏儿 exact 与“少女” describe 都含有以下相同证据：

```json
{
  "exact": {"mention_quote": "萧熏儿", "evidence_quotes": ["微笑的小脸", "纤细的指尖"]},
  "describe": {"mention_quote": "少女", "evidence_quotes": ["微笑的小脸", "纤细的指尖"]}
}
```

N2 输出只保留萧熏儿 grounded block；“少女”的 evidence 被删空，因此不进入 `grounded_mentions`。若“少女”还有 exact 未持有的“少女身材修长”，则只保留这一条和该 describe 块。

比较键是 Grounding 回填后的 raw quote 完全相等，不做语义相似、标点忽略或非空白规范化。模型 quote 即使通过纯空白恢复，只要最终回填为同一 raw quote，也会被识别为重复。

### 4.5 Chunk 元数据索引

N2 验证后，由代码在 Chunk 元数据中生成可重建索引：

```json
{
  "candidate_mentions": {
    "m1": {"mention_type": "exact", "packet_hash": "...", "status": "grounded"},
    "m2": {"mention_type": "describe", "packet_hash": "...", "status": "grounded"}
  }
}
```

`packet_hash` 是局部提及证据包的指纹，不是正式人物 ID。hash 始终使用 Grounding 和 exact 优先过滤后的真实原文，具体规则见 4.6。

### 4.6 原始文本、span 与 hash 规范

所有 span 都是半开区间 `[start, end)`，下标基于已经解码完成的原始 `chunk_text` Unicode code point 序列。代码必须验证 `0 <= start < end <= len(container_text)`。

- `chunk_hash = SHA-256(chunk_text 的原始 UTF-8 字节)`；
- grounded packet v6 不再生成逐条 `quote_hash` 或 `mention_quote_hash`；原文逐字性由 raw quote、source span 回放和 `chunk_hash` 共同验证；
- CRLF/LF、全角空格、Unicode 组合形式、中文标点、首尾空格都不得在 grounding 前悄悄改写；纯空白等价恢复必须先定位并回填真实原文切片；
- 如果摄入层必须转换编码或换行，应先生成新的 `source_document_version_id` 和 `chunk_hash`，再进入本流水线；
- 重复 quote 的每个 `source_span` 是不同证据出现位置，进入 M2 前必须展开为独立 occurrence。

`packet_hash` 使用固定键顺序的规范 JSON 序列化，输入严格为：

```text
grounded_packet_version
source_document_version_id
chunking_policy_version
chunk_id
chunk_hash
chunk_source_span
local_mention_id
mention_type
mention_scope
mention_quote 原始字符串或 null
evidence_precedence_policy_version
approved evidence occurrences（按 source span 排序）：
    raw start
    raw end
    relation_to_mention
    match_mode
```

`run_id`、模型名、调用时间和 trace 不进入 `packet_hash`。N2 packet 顶层同时输出 `evidence_precedence_policy_version=exact-evidence-precedence-v1`；策略变化必须升级 packet 版本并使 hash/cache 失效。

## 5. M2：每个 exact 携带全部 individual describe 证据池解析

### 5.1 调用单位

设当前 Chunk 有 E 个 `exact + individual` 块、D 个 `describe + individual` 块。collective 不计入 E 或 D。代码生成 E 个 M2 模型任务。每个任务都包含：

1. 一个 `exact` 目标；
2. 该 exact 自身的 approved evidence；
3. 本轮全部 D 个 `describe` 块；
4. 用于理解人物关系的完整 `chunk_text`。

因此调用数是 E，不是 `E + E × D`。每个 describe 仍会被全部 exact 分别判断，只是同一 exact 对 D 个 describe 的判断合并到一次调用中。E 个任务之间可以并行。

- 在 exact 归属模式中，`describe` 还没有自己的正式人物引用；只有 N3 剩余池进入独立建人模式后才能形成 `promoted_character_ref`。
- D=0 时仍可执行 E 个任务，只拆解各 exact 自身证据。
- Chunk 没有 exact 时，describe 暂存为 unresolved，不启动人物归属 M2。
- `mention_type=null` 不进入模型输入，单独保留 trace；`mention_scope=collective` 留在 quarantine，不进入归属或独立建人输入。

### 5.2 代码编排信封

代码使用 `M2OrchestrationEnvelope` 保存以下内容，但不会把它们原样发送给模型：

- `target_character_ref` 及 target packet hash；
- target evidence 与 describe evidence 的原始 quote、Chunk span、packet hash 和内部映射；
- `task_cache_key`、`context_version`、`resolver_version` 和 `resolution_round`；
- 真正发送给 Provider 的 `model_input`。

`describe_ref`、`fragment_ref`、`evidence_ref`、span、hash 和状态都只存在于代码信封或代码回填结果中。实际 Provider 请求只能取 `model_input`；模型不需要读取、记忆或回传这些编排字段。

### 5.3 真正发送给模型的输入

```json
{
  "target": {
    "mention_quote": "林黛玉",
    "approved_evidence_quotes": [
      "林黛玉换上红衣，走进屋中"
    ]
  },
  "describe_blocks": [
    {
      "mention_quote": "红衣女子",
      "evidence_quotes": [
        "红衣女子眉目清秀，身形纤细"
      ]
    },
    {
      "mention_quote": "白发老人",
      "evidence_quotes": [
        "白发老人站在她身后"
      ]
    }
  ],
  "chunk_text": "林黛玉换上红衣，走进屋中。红衣女子眉目清秀，身形纤细。白发老人站在她身后。"
}
```

`chunk_text` 只用于理解代词、上下句和人物关系。模型输出的 `fact_quote` 必须逐字来自 `target.approved_evidence_quotes` 或 `describe_blocks[].evidence_quotes`；只存在于 Chunk 上下文、但不在允许证据池中的文字不得输出为事实。

### 5.4 模型输出

```json
{
  "belongs_to_target": [
    {
      "fact_quote": "眉目清秀",
      "category": "face",
      "attribute": "眉目",
      "value": "清秀"
    }
  ]
}
```

模型只返回肯定属于当前 exact 的外貌事实；没有属于目标的事实时返回空数组。模型不输出 `not_target`、`uncertain`、任何 ref、span、support 字段或 epistemic 状态。Prompt 必须要求只输出原文明示的当前视觉事实，否定、不确定和纯推断内容直接省略。

`fact_quote` 是唯一保留的原文锚点。代码按以下顺序回填：

1. `fact_quote` 能在 target approved evidence 中安全匹配：归并到 exact，不消费 describe；
2. 否则，它只能在一个 describe evidence occurrence 中安全匹配：回填内部来源和 span，交给 N3 仲裁；
3. 匹配多个 describe occurrence：标记 `ambiguous_fact_binding`，不归并、不删除；
4. 不在允许证据池中：标记 `fact_not_in_allowed_evidence` 并拒绝；
5. 安全匹配沿用 N2 规则：严格逐字优先，失败后只容忍删除 Unicode 空白后字符完全一致，任何非空白改写拒绝。

### 5.5 task 级缓存与幂等

每个 exact 的完整 M2 请求生成稳定 `task_cache_key`：

```text
SHA-256(canonical JSON {
  target_packet_hash,
  ordered_describe_pool_hash,
  context_version,
  resolver_version
})
```

模型名、请求时间和 run ID 不进入 key。Prompt、输出 Schema、事实绑定或归属策略变化时必须升级 `resolver_version`；Chunk 上下文构造变化时必须升级 `context_version`。相同有效 key 直接复用完整输出，不执行部分 ref 缓存拼接。

### 5.6 M2 第二种模式：剩余 describe 独立建人

exact 归属和 N3 仲裁结束后，每个仍有未消费 evidence 的 describe 生成一个独立建人任务。若有 R 个剩余 describe 块，就生成 R 个任务。

真正发送给模型的输入：

```json
{
  "describe": {
    "mention_quote": "红衣女子",
    "remaining_evidence_quotes": [
      "红衣女子眉目清秀，身形纤细"
    ]
  },
  "chunk_text": "林黛玉走进屋中。红衣女子眉目清秀，身形纤细。"
}
```

模型输出可以把一个剩余 describe 池拆成一个或多个人物。模型仍不读取或返回 ref/span：

```json
{
  "characters": [
    {
      "character_label_quote": "红衣女子",
      "belongs_to_character": [
        {
          "fact_quote": "眉目清秀",
          "category": "face",
          "attribute": "眉目",
          "value": "清秀"
        }
      ]
    }
  ]
}
```

代码允许 `character_label_quote` 逐字等于已经验证过的 describe `mention_quote`，此时不生成或保存人物标签位置；其他标签仍须在剩余证据池中安全且唯一匹配。每条 `fact_quote` 独立执行严格/纯空白等价 Grounding：安全唯一匹配的事实正常回填来源和 span；重复、歧义或不存在的事实单独进入 review，不猜测 occurrence，也不连带删除同人物已安全绑定的事实。人物标签有效且至少一条事实安全时即可建立人物；全部事实失败时不建人。多个新人物的标签或已接受事实位置发生重叠时，相关人物仍整体失败关闭。未绑定内容保存在 `unassigned_fragments`，不得静默丢弃。该策略版本为 `promotion-partial-fact-acceptance-v1`。

`promotion_hash` 基于来源版本、Chunk、describe packet hash、按位置排序的剩余原文 hash/span、`context_version` 和 `resolver_version` 计算。代码按每个人最早的已绑定事实位置排序后分配 `promotion_index=1..N`，不使用模型数组顺序生成正式引用。

### 5.7 当前运行时映射

Python `0.1.0.dev26` 按上述契约提供以下边界：

- `build_m2_attribution_envelopes`：从一个 N2 `GroundingResult` 为每个 individual exact 生成一个 `M2OrchestrationEnvelope`，并把全部 individual describe 展开为代码侧 occurrence binding；collective 与 null mention 不进入输入；
- `M2AttributionOrchestrator`：只把 `model_input`、M2 system instruction 和 `M2_ATTRIBUTION_RESPONSE_SCHEMA` 交给 Provider，解析最小事实输出后执行 target 优先、describe 唯一 occurrence 的安全绑定；失败项只进入代码侧 issues；
- `M2PromotionEnvelope.from_grounded_describe`：接收一个 individual describe 及 N3 产生的 remaining fragments；未接 N3 时也可使用完整 approved evidence 做确定性测试；
- `M2PromotionOrchestrator`：逐条验证事实来源，部分接受安全事实、隔离歧义事实，拦截跨人物标签/已接受事实重叠，按最早安全事实位置生成稳定 `promotion_index`，并保留未认领残片；
- `resolve_n3_chunk`：等待同一 Chunk 全部 exact 结果，直接归并 exact 事实，对 describe fact span 做唯一消费、跨目标重叠冲突隔离和非冲突剩余片段重建；
- `run_n3_promotion_from_m2_run`：验证 M1/M2 来源 hash，重放当前 N2，写出 N3 三类产物，并对剩余 individual describe 执行带稳定 hash 的断点续跑；
- `replay_promotion_grounding`：不调用模型；读取已保存的 promotion envelope 与模型原始输出，按当前版本化 Grounding 策略重新生成 grounded/review 结果，使模型输出缓存与确定性策略解耦；
- `run_document_evidence_aggregation`：不调用模型；把 exact 与 promoted 事实的 Chunk 局部 span 换算为文档绝对 span，逐字回放校验，并安全合并重叠 Chunk 副本，同时保留全部来源 occurrence；
- `prepare_document_identity`：不调用模型；建立完整 local/promoted 人物节点目录、原文上下文、确定性共享事实/局部共指边和每节点有上限的候选任务；
- `build_local_coreference_edges`：只在同一 Chunk 和双方上下文交集内，从可逐字回放的显式同位、示指命名或连续共指原文建立 `describe -> exact` 的确定性 same edge；
- `run_document_identity`：按任务缓存执行或恢复 M3，重新 Grounding 已保存模型输出，只有全部任务成功后才建立统一人物注册表；
- `run_identity_rescue`：按无向人物簇对消除反向候选，复用已有 grounded 裁决，并在每轮重建注册表后重新生成残余任务；默认最多三轮，无决定性注册表变化时提前停止。注册表的当前 unresolved 由最终合并图和 cannot-link 派生，已被 supplemental same/different 消解的历史 uncertain 不再残留；same/different 冲突失败关闭并进入 review；
- `run_local_identity_closure_replay`：不调用模型；复用已保存的 M3 与 rescue grounded 决策，加入通过当前局部共指策略验证的边后重建 registry/profile，并输出前后摘要和独立审计产物；
- `run_document_profile_assembly`：不调用模型；验证 registry/evidence 文档身份、完整事实 hash、Chunk hash 和所有事实/evidence span，再按 `fact_hash` 把完整事实物化到全局人物，并保留零事实人物、未绑定事实、冲突、review 与 cannot-link；
- `run_document_fact_group_assembly`：不调用模型；验证 registry/profile 的文档身份、人物归属、完整 raw fact hash、来源 artifact hash 和所有 span，再按最终人物与完整结构键生成稳定 canonical fact groups；
- `run_document_appearance_scope_assembly`：不调用模型；解析并折叠相邻重复章节标题，将每个 canonical fact 唯一绑定到章节和文档顺序，赋予保守 persistence，life/form/scene 暂时保持 unknown；
- `prepare_document_appearance_transitions`：不调用模型；直接验证并复用原 M1 Manifest 的重叠 Chunk，以 `chunk_id` 连接该 Chunk 下已绑定到最终人物簇的 local/promoted nodes，生成 Chunk 人物表；
- `run_document_appearance_transitions`：模型每个原 Chunk 只读取 `name + aliases + text`，返回最小 transition 语义与逐字 evidence；`chunk_id/hash/span` 留在代码信封。v3 代码门槛要求单段连续 evidence、同一 evidence 内逐字且有序的 before/after，排除没有身体变化的武魂/外物状态；生命阶段变化重置 form/scene，scene 在段落行或章节边界关闭，再执行绝对 span/character_id 回填、重叠 Chunk 去重、change 推导、稳定 transition ID、canonical fact state 投影和 StateSegment 物化；
- `build_appearance_semantic_projection`：不调用模型；只在同人物、同 StateSegment、同 exact attribute 内生成稳定 pair relation，以完全相等和安全子串规则分类，并只从 equivalent 连通分量派生 normalized propositions；
- `run_document_label_review_projection`：不调用模型；从最终 identity registry 派生正交 label kind/stability，完整保留历史 review，并只把最终图未关闭的问题投影到 actionable queue；
- `run_render_ready_character_profiles`：不调用模型；重新验证 fact/state/label 三层来源，以人物、life/form/scene 和 document position 唯一选择 StateSegment，区分 active/provisional applicability，再编译结构化 traits、相关 transitions、scope 内冲突、warnings 与 canonical/raw provenance；
- `DeepSeekProvider`：读取每个阶段请求自带的 schema name 和 response schema，M1/M2 共用同一套 HTTPS、重试、错误分类与脱敏 trace 实现。

### 5.8 文档级事实汇总

统一产物为 `document-character-evidence.json`。每条 `appearance_facts` 记录 `character_origin`、`character_label_quote`、结构化事实、`document_fact_span`、确定性的 `fact_hash` 和一个或多个 `source_occurrences`。每个来源 occurrence 保留 Chunk ID/hash/span、local 或 promoted character ref、原始 evidence quote、Chunk 局部 span 与换算后的文档 evidence span。

重叠去重键固定为：`character_origin + character_label_quote + fact_quote + document_fact_span + category + attribute + value`。因此，同一原文位置且结构完全相同的重叠副本会合并；不同人物、不同文档位置或不同结构解释不会因为 quote 相同而被误删。`fact_hash` 是完整文档事实身份的 hash，不是逐 quote hash。

M2 attribution 只生成已绑定的候选事实，不修改 N2 packet，也不从 describe 工作池删除字符。N3 只修改派生工作池；N2 packet、M1 模型输出和 M2 attribution 产物保持不可变。

## 6. N3：证据验证、describe 消费与循环

### 6.1 fact_quote 代码验证

N3 只接收已经由代码绑定来源的 `fact_quote`：

- `approved_target_evidence`：事实位于当前 exact 的 approved evidence，直接归并；
- `approved_describe_evidence`：事实唯一位于一个 describe evidence occurrence，进入跨 exact 仲裁；
- `ambiguous_fact_binding`：存在多个可匹配来源，不归并、不消费；
- `fact_not_in_allowed_evidence`：不在允许证据池中，拒绝。

完整 Chunk 只能帮助模型理解关系，不能把只存在于上下文、但不在允许 evidence 中的文字升级为外貌事实。

### 6.2 describe 归属汇总

N3 等待同一轮 E 个 exact 任务完成，再按代码回填的 describe source occurrence 和 fact span 汇总肯定事实。模型没有输出的内容视为“未认领”，不再要求模型逐项返回 `not_target` 或 `uncertain`。

仲裁和消费的最小单位是字符 span，不是整条 `evidence_quote`：

1. 某个 fact span 只有一个 exact 返回并通过绑定：标记 `consumed_unique`，事实归入该 exact；
2. 不同 exact 的 fact span 相同或重叠：标记 `conflicted`，不得消费；
3. 同一个 exact 的重复或重叠 fact 先确定性合并；
4. 同一 describe evidence 内，两个互不重叠的 span 可以分别归给两个 exact 并分别消费。
5. 没有 exact 成功认领的内容继续留在 describe 待处理池。

N2 先按 `exact-evidence-precedence-v1` 生成过滤后的不可变 packet；N3 这里的“删除”是从该 packet 派生的可变 describe 待处理池中消费对应原文 span，不再回写或修改已经物化的 N2 packet。M1 原始 model output 仍用于重放和纠错。

### 6.3 剩余 describe 重新进入 M2

N3 将没有被任何 exact 成功消费的原文 span 重建为 `remaining_evidence_fragments`。这些剩余内容不再重新交给全部 exact，也不再进行 exact 归属循环，而是按 describe 块分别进入 5.6 的“剩余 describe 独立建人”模式。

例如“红衣女子眉目清秀”中的“眉目清秀”没有被任何 exact 返回，N3 就保留该内容；M2 结合 `chunk_text` 将“红衣女子”解析成新的独立本地人物。

独立建人规则：

- 每个非空剩余 describe 池至少尝试建立一个本地人物；
- 一个池包含多个未被 exact 消费的人物时，模型可以拆成多个人物；
- 每条 `fact_quote` 只允许从剩余 evidence 安全绑定，已消费片段不得再次使用；
- `pool_hash + context_version + resolver_version` 形成稳定 `promotion_hash`，相同输入不得重复建人；
- exact 冲突区间不属于“未认领”，继续进入 review，不得借独立建人绕过冲突；
- 模型输出验证失败时进入 `promotion_review_required`，不得静默丢弃剩余人物。

代码侧消费结果仍保留内部来源和 span，例如：

```json
{
  "describe_source_ref": {
    "local_mention_id": "m2",
    "packet_hash": "..."
  },
  "consumed_fragments": [
    {
      "fact_quote": "眉目清秀",
      "assigned_target_local_mention_id": "m1",
      "fact_quote": "眉目清秀",
      "fact_chunk_span": {"start": 17, "end": 21},
      "source_evidence_quote": "红衣女子眉目清秀，旁边老人须发皆白",
      "source_evidence_span": {"start": 13, "end": 31},
      "status": "uniquely_assigned"
    }
  ],
  "remaining_evidence_fragments": [
    {
      "source_evidence_quote": "红衣女子眉目清秀，旁边老人须发皆白",
      "source_evidence_span": {"start": 13, "end": 31},
      "fragment_quote": "旁边老人须发皆白",
      "fragment_span": {"start": 22, "end": 31}
    }
  ],
  "next_action": "promote_remaining_describe"
}
```

## 7. 跨 Chunk 人物身份层（M3）

### 7.1 完整局部人物目录

代码先把所有 N3 exact target 和所有安全 promotion 物化为 `document-local-character-nodes.json`。即使某个 exact 暂时没有外貌事实，也必须保留其局部人物节点，避免身份层只看见“有外貌的人”。每个节点保留原有 `local_character_ref` 或 `promoted_character_ref`、来源 Chunk、已有 `fact_hash` 引用和用于模型阅读的原文上下文。这里的 hash、ref、span 全部属于代码侧，模型不可见。

候选检索只使用弱信号缩小范围：同一 exact 标签、标签包含关系、可能的姓名字形变体、相同事实原文，以及近距离原文中的显式介绍措辞（例如“我叫”“这位是”“正是”）。弱信号绝不直接合并。默认每个当前节点最多保留 2 个候选。确定性 same edge 仅有两种来源：两个局部节点共同引用同一个文档事实 `fact_hash`；或满足 7.1.1 全部约束的局部共指闭合。当前全局唯一姓名、同名、字形相似、外貌相似和单纯距离接近都不能建立确定性身份边。

### 7.1.1 局部确定性身份闭合

`grounded-local-coreference-v1` 只处理已有局部原文已经完整陈述身份关系、但 M3 候选边未覆盖的闭合漏项。新边必须同时满足：

1. 左节点是 `describe`，右节点是 `exact`，且两者来自同一 Chunk；
2. 身份证据完整位于双方 `context_quotes` 的文档绝对 span 交集内，并可从原文和双方上下文逐字回放；
3. 原文明确构成同位、示指命名或连续局部共指关系；问句、否定句或只有姓名共现均拒绝；
4. 证据 span、原文 quote、关系类型和策略版本进入独立 deterministic-edge 审计产物；
5. 新边进入现有全局 identity 图后仍服从 cannot-link，冲突时失败关闭；
6. 不以 `proper name + global unique`、最终簇唯一或全局搜索结果创建边。

例如，连续原文 `高大的身影 -> 中年男子 -> 这就是唐昊` 可以建立 `高大的身影 -> 唐昊`；若只有两个远距离的“唐昊”标签或一段询问“这是唐昊吗”，则不能建立边。

### 7.2 M3 模型输入

一个模型任务只比较当前局部人物与一个候选人物。输入没有 `node_key`、人物 ref、span、hash、cache key 或 `character_id`：

```json
{
  "current_character": {
    "label_quote": "熏儿",
    "label_type": "exact",
    "context_quotes": ["少女走到萧炎身旁，萧炎唤她熏儿。"],
    "appearance_fact_quotes": ["美丽的眼睛"]
  },
  "candidate_character": {
    "known_labels": ["萧熏儿"],
    "context_quotes": ["萧熏儿微微一笑。"],
    "appearance_fact_quotes": ["修长的睫毛"]
  },
  "bridge_context_quotes": ["萧熏儿走近，萧炎随后唤她熏儿。"]
}
```

`bridge_context_quotes` 优先提供两个上下文的完整并集。并集过长但两个上下文之间的原文间隔仍在上限内时，改为在总预算内优先保留间隔末段和后一上下文之后的过渡，并在仍有预算时补充前侧窗口；这可覆盖章节切换、转生说明或紧随其后的自我介绍，而不会把整个大段 Chunk 塞给模型。外貌相似、同名、职位相同或距离接近都不能单独证明同一人物；外貌不同也不能单独证明是不同人物。

### 7.3 M3 模型输出

模型只输出关系与证明关系的原文：

```json
{
  "identity_relation": "same_character",
  "label_relation": "alias",
  "identity_evidence_quotes": ["萧炎随后唤她熏儿"]
}
```

- `same_character`：必须给出 `label_relation` 和至少一条身份原文；
- `different_characters`：`label_relation` 必须为 `null`，并且必须给出明确区分两人的原文；
- `uncertain`：`label_relation` 为 `null`，证据数组为空；
- `label_relation` 只允许 `same_surface`、`name_variant`、`alias`、`title`、`contextual_description`、`unknown`；
- `identity_evidence_quotes` 必须从模型可见上下文连续逐字复制，不能概括、改写或拼接。

### 7.4 Grounding 与失败关闭

代码把每条身份引用在所有模型可见 context 中匹配。严格匹配失败时，仅允许删除 Unicode 空白后字符完全一致的恢复；任何非空白字符变化都拒绝。重叠 context 指向同一文档绝对位置时只算一次；同一 quote 若对应多个不同文档 occurrence，则标记 `ambiguous_identity_evidence`，不猜位置。

只要至少一条身份引用唯一 Grounding，same/different 可保留，其他歧义引用单独进入 issue；若没有任何引用安全 Grounding，则整条关系降为 `uncertain`。这与 promotion 的“部分接受”原则一致。

### 7.5 全局人物档案

全部任务完成后，代码使用 union/cannot-link 约束生成 `document-character-registry.json`：

- `character_id` 是基于来源版本、身份策略和最早成员节点生成的 opaque ID，不由姓名直接生成；
- `member_character_refs` 保存并映射原有 local/promoted ref；
- `labels` 记录 name、name_variant、alias、title、contextual_description 或 unknown；泛称和 title 默认不声明全局唯一；
- `appearance_fact_refs` 引用 `document-character-evidence.json` 已有的 `fact_hash` 与原文，不再创建逐 quote hash；
- 同一属性出现多个值时全部保留，并在 `possible_conflicts` 中记录，不静默覆盖；
- 明确的 `different_characters` 形成 `cannot_link_constraints`，阻止传递合并；
- 所有已经 Grounding 的 same edge 先进入全局图；代码以 cannot-link 为硬约束，稳定地合并所有不会产生冲突的连通分量，不再因逐节点处理顺序把同一连通图的多个入口误报为 `multiple_same_character_candidates`；
- 证据不足或 same edge 被 cannot-link 阻断时进入 `unresolved_bindings` / `review_items`。未决局部节点仍作为 singleton 出现在注册表中并保留其事实，但不得与候选人物猜测合并。

M3 支持按 `task_cache_key` 断点续跑。保存的模型输出在恢复时重新执行当前 Grounding，完整成功后才写统一人物注册表。

### 7.6 残余 cluster-level 裁决

真实运行仍可能留下 pair 任务无法解决的别名或时间跨度问题。补救节点只接收确定性全局聚合后的残余 unresolved，一次展示当前人物和少量候选人物簇；它复用已保存的 M3 结果，不默认重跑全部 M3。

模型输入中的 `current_character.context_quotes`、候选的 `context_quotes` 和双方的 `appearance_fact_quotes` 只帮助理解人物。每个候选另有独立的 `relationship_context_quotes`，其中必须包含来自原文、可能支撑双方身份关系的连续上下文。模型选择候选时只输出本任务内的 `candidate_number`；该序号不是人物 ID，代码负责回填真实 cluster 和 anchor node。

```json
{
  "current_character": {
    "labels": ["小三"],
    "context_quotes": ["小三，你过来。"],
    "appearance_fact_quotes": []
  },
  "candidate_characters": [
    {
      "candidate_number": 1,
      "known_labels": ["唐三"],
      "context_quotes": ["唐三点了点头。"],
      "appearance_fact_quotes": [],
      "relationship_context_quotes": ["杰克对唐三道：小三，你过来。"]
    }
  ]
}
```

输出仍只有关系、候选序号、标签关系和身份证据：

```json
{
  "identity_relation": "same_character",
  "candidate_number": 1,
  "label_relation": "alias",
  "identity_evidence_quotes": ["杰克对唐三道：小三，你过来。"]
}
```

Grounding 有意采用更窄的证据域：`identity_evidence_quotes` 只能从所选候选的 `relationship_context_quotes` 中连续逐字复制，不能从普通 `context_quotes` 或外貌事实中取证，也不能引用另一个候选的关系上下文。代码仅在该候选的关系绑定内查找，并要求唯一严格匹配；严格匹配失败时只允许纯空白等价恢复。引用仅是人物标签、少于 6 个非空白字符、出现于多个不同绝对位置、改写或拼接时，关系降为 `uncertain`。任何结果都必须继续服从 cannot-link 硬约束。

若代码找不到任何候选专属关系上下文，则不创建模型任务，继续保留 unresolved，避免让模型用作品常识或相似外貌猜测。该节点支持按 `task_cache_key` 断点续跑，模型输出在恢复时重新 Grounding，全部任务成功后把安全关系作为 supplemental decisions 重建注册表。

### 7.7 文档人物档案组装

`document-character-profiles.json` 是纯代码生成的最终结构化档案。构建器先要求 `document-character-registry.json` 与 `document-character-evidence.json` 的 `source_document_version_id` 和 `document_hash` 完全一致，再建立 `fact_hash -> DocumentAppearanceFact` 索引。人物只能通过 registry 的 `appearance_fact_refs[].fact_hash` 取得完整事实，禁止按姓名、别名或 quote 猜测连接。

每个全局人物保留 `character_id`、身份状态、主标签、全部标签、成员 local/promoted ref、按绝对位置排序的完整 `appearance_facts`、冲突和相关 `review_item_ids`。每条完整事实继续保存事实原文、结构化属性、文档绝对 span 与全部来源 Chunk occurrence。顶层保存未绑定事实、未决绑定、完整 review 和 cannot-link，避免在档案物化时丢失失败或待复核信息。

构建时执行以下失败关闭检查：

- 两个来源文件或输入正文不属于同一文档版本/hash；
- evidence 出现重复 `fact_hash`，或完整事实字段无法重算出该 hash；
- registry 引用不存在的 hash，或同一 hash 被多个全局人物占用；
- registry 的 `fact_quote` 与 evidence 不一致；
- 事实、证据、Chunk 的绝对/局部 span 或 Chunk hash 无法逐字回放；
- 人物冲突引用了该人物之外的事实。

没有外貌事实的人物仍输出 `appearance_facts: []`。没有被任何全局人物引用的事实进入 `unassigned_appearance_facts`，不得静默删除。本阶段不调用模型，不生成自然语言画像，也不推断性别、年龄或性格。

### 7.8 Post-link canonical fact groups

`document-character-fact-groups.json` 是 `document-character-profiles-v1` 之后的独立结构层。`fact_hash` 继续表示不可变 raw evidence fact；新层使用独立的 `canonical_fact_id`，分组键固定为：

```text
character_id
+ document_fact_span
+ category
+ attribute
+ value
```

因此，同一人物在身份归并后由多个 local/promoted mention 重复物化的同结构事实会进入一个 group；同 span 不同 `attribute`、不同 `value`、不同人物或不同 span 均保持独立。本层不判断同义、包含、状态变化或真假冲突，`scope_assignment_status` 固定为 `unassigned`，后续状态层再处理 scope。

每个 group 保存原文 `fact_quote`、稳定 span、全部 `source_fact_hashes` 和全部 occurrence bindings。每个 occurrence binding 同时记录 `source_fact_hash`、该 raw fact 内的 `source_occurrence_index` 和完整 occurrence，从 canonical fact 可以无损回到 raw fact、Chunk、证据原文和绝对位置。零事实人物继续出现在 `characters` 索引中；未分配 raw facts/occurrences 另存引用，不因无法建立 character group 而丢失。

构建器验证 registry/profile 同文档、人物集合与逐人物 fact ownership 完全一致，重算 raw `fact_hash`，回放 fact/evidence/Chunk span 与 Chunk hash，并核对 profile summary 和 source artifact hash。任一不一致都失败关闭。输入 registry/profile 只读，Provider 调用为 0。

### 7.9 Grounded transition 与派生 StateSegment

M1/N2/M2/N3 的职责和模型边界在当前主线冻结；“冻结”不等于它们的模型质量已完成 075 人工 Gate。071 之后不再向前半段追加全局状态字段，而由 identity registry、canonical fact groups 和 `document-character-appearance-states-v5` 分层承载身份、事实与状态。

最终 Grounded Transition 由代码根据来源版本、transition 策略及完整 grounded 内容生成稳定 `transition_id`。`StateSegment` 不调用模型，也不是独立可编辑真相源；它按每个人物的 document start/end、transition effective position 与 scene expiry 把全文分成连续半开区间。每个区间保存 `life/form/scene`、起止 boundary 原因、相关 transition 引用和 `observed_fact_ids`。同位置事件合并为一个 boundary，并固定按 life → form → scene → appearance 应用；life 清空旧 form/scene，旧 scene expiry 不能清除更晚建立的 scene。

每个 canonical fact 只按 `document_fact_span.start` 进入一个 `observed_fact_ids`，事实内容、persistence 与 raw provenance 仍留在既有 fact group/assignment 层。`observed` 不等于“当前仍有效”；跨区间持续的 `active_fact_ids` 或 applicability 只能由 074 根据 persistence、关系图和选择器另行派生。零事实人物仍有一个覆盖全文的 `unknown` segment。

072 已先在 `character_id + state_segment_id + exact attribute` 内建立保留原值和方向的 relation graph，再由 `equivalent` 连通分量派生 normalized proposition；不得先覆盖原值再反推关系。确定性规则只把完全相同值判为 `equivalent`、长度至少 2 的安全子串判为有方向的 `compatible`，其他 pair 保守为 `unclassified`。斗罗 dev24 的 109 个 observations 形成 37 条关系（7 equivalent、5 compatible、25 unclassified）与 103 个 propositions，新增语义模型调用为 0。没有 active applicability 时不会生成 `true_conflict`。Registry 的 `appearance_fact_refs` 继续是身份到事实的归属边，ProfileView/render profile 只作为可重建视图。`label_kind` 与 `label_stability` 在 073 保持正交；当前 `character_id` 不可在缺少稳定 subject identity 或迁移协议时直接作为永久外部视觉资产键。

### 7.10 Label 与 Review 派生视图

`document-character-label-review-projection-v1` 只读取最终 `document-character-registry-v1` 和对应原文 hash，不修改 Registry。每个来源标签保留 `label_quote/source_label_role/source_globally_unique`，新增正交 `label_kind` 与 `label_stability`。确定性首版支持 proper name、alias、title、relationship label、descriptive label 与 unknown；稳定性独立为 stable、contextual、temporary 或 unknown。Preferred label 按语义类型、稳定性和来源 canonical label 的固定顺序选择。

Review 投影不删除旧项。每个 Registry review 一对一进入 `audit_items`，原 `status=pending` 保存为 `source_status`；最终人物簇相同则标 `resolved_same_character`，最终 cannot-link 全覆盖则标 `resolved_different_characters`，仍在 `unresolved_bindings` 或无法证明关闭时进入 `actionable_review_items`。精简 actionable 队列只保存工作所需引用，完整 Grounding 证据仍在对应 audit item。

斗罗 dev25 的 7 个人物和 17 个标签得到 3 个 title，其中来源仍为 `name` 的“大师”被安全投影为 `title + stable`。9 个历史 review 全部保留；8 个已由最终同人簇关闭为 `resolved/audit_only`，1 个“看门的青年”保持 actionable。该步骤模型调用为 0。

### 7.11 Render-ready Profile Compiler

`render-ready-character-profiles-v1` 读取完整 fact groups、appearance states、Label/Review projection 与 `render-profile-compile-requests-v1`。每个请求显式给出 `character_id`、life/form/scene 条件和 `document_position`；只有唯一命中一个半开 StateSegment 才编译 traits。缺少位置、多个候选或无匹配均输出空 traits 和机器可读 warning，不跨时期或形态拼接。

Applicability 与 observation 分层。事实必须先于选择位置出现；stable 沿连续同 life/form 路径生效，persistent-until-changed 还受同 attribute appearance transition 截止，momentary 只在 fact span 内生效。scene 的章节上界和 unknown persistence 都只能产生 provisional，输出同时维护 `active_fact_ids` 与 `provisional_fact_ids`。Trait 仍引用 072 proposition 和所有参与的 canonical fact；provenance 逐 fact 保存 raw hash、document span 与全部 source occurrence。

`unresolved_conflicts` 只接受两侧均为确定 active 的 `true_conflict`。一侧 provisional 的 true conflict 降为 warning；active/provisional 的 `unclassified` 也只保留 warning，不被强制解释。斗罗 dev26 的四个 selector 均完成编译，共 7 active、40 provisional fact bindings，0 unresolved conflicts、17 聚合 warnings，Provider 调用为 0。该结果是结构化编译 Gate，不等于自然语言 Prompt、视觉一致性或人工质量 Gate。

## 8. V3 完成门槛

V3 设计完成不等于运行时完成。进入人物识别阶段前至少需要：

1. M1/N2/M2/N3 DTO 与 JSON Schema 一致；
2. M1 输出 type、scope、人物提及块和原文 evidence，不输出外貌字段；
3. 人物称谓不输出 occurrence 数量或 span；N2 对 type、scope、mention/evidence 做确定性验证，并以 versioned exact precedence 删除 describe 同文副本和空块；collective 不得进入单人物 promotion；
4. 第一轮每个 individual exact 生成一个携带全部 individual describe 块的 M2 任务；所有 individual describe 先由所有 exact 分别判断；
5. 所有模型阶段都分离代码信封、模型输入、模型输出和代码回填，模型不处理来源版本、Chunk ID、hash、cache key 或 trace；
6. M2 模型输入输出不含 ref、span、归属状态或 epistemic 状态；代码以 `fact_quote` 安全且唯一匹配后回填来源和 span；
7. N3 以代码回填的 Chunk fact span 为最小单位完成唯一认领、非重叠独立消费、冲突保留和剩余池重组；
8. 每个剩余 individual describe 池单独进入 M2 独立建人，生成经过证据验证的 `promoted_character_ref` 和外貌事实；collective 池不进入此步骤；
9. `packet_hash`、`task_cache_key`、`pool_hash` 与 `promotion_hash` 不依赖 run ID，重跑稳定；
10. 原始 UTF-8、Unicode code-point offset、半开区间和禁止隐式文本归一化规则有确定性测试；
11. 建立最小真实 Chunk shadow 数据集并由用户审核；
12. M3 候选数有明确上限；同名、相似名称和相似外貌只能触发候选，不能自动合并；
13. same/different 必须经过严格或纯空白等价的原文 Grounding，多 occurrence 不猜测；
14. 全局 ID、ref 回填、冲突保留、cannot-link、unresolved/review 均由确定性代码生成；
15. 人物档案只按同文档 `fact_hash` 连接；缺失、冲突、重复占用和 span 回放失败均失败关闭，零事实人物与未绑定事实保留；
16. 局部确定性身份边只能来自双方共享局部上下文中的可回放显式关系，不能以全局唯一姓名自动 join，并必须继续受 cannot-link 约束；
17. Post-link canonical fact groups 必须使用包含 `attribute` 的完整结构键，保留全部 raw fact hash 与 occurrence binding，并且不得改写 raw profiles；
18. Grounded Transition 必须有稳定 ID；StateSegment 必须连续覆盖每个注册人物、由确定性输入重建，并让每个 canonical fact 恰好出现于一个 `observed_fact_ids`；
19. 072 必须先形成 segment-aware relation graph，再只从 equivalent 连通分量派生 normalized proposition；compatible/unclassified 不得触发合并，observation binding 与 active applicability 必须分层；
20. Label/Review 投影必须保留来源标签语义和全部历史 review；`label_kind` 与 `label_stability` 正交，actionable 队列只能由最终人物图和 unresolved 状态确定；
21. Render compiler 必须以 character/state/document position 唯一选择 StateSegment，区分 active/provisional applicability，禁止未来 observation 和跨 life/form 混合，并把每个 trait 回溯到 canonical fact 与 raw occurrence；
22. 真实模型身份精度需通过人工标注数据集评测，不能由“批处理完成”替代。

## dev29 派生快照接口

R03/R04 的 `CharacterSnapshot`、有效期证据事件、旧 render adapter 和查询边界见 [40 契约](40-character-snapshot-and-applicability.md)。这是代码侧派生视图；M1/M2/M3 模型 payload 不变，自动场景/换装语义发现仍待实施。
