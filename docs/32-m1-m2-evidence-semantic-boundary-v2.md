# M1/M2 v2：证据发现与局部语义解析边界

> 决策状态：已确认；M1 v2 已按用户批准带残余风险进入条件 Gate，N2 v2 确定性纵向切片已实现，M2 v2 仍为目标协议。
>
> 设计基线：`semantic-pipeline-v2-design-v1.3`
>
> 兼容性：这是 M1/N2/M2 的破坏性协议升级。legacy M1/N2/M2 v1 仍保留给旧链；M1 v2 通过独立模块并行运行，旧 Prompt、数据集和 5/6 结果只保留为历史证据。

当前 M1 v2 入口：`application/ports/visual_evidence.py`、`infrastructure/llm/visual_evidence.py`、`application/services/visual_evidence_service.py`。主 Prompt 已按用户决定回退为 `visual-evidence-discovery-prompt-v2.8`；v2.9 的运行结果与失败保留为历史证据，不改写为通过。005 的非唯一逐字引文和少年脸貌漏召回是用户批准的残余风险，只授权继续 N2 工程开发，不授权 active Observation 或持久化。

Source Match Policy `visual-evidence-source-match-policy-v2` 只忽略 Unicode whitespace。候选的全部非空白字符和标点必须与 Chunk 同序一致，归一化后必须唯一匹配；通过后系统将候选替换为 Chunk 原始连续切片再计算输出指纹。文字改写、标点变化或归一化后多重匹配仍失败关闭。

## 1. 决策

M1 只负责从每个有效 Chunk 中召回可能包含人物视觉信息的连续原文证据，并在局部 owner 明确时给出原文锚点。M1 不再输出 `raw_proposition`、`coarse_family/coarse_families`、`epistemic_status`、显式时间信号或 unresolved 语义分类，也不按 face/body/clothing 或精确字段提前拆分事实。

M2 消费 N2 已定位的 evidence candidates，统一完成局部语义原子化、载体绑定、规范字段、源语言值、认知状态和原文明示信号的解析。M2 不能改变局部 owner，不能使用候选证据之外的信息补事实，也不能决定跨 Chunk 身份、时间作用域、持续性或 Promotion。

```text
M1：哪里有相关原文
  ↓
N2：原文证据是否真实、唯一、可定位
  ↓
M2：这段原文具体表达了什么
```

## 2. 为什么调整

v1 同时要求 M1：发现视觉内容、拆成独立 facts、选择 coarse family、判断 epistemic、识别显式信号；M2 又对 grounded facts 做语义单元拆分和字段映射。两层都承担事实原子化，形成职责重叠。

真实样本“男子年龄在二十左右，英俊的相貌，配上挺拔的身材”暴露了该问题：M1 v1 完整保留了年龄、脸和身材语义，却因没有单独输出 `body` fact 被判失败；而 M2 的核心职责本来就是把一个复合证据拆成多个 semantic units。因此 v2 不再把“完整复合证据未在 M1 分类拆开”视为 M1 漏召回。

只有候选引文或其 owner 绑定完全漏掉某段视觉证据，才是 M1 v2 召回失败。

## 3. 阶段职责

| 阶段 | 唯一职责 | 明确不负责 |
|---|---|---|
| M1 | 视觉相关连续证据召回；可选局部 owner 锚点 | 分类、事实原子化、命题改写、epistemic、显式信号、字段、身份、时间范围 |
| N2 | 引文定位、span/hash、上下文、稳定 ID、去重和结构失败关闭 | 视觉语义、类别、字段、认知状态、信号 |
| M2 | 局部语义单元、载体、field/value、epistemic、显式 signal | 改 owner、跨 Chunk 身份、phase/scope/persistence、Promotion |
| M3 | 跨 Chunk 身份组件解析 | 字段和时间 |
| M4 | phase、scope、persistence | 重新发现事实或修改字段/身份 |

## 4. M1 v2 目标协议

### 输入

模型业务输入只有：

```json
{
  "chunk_text": "冻结后的当前 Chunk"
}
```

### 输出

```json
{
  "mentions": [
    {
      "mention_quote": "男子"
    }
  ],
  "evidence_candidates": [
    {
      "owner_index": 0,
      "evidence_quote": "男子年龄在二十左右，英俊的相貌，配上挺拔的身材"
    }
  ]
}
```

约束：

- `mention_quote` 和 `evidence_quote` 必须是当前 Chunk 的逐字连续子串；
- `evidence_quote` 必须最小但语义完整，并在当前 Chunk 中只出现一次，以便 N2 唯一定位；短片段重复时只扩展到足以消歧的相邻原文；
- 否定、不确定、推断、明确或近似年龄、比较、presentation 和 transformation 等限定关系必须与其修饰的外貌保留在同一候选中；
- `owner_index` 明确时引用 `mentions`，不明确时为 `null`；
- 一个候选可以包含多个视觉维度，不按 face/body/clothing 拆分；
- 不输出 mention kind、raw proposition、coarse family、epistemic、signal 或 reason code；
- 不因候选包含复合语义而扩大到无关段落；owner 不同或证据不连续时仍应拆开。

