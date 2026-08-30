# 简化人物证据流水线 V3 契约

> 状态：新项目目标契约草案；用于 `v3-simplified-character-evidence` 分支。当前分支不包含旧版实现、评测或提示词。人物记忆与 `local_character_ref -> character_id` 的具体策略留待后续独立设计。

## 1. 目标

V3 优先建立一条容易解释和验证的三段流水线：

```text
M1：识别人物提及，标记 exact / describe / null，并归拢相关外貌原文
  ↓
N2：只用代码验证人物称呼和外貌原文确实存在于 Chunk
  ↓
M2：以一个 exact 人物为目标；每个 describe 分别与每个 exact 组合解析
  ↓
N3：验证证据、汇总 describe 归属、消费已唯一归属片段并回送剩余 describe
```

本契约不要求 N2 判断跨人物证据冲突。同一段 `evidence_quote` 可以同时出现在多个提及块中。只有 `exact` 提及可以作为 M2 的目标人物；`describe` 只是待归属的描述证据池，不得直接当成一个独立人物。

## 2. 稳定来源身份

每个输入 Chunk 至少保留：

- `source_document_version_id`：小说来源版本；
- `chunk_id`：同一来源版本和分块规则下稳定；
- `chunk_hash`：Chunk 正文的内容哈希；
- `chunk_text`：本次处理的完整正文。

`chunk_id` 不能单独证明内容未变化。来源版本、分块规则或正文变化时，必须生成新的来源/Chunk 版本关系。

## 3. M1：局部候选人物与证据归拢

### 3.1 唯一职责

M1 从一个 Chunk 中识别人物提及表达，并把模型认为与该提及有关的连续原文证据放进同一个结构块，同时输出 `mention_type`。

M1 不做字段分类、外貌原子化、跨 Chunk 身份、时间作用域、持续性或人物记忆写入。

### 3.2 模型输入

```json
{
  "chunk_id": "chunk-001",
  "chunk_text": "青衫老者身形高瘦，留着花白胡须。白衣女子眉目清秀。"
}
```

### 3.3 模型输出

```json
{
  "chunk_id": "chunk-001",
  "candidate_mentions": [
    {
      "mention_type": "describe",
      "mention_quote": "青衫老者",
      "evidence_quotes": [
        "青衫老者身形高瘦，留着花白胡须"
      ]
    },
    {
      "mention_type": "describe",
      "mention_quote": "白衣女子",
      "evidence_quotes": [
        "白衣女子眉目清秀"
      ]
    }
  ]
}
```

JSON 中同名字段不能重复，因此一个人物的多条证据必须放在 `evidence_quotes` 数组中。

`local_mention_id` 不由模型生成。服务端按验证后的数组顺序物化为 `m1`、`m2` 等 Chunk 局部提及编号。只有 `mention_type=exact` 的块可以进一步形成 `local_character_ref`；`describe` 和 `null` 块都不是独立人物。

没有任何人物称呼、只能发现人物相关证据时，进入 `null` 块：

```json
{
  "mention_type": null,
  "mention_quote": null,
  "evidence_quotes": ["只见一双手苍白瘦削"]
}
```

### 3.4 mention_type 判定

`mention_type` 只有三种值：

- `exact`：`mention_quote` 是明确人物名称，例如“张三”“林黛玉”“唐三”。只有这类提及可以作为确切目标人物。
- `describe`：`mention_quote` 只是泛称、身份描述或外貌描述，不能唯一指向一个人物。例如“人”“老者”“老人”“女孩”“少女”“男人”“女子”“女人”“红衣女子”“月袍老人”“青衫老者”“白衣女子”都属于 `describe`。
- `null`：原文证据里没有可抽取的人物称呼，此时 `mention_quote` 必须为 JSON `null`，不是字符串 `"null"`。

判定优先看提及本身是否含有明确人物名称。单纯由颜色、衣着、年龄、性别、职业、身份或人物类别词组成的短语一律是 `describe`，不能因为描述很具体就升级为 `exact`。

### 3.5 describe 泛称后缀规则

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
2. 提及是已经识别出的最小明确人物名称时结果为 `exact`；
3. 否则只要命中泛称后缀表，就强制归一为 `describe`；
4. 其余提及保留 M1 的语义分类，等待评测完善后缀表。

M1 应优先拆成最小提及，避免把名字和泛称粘成一个块。例如“林黛玉这女子”应拆出 exact“林黛玉”和 describe“这女子”；相关 evidence 允许同时进入两个块。若模型将“红衣女子”错误标为 `exact`，N2 代码归一为 `describe` 并记录 `mention_type_normalized_by_suffix` trace，不直接丢弃其 evidence。

## 4. N2：最小确定性原文验证

### 4.1 验证范围

N2 只做来源存在性和结构验证：

