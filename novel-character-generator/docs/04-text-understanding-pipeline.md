# 文本理解流水线

> [← 上一篇](03-domain-data-model.md) · [文档索引](README.md) · [下一篇 →](05-character-render-profile.md)
>
> 文档版本：3.2 · 源章节：7. 文本理解流水线 · 修订日期：2026-08-26
>
> 当前状态：TXT 规范化、5,000 估算 Token 分块与少量重叠、视觉候选 v3、服务端证据定位、Observation 自动聚合，以及上传后细粒度检索与视觉精提取基础链路已经运行；复杂共指、小说级阶段 resolver、设计缺口和出图就绪度仍是目标设计。

## 7. 文本理解流水线

### 7.1 导入与分块

1. 检测文件类型、编码、大小和恶意内容；计算 SHA-256。
2. 规范换行和不可见字符，但保留原文字符偏移映射。
3. 识别卷、章、节边界；无法识别时按段落回退。
4. 使用目标 token 上限而非固定字符数；字符数只作为快速预估。
5. 大章节在段落/句子边界切分；重叠区保留来源映射。
6. 每块保存内容哈希，使追加章节只创建新块或重算受影响块。

默认候选范围为 1K–12K tokens，不预设单一最优值。**[PoC 决策项 POC-TEXT-01]** 第 0 阶段必须在同一中文小说黄金集上比较场景优先 1K–3K、段落递归 2K–4K、当前大块 6K–12K、小块双 pass 和邻块上下文方案，并按字段 precision/recall、span 准确率、实体链接、重复率、延迟、总成本及“每个正确字段成本”冻结一期参数。PoC 通过前，6K–12K 只能作为对照组，不能写入生产默认配置。

### 7.2 块级提取

每个块一次调用，结构化输出：

```python
class VisualCandidateExtractionResult(BaseModel):
    entities: list[VisualEntityCandidate]
    visual_candidates: list[VisualFactCandidate]
    deferred_items: list[VisualDeferredCandidate]
```

这是当前 `visual-observation-v3.1` 的视觉候选契约。它保留每块一次主要批量调用，但只处理“人物候选 + 原子视觉候选 + 显式时间信号”；offset 定位交给服务端。Provider 输出经 locator 变成带 mention_id 的候选包并先持久化，随后由实体解析模型逐 Chunk 读取累计人物记忆，每 10 Chunk 固定收敛。收敛确认的 final mention→character 绑定只生成 pending Observation；R3 再解析人物阶段、呈现方式、现实状态、形态和时间范围，只有 final 作用域才激活并进入聚合。开发阶段不再付费运行 v2 Shadow，也不自动回退 v2。完整边界见[R2 人物实体解析契约](24-character-entity-resolution-contract.md)和[R3 人物阶段与时间作用域解析契约](25-character-phase-resolution-contract.md)，重构动机和评测计划见[视觉优先的全文抽取重构方案](23-visual-first-extraction-refactor.md)。

服务端 Adapter 生成的内部 `ObservationDraft` 为：

```python
class ObservationDraft(BaseModel):
    character_name: str
    field_path: str
    value: JsonValue
    evidence_quote: str
    start: int                         # evidence locator 计算
    end: int
    confidence: float
    epistemic_status: str = "asserted"
    life_phase_key: str | None = None
    life_phase_label: str | None = None
```

视觉字段必须原子化。Provider 必须直接返回 `skin.color`、`hair.color`、`hair.length`、`clothing.style`、`cleanliness`、`body.build`、`face.*`、`age`/`age_stage`、`accessories.*`、`injuries.*`、`distinctive_marks.*` 或 `disguise.*`，不能返回综合 `appearance`、旧字段别名或角色名前缀。v3 Adapter 会拒绝非视觉、非规范和 inferred/uncertain 候选；Repository 中的旧归一化逻辑仅用于历史数据兼容。

证据必须精确落在当前 chunk。模型只抄写 quote，不提供数字偏移；服务端先唯一精确匹配，再结合人物 mention、句界和距离处理重复引用，只允许受控的空白归一化。仍重复或找不到时拒绝该候选并记录 warning，不猜测写入。

Prompt 只注入：

- 当前块文本；
- 在当前块出现或可能相关的角色摘要；
- 必需的 Schema；
- 少量跨块待解决问题。

禁止注入全书完整记忆快照。上下文预算在调用前计算，超限时先裁剪低相关记忆，再拆块。

### 7.3 实体链接与共指顺序

正确顺序为：

```text
候选提及检测
  → 当前块称谓/代词共指
  → 与已有角色实体匹配
  → 别名假设聚类
  → 低置信度项进入人工审核
  → 事实绑定到规范 character_id
```

不再先提取角色事实、后做共指。低频实体不能直接丢弃：出现一次但包含外貌描写、对话姓名或关键身份的候选仍需保留。

### 7.4 时间定位与状态解析

角色事实绑定完成后，再执行时间定位，避免“他少年时”中的“他”尚未解析就建立错误状态：