## 5. N2 v2 已实现协议

N2 输入 `PreparedChunk + VisualEvidenceDiscoveryResult`，输出 `GroundedEvidencePacket`：

运行时入口为 `application/ports/evidence_grounding.py` 与 `application/services/evidence_grounding_service.py`，版本为 `evidence-grounding-input-v2`、`grounded-evidence-packet-v2`、`evidence-grounding-policy-v2`。N2 接受唯一逐字或仅空白差异且唯一的来源切片；逐字但多次出现的引文进入 `deferred_items/ambiguous_evidence`，不借 owner 猜 occurrence；文字或标点改写进入 `rejected_items/quote_not_in_chunk`。

```json
{
  "mention_nodes": [],
  "grounded_candidates": [
    {
      "candidate_id": "ge_...",
      "local_owner_id": "e1",
      "evidence_quote": "男子年龄在二十左右，英俊的相貌，配上挺拔的身材",
      "evidence_span": {
        "start": 120,
        "end": 147,
        "source_quote": "男子年龄在二十左右，英俊的相貌，配上挺拔的身材",
        "quote_hash": "..."
      },
      "local_context": {
        "text": "..."
      }
    }
  ],
  "rejected_items": [],
  "deferred_items": []
}
```

N2 只能按来源和结构分流。明显非视觉但引文可定位的 false positive 仍进入 M2，由 M2 进行语义 reject。

## 6. M2 v2 目标协议

### 输入

```json
{
  "candidates": [
    {
      "evidence_quote": "男子年龄在二十左右，英俊的相貌，配上挺拔的身材",
      "owner_mention_quote": "男子",
      "local_context": "..."
    }
  ],
  "canonical_field_catalog": []
}
```

`candidate_id`、span/hash、Chunk ID 和版本信封由服务端保留，不发给模型。

### 输出

```json
{
  "decisions": [
    {
      "candidate_index": 0,
      "decision": "map",
      "semantic_units": [
        {
          "semantic_unit_index": 0,
          "referent_kind": "whole_character",
          "referent_quote": "年龄在二十左右",
          "field_path": "age",
          "normalized_value": "二十左右",
          "epistemic_status": "asserted"
        },
        {
          "semantic_unit_index": 1,
          "referent_kind": "body_part",
          "referent_quote": "相貌",
          "field_path": "face.description",
          "normalized_value": "英俊",
          "epistemic_status": "asserted"
        },
        {
          "semantic_unit_index": 2,
          "referent_kind": "whole_character",
          "referent_quote": "身材",
          "field_path": "body.build",
          "normalized_value": "挺拔",
          "epistemic_status": "asserted"
        }
      ],
      "temporal_signals": [
        {
          "signal_quote": "年龄在二十左右",
          "signal_kind": "age",
          "semantic_unit_indices": [0]
        }
      ],
      "reason_code": "explicit_semantic_mapping"
    }
  ]
}
```

字段路径示例必须以运行时 canonical catalog 为准；本文示例只说明职责和绑定结构，不替代 catalog。

M2 对局部显式信号只做“文本表达了什么”的判断。N6/M4 继续决定其属于哪个叙事窗口、何时开始结束以及是否持续。

## 7. 局部 owner 到稳定人物的转换

M1 的 `owner_index` 和 N2 的 `local_owner_id` 都只是当前 Chunk 内的 mention 引用，不是稳定人物 ID。一个 Chunk 可以同时包含多个人物，同一个人物也可以出现在多个 Chunk，因此不能把单值 `owner` 直接写成 Chunk 的身份事实。

M3 验收后由服务端物化版本化绑定，并从同一关系生成两个访问方向：

```text
chunk_id -> candidate_id -> mention_id -> binding_id -> character_id
character_id -> observation_id -> candidate_id -> chunk_id/span
```

Chunk 读取接口可以在 `metadata.derived_owners` 中暴露如下可重建缓存：

```json
{
  "stable_owner_ids": ["character-001", "character-007"],
  "owner_binding_version": "m3-binding-v12",
  "owner_index_status": "fresh"
}
```

约束：

- `stable_owner_ids` 必须是集合，只包含 M3 已稳定 owner；unknown/unresolved 不得伪装成特殊人物 ID；
- 派生 owner 元数据不参与 `chunk_hash`，不传回 M1，也不是身份事实源；
- 权威事实是带 provenance、状态、版本和 supersede 链的 `OwnerBinding`；
- M3 reopen、人工改绑或版本变化时，同时失效 Chunk 方向缓存、人物方向观察索引和受影响的 M4 batch；
- 两个方向是同一关系的索引，不允许分别写入后自行漂移。

## 8. M4 的唯一组包方向

上游按 Chunk 流式处理：M1 发现证据，N2 定位，M2 解析语义，M3 稳定 owner。N6 随后把数据转换为人物中心视图。M4 每次只接收一个 `character_id` 的 stable observations、signals、已有 phase 与必要最小窗口；不得把“逐 Chunk 混合多个人物”作为第二种 Prompt 输入模式。