1. `chunk_id` 与执行请求一致；
2. `mention_type` 只能是 `exact`、`describe` 或 JSON `null`；
3. `mention_type=null` 时 `mention_quote` 必须为 `null`；另外两类必须为非空字符串；
4. 使用 `describe-suffix-v1` 复核并归一 mention type，归一必须写 trace；
5. 非空 `mention_quote` 必须存在于 `chunk_text`；
6. 每条 `evidence_quote` 必须存在于 `chunk_text`；
7. 记录每条引文的出现次数、位置和哈希；
8. 同一提及块内完全相同的 evidence 去重；
9. 无效 evidence 单独拒绝，不因一条无效 evidence 丢弃该块内其他有效 evidence。

### 4.2 有意不做

- 不判断同一 evidence 是否同时属于两个人物；
- 不阻止同一 `evidence_quote` 出现在多个人物块；
- 不做跨 Chunk 人物身份合并；
- 不判断外貌字段或语义是否正确。

跨提及重复证据被视为允许的 M1 提案。N2 不负责判断 `describe` 属于哪个 `exact` 人物。

### 4.3 approved_evidence

`approved_evidence` 就是 N2 已确认存在于当前 Chunk 的 M1 `evidence_quote`。

```json
{
  "chunk_id": "chunk-001",
  "grounded_mentions": [
    {
      "local_mention_id": "m1",
      "mention_type": "describe",
      "mention_quote": "青衫老者",
      "approved_evidence": [
        {
          "evidence_quote": "青衫老者身形高瘦，留着花白胡须",
          "occurrence_count": 1,
          "source_spans": [{"start": 0, "end": 19}],
          "quote_hash": "..."
        }
      ],
      "packet_hash": "..."
    }
  ],
  "rejected_evidence": []
}
```

只要一个提及块至少保留一条 approved evidence，就可进入后续组包。但 `describe` 不能单独作为 M2 目标；`null` 本轮不参与 exact×describe 组合。

### 4.4 Chunk 元数据索引

N2 验证后，由代码在 Chunk 元数据中生成可重建索引：

```json
{
  "candidate_mentions": {
    "m1": {"mention_type": "exact", "packet_hash": "...", "status": "grounded"},
    "m2": {"mention_type": "describe", "packet_hash": "...", "status": "grounded"}
  }
}
```

`packet_hash` 是局部提及证据包的指纹，不是正式人物 ID。哈希输入包括来源版本、Chunk 身份、mention type、mention quote 和已批准 evidence 的规范化内容与位置；不包含 `run_id`。

## 5. M2：exact 目标与 describe 证据池组合解析

### 5.1 调用单位

设当前 Chunk 有 E 个 `exact` 块、D 个 `describe` 块。代码生成：

1. E 个 exact 自身证据解析任务；
2. E × D 个“一个 exact 目标 + 一个 describe 证据池”归属解析任务。

因此每个 `describe` 都会分别与每个确切人物进入 M2，不能提前只选一个人物，避免漏掉真正归属。不同组合可以并行执行。

- `describe` 没有自己的 `local_character_ref`，不能独立产出人物事实。
- Chunk 没有 `exact` 时，`describe` 暂存为 unresolved，不启动人物归属 M2。
- `mention_type=null` 本轮不参与 exact×describe 组合，单独保留 trace。

### 5.2 输入

```json
{
  "target_character_ref": {
    "source_document_version_id": "novel-v1",
    "chunk_id": "chunk-001",
    "local_mention_id": "m1",
    "mention_type": "exact",
    "packet_hash": "..."
  },
  "target_mention_quote": "林黛玉",
  "target_approved_evidence_quotes": [
    "林黛玉换上红衣，走进屋中"
  ],
  "describe_source": {
    "local_mention_id": "m2",
    "mention_type": "describe",
    "mention_quote": "红衣女子",
    "packet_hash": "...",
    "available_evidence_fragments": [
      {
        "source_evidence_quote": "红衣女子眉目清秀，身形纤细",
        "fragment_quote": "红衣女子眉目清秀，身形纤细"
      }
    ]
  },
  "resolution_round": 1,
  "chunk_text": "林黛玉换上红衣，走进屋中。红衣女子眉目清秀，身形纤细。"
}
```

`describe_source=null` 表示只拆解 exact 自己的 approved evidence。非空时，M2 必须逐条判断 describe 片段是 `belongs_to_target`、`not_target` 还是 `uncertain`。

`chunk_text` 只辅助理解。模型不能从完整 Chunk 随意补证据；exact 自身事实必须来自 `target_approved_evidence_quotes`，describe 归属事实必须来自当前 `available_evidence_fragments`。

### 5.3 输出

```json
{
  "target_character_ref": {
    "source_document_version_id": "novel-v1",
    "chunk_id": "chunk-001",
    "local_mention_id": "m1",
    "mention_type": "exact",
    "packet_hash": "..."
  },
  "target_appearance_facts": [],
  "describe_source_ref": {
    "local_mention_id": "m2",
    "packet_hash": "..."
  },
  "describe_evidence_assessments": [
    {
      "source_evidence_quote": "红衣女子眉目清秀，身形纤细",
      "fragment_quote": "红衣女子眉目清秀，身形纤细",
      "attribution_status": "belongs_to_target",
      "claimed_evidence_quote": "红衣女子眉目清秀，身形纤细",
      "appearance_facts": [
        {
          "category": "face",
          "attribute": "眉目",
          "value": "清秀",
          "support_quote": "眉目清秀",
          "epistemic_status": "asserted"
        }
      ]
    }
  ]
}
```