```text
场景边界识别
  → 叙事模式识别（当前/回忆/预叙/梦境/传闻/假设）
  → 故事事件与时间线候选匹配
  → TemporalScope 规范化
  → 观察绑定角色与作用域
  → 按目标时间解析 CharacterAppearanceState
  → 产生 ResolvedAppearanceFacts/Profile 草稿或待审核项
```

时间定位优先使用原文明确时间、事件因果和年龄阶段；章节位置只作为排序与区间边界，不单独证明人生阶段。当前稳定人生阶段键包括 `past_life`、`reincarnated_childhood`、`childhood`、`adolescence` 和 `adulthood`。人生阶段与时间线是两个维度：“前世→转生幼年”可以属于同一 canonical 人生顺序，平行世界、时间循环分支和假设世界才使用独立 timeline。R3 基础主链已经把歧义作用域保留为 `needs_review` 并阻止其进入聚合；完整规则和限制见[R3 契约](25-character-phase-resolution-contract.md)。

神情提取与外观事实同时进行，但保存为独立 Observation。只有可见线索进入图像渲染；内心独白用于语义理解，不直接转为笑容、哭泣等视觉指令。

### 7.5 增量处理

增量输入基于文档哈希和块哈希，而不是只记录 `chunk_count`：

- 纯追加章节：只处理新增块；
- 中部编辑：从首个变化块开始重提取受影响窗口；
- 删除章节：将相关观察标记为失效，不物理删除审计记录；
- Prompt、模型或 Schema 升级：创建新的 extraction run。Run 从第一个 chunk 开始时，会把同一源文档版本、不同 `extractor_version` 的旧自动 Observation 标记为 `superseded`，人工 Observation 保留；相同版本重跑继续依赖稳定指纹去重；
- 聚合档案重新计算不需要再次调用 LLM。
- 场景或事件被重新绑定时间线时，只失效受影响作用域的状态快照，不重跑无关章节；
- `ResolvedAppearanceFacts`、Profile 草稿和最终 `ResolvedCharacterSnapshot` 都是派生产物，可按 resolver/Profile 版本重建，不作为唯一事实源；Snapshot 只在已批准 Profile 和明确目标时间上解析。

当前 extractor version 形如 `<provider>:<model>:visual-observation-v3`，其中尾部是视觉提取 Schema 版本。这个版本替换机制保证新旧自动事实不会同时参与聚合，但不等于角色/字段级精细差异重算：后者已延期，目前仍会对 Run 涉及的人物进行保守聚合重建。

场景采用 `(novel_id, narrative_order)` 作为稳定槽位，其中 `narrative_order = chunk.ordinal * 1000 + scene_index`。重新分析时，同一槽位的新自动结果直接更新原 Scene 的标签、来源范围和置信度；自动时间绑定随新结果更新，`binding_status=corrected` 的人工时间绑定保持不变。不能再把“来源范围稍有变化”当成新 Scene 插入。

### 7.6 应用编排状态

文本流程由 `PipelineRun` 和 `PipelineStep` 驱动，应用服务只传递业务 ID 和小型命令对象：

```python
class TextPipelineCursor(BaseModel):
    schema_version: str
    run_id: UUID
    novel_id: UUID
    current_chunk_ordinal: int
    completed_step_keys: list[str]
    pending_review_ids: list[UUID]
    error_codes: list[str]
    status: str
```

游标持久化到业务任务表，不保存原文全文、数据库 Session、Provider Client 或 Pydantic 大对象。Worker 根据 `run_id` 和 `step_id` 从 Repository 加载数据。若局部 LangGraph PoC 启用，其 Graph State 只能引用这些业务 ID，不能复制或替代 `TextPipelineCursor` 的任务真值。

### 7.7 检索增强的视觉精提取（目标设计）

当前 5K 级 `text_chunks` 用于全文角色/阶段发现和基础 Observation。它们不适合只为一个重要角色反复扫描整书，也不能仅凭“姓名和外貌词同句”保证召回率。目标方案在上传新源版本后异步建立独立的 1K/100 细粒度 passage 索引：PoC 使用 SQLite FTS5 中文预分词 BM25 与“远程 Embedding API + Qdrant Local”向量检索并行召回，使用 RRF 融合，命中段必须携带前后邻居，再由 LLM 判断人物归属和原子视觉字段。

精提取只针对用户选定的角色、人生阶段和缺失字段组运行；它不会替换当前全文提取。可精确回映到原 `text_chunk` 的直接文本事实进入 Observation；职业、行为、比较和语境形成的候选进入 Suggestion 并等待审批，绝不自动污染 AppearanceState。完整数据模型、QueryPlan、恢复、API、配置和验收契约见[检索增强的角色视觉精提取实现设计](21-retrieval-augmented-visual-enrichment.md)。

---

[← 上一篇](03-domain-data-model.md) · [文档索引](README.md) · [下一篇 →](05-character-render-profile.md)