当一个人物关联的证据超过 token 预算时，N6 按章节、Chunk、span 顺序切成多个有界子批次，并保留 signal 与关联 observation 的完整性。因此两种视图都存在，但职责不同：Chunk 视图负责摄取、查询和失效传播，人物视图负责 M4 时间解析。

## 9. 评测边界

### M1 v2

- evidence coverage recall；
- quote fidelity；
- owner anchor 按 `required / allowed / must_be_null` 三态分别计量；
- irrelevant candidate rate；
- empty Chunk false-negative audit；
- Schema、token、延迟和调用可靠性。

M1 v2 不再评分 coarse family、raw proposition、事实拆分、epistemic 或 signal kind。

当前评测契约为 Dataset Schema `visual-evidence-evaluation-dataset-v2.4`（兼容 v2.2）、Rubric `visual-evidence-evaluation-rubric-v2.5` 与 Source Match Policy `visual-evidence-source-match-policy-v2`。短边界集为 16 条 `m1-visual-evidence-short-v2.3-draft`；另有 10 条由生产章节切分与 `target_tokens=1000` 从 `tests/测试` 重建的 `m1-visual-evidence-real-v2.5-draft`。真实运行器必须先经过与 shadow 服务一致的 deterministic validation；除唯一且仅有 Unicode 空白差异可安全回填原始切片外，非逐字、文字/标点变化或无法唯一定位的 evidence 引文直接失败。成功运行保存 prompt、dataset、rubric 与 validation policy SHA-256，以及模型、请求、尝试次数、延迟和 token usage 等运行元数据，不保存 API key 或原始 Provider 响应。

Prompt v2.2 在 approved 短集上的首次真实诊断为 14/16：否定外貌漏召回 1 条；推断年龄候选虽保留“看来、约莫六十岁”，但裁掉“从他”后不再满足批准的完整跨度。v2.3 将优先级改为“召回 → 语义/语法完整与唯一定位 → 最后最小化”，修复这两条后暴露 unknown-owner 回归；v2.4 排除 body part owner，但仍把“不知道哪一个人”的表达当作 owner。v2.5 要求 owner mention 必须正向识别一个具体局部人物，最终同模型、同 16 条 approved 短集为 16/16。该结果通过短回归 Gate，但不能替代尚未批准的真实 Chunk Gate。

v2.6 增加穿脱可穿戴物和人物定位起点；v2.7 增加“语义边界→唯一定位边界”和全 Chunk 覆盖复扫；v2.8 增加 owner 硬边界与同 owner 复合事件。v2.8 双集真实回归为短集 16/0/0、真实集 2/5/3；009 的前三段 transformation 已改善。v2.9 的通用唯一性/独立 cue 规则完成双集检查后仍未稳定解决 005，用户因此决定主 Prompt 回退 v2.8，并将 005 作为条件 Gate 残余风险交由 N2 安全分流。

### M2 v2

- candidate map/signal-only/defer/reject；
- semantic-unit recall/precision；
- 过拆/漏拆；
- referent binding；
- field/value accuracy；
- epistemic accuracy；
- explicit signal recall/precision；
- signal-to-semantic-unit binding。

## 10. 迁移影响

需要升级：

- M1 DTO、Prompt、Provider、Service、Artifact 与评测器；
- N2 输入、`GroundedEvidencePacket`、定位服务和集成测试；
- M2 DTO、Prompt、Provider、Service、Artifact、字段/信号校验和评测器；
- M1/M2 数据集与保存输出格式；
- M1→N2→M2 一次性 shadow 编排；
- M3 `OwnerBinding` 物化、Chunk/人物双向派生索引及 supersede 失效传播；
- N6 单人物组包、排序、token 切批与 signal-observation 完整性校验；
- 技术契约、机器 Schema、版本台账和 Gate。

不直接复用为 v2 Gate：

- M1 v1 的 15 条短集和 6 条真实集评分；
- M1 v1 Prompt 5/6 结果；
- M2 v1 的 9 条 draft 数据集；
- 当前 `LocalObservationDiscoveryResult`、`GroundedLocalPacket` 和 `FieldDisambiguationResult`。

这些资产可用于提取 v2 金标和回归场景，但必须按新职责重新标注和批准。

## 11. 完成条件

只有以下全部具备，才能把 v2 边界标为已实现：

1. 三段 v2 DTO、Prompt、Provider 和服务落地；
2. 机器 Schema 与运行时 Pydantic Schema 一致；
3. 新 M1/M2 数据集经用户审核；
4. M1 evidence Gate 已由用户带残余风险条件批准；M2 semantic Gate 仍需独立通过；
5. M1→N2→M2 一次性 shadow 集成通过；
6. v1 与 v2 工件不会混写，旧结果保持可追溯但不冒充 v2 证据；
7. 仍不产生 active Observation，直到后续身份、时间、M5 与 Promotion Gate 通过。