`claimed_evidence_quote` 是模型认为属于 exact 目标的最小连续原文片段，必须位于 `fragment_quote` 中；每条 `support_quote` 又必须位于 `claimed_evidence_quote` 中。这样一句 evidence 同时描写两个人时，N3 只消费已分清的片段，不会整句删除。

`not_target` 和 `uncertain` 不得输出 `claimed_evidence_quote` 或 appearance facts。M2 不返回稳定 fact ID，不修改目标引用，不写入人物记忆。

## 6. N3：证据验证、describe 消费与循环

### 6.1 事实证据三态验证

N3 仍对每条 `appearance_fact.support_quote` 执行三态验证：

- `approved`：exact 自身事实位于目标的 approved evidence；或 describe 事实位于经过验证的 `claimed_evidence_quote`，且 claimed quote 位于该 describe 的 approved evidence 片段。
- `review_context_only`：证据只存在于完整 Chunk，但不在本次允许的 exact/describe 证据范围内。不能直接批准，写入 trace。
- `rejected_hallucination`：证据连完整 Chunk 都不存在，拒绝并写入 trace。

### 6.2 describe 归属汇总

N3 必须等待同一轮中某个 describe 片段与全部 exact 目标的 M2 结果，再按原文 span 汇总：

1. 只有一个 exact 对该片段给出通过证据校验的 `belongs_to_target`：将该片段标记为 `consumed_unique`，事实归入该 exact 人物。
2. 两个或更多 exact 对同一片段给出 `belongs_to_target`，或不同 claim span 互相重叠：标记 `conflicted`，不得消费，进入 review/下一轮。
3. 没有 exact 成功认领：片段继续留在 describe 待处理池。
4. `not_target` 和 `uncertain` 永远不能触发证据消费。

这里的“删除”是从可变的 describe 待处理池中消费对应原文 span，不是删除 N2 的原始 `approved_evidence`。N2 包必须保持不可变，用于审计、重放和纠错。

### 6.3 剩余 describe 重新进入 M2

N3 将未消费的原文 span 重建为 `remaining_evidence_fragments`，再次与每个 exact 目标进入 M2。必须同时具备循环保护：

- 本轮至少消费了一个片段，或者 exact 候选集合/可用上下文发生变化，才允许自动重跑；
- `pool_hash` 与上一轮相同即视为无进展，停止自动循环并标记 `defer_unresolved`；
- 设置 `resolution_round` 上限，超过上限进入人工 review；
- 已消费片段不得再次进入后续 M2。

示例消费结果：

```json
{
  "describe_source_ref": {
    "local_mention_id": "m2",
    "packet_hash": "..."
  },
  "consumed_fragments": [
    {
      "claimed_evidence_quote": "红衣女子眉目清秀",
      "assigned_target_mention_id": "m1",
      "status": "consumed_unique"
    }
  ],
  "remaining_evidence_fragments": [
    {
      "source_evidence_quote": "红衣女子眉目清秀，旁边老人须发皆白",
      "fragment_quote": "旁边老人须发皆白"
    }
  ],
  "next_action": "requeue_m2"
}
```

## 7. 后续人物识别接口占位

V3 当前只冻结最小引用：

```json
{
  "local_character_ref": {
    "source_document_version_id": "novel-v1",
    "chunk_id": "chunk-001",
    "local_mention_id": "m1",
    "mention_type": "exact",
    "packet_hash": "..."
  },
  "character_id": null,
  "identity_status": "unresolved"
}
```

后续人物记忆只通过版本化的 `local_character_ref -> character_id` 绑定接入。绑定策略、人物创建、别名、代词、合并与拆分规则不在本契约中决定。

## 8. V3 完成门槛

V3 设计完成不等于运行时完成。进入人物识别阶段前至少需要：

1. M1/N2/M2/N3 DTO 与 JSON Schema 一致；
2. M1 输出 `exact/describe/null`、人物提及块和原文 evidence，不输出外貌字段；
3. N2 对 mention type、mention/evidence 做确定性验证并允许跨提及重复 evidence；
4. 每个 describe 与每个 exact 都生成 M2 组合任务，describe 不被当成独立人物；
5. M2 输出 describe 归属状态、最小 claimed evidence 和外貌事实；
6. N3 完成三态证据验证、唯一认领、冲突保留、片段消费、剩余池重组和无进展停止；
7. `packet_hash` 与 `pool_hash` 不依赖 run ID，重跑稳定；
8. 建立最小真实 Chunk shadow 数据集并由用户审核；
9. 不产生 active 人物事实或正式人物记忆写入。
