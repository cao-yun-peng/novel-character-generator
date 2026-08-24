# 文本理解流水线

> [← 上一篇](03-domain-data-model.md) · [文档索引](README.md) · [下一篇 →](05-character-render-profile.md)
>
> 文档版本：2.9 · 源章节：7. 文本理解流水线 · 修订日期：2026-08-24
>
> 当前状态：TXT 规范化、章节分块和基础角色/视觉事实提取已经运行；复杂实体链接、时间自动化和 Observation 到外观档案的聚合仍未全部闭环。

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
class ChunkExtractionResult(BaseModel):
    mentions: list[CharacterMention]
    alias_hypotheses: list[AliasHypothesis]
    observations: list[ObservationDraft]
    expression_observations: list[ExpressionObservationDraft]
    scene_hypotheses: list[SceneHypothesis]
    timeline_hypotheses: list[TimelineHypothesis]
    relations: list[RelationDraft]
    unresolved_references: list[ReferenceDraft]
    warnings: list[str]
```

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
  → 产生 ResolvedCharacterSnapshot 或待审核项
```

时间定位优先使用原文明确时间、事件因果和年龄阶段；章节位置只作为弱证据。复杂倒叙、重生、时间循环和平行世界无法唯一确定时，保留多个候选作用域并进入人工审核，不得让 LLM 静默选择一个版本。

神情提取与外观事实同时进行，但保存为独立 Observation。只有可见线索进入图像渲染；内心独白用于语义理解，不直接转为笑容、哭泣等视觉指令。

### 7.5 增量处理

增量输入基于文档哈希和块哈希，而不是只记录 `chunk_count`：

- 纯追加章节：只处理新增块；
- 中部编辑：从首个变化块开始重提取受影响窗口；
- 删除章节：将相关观察标记为失效，不物理删除审计记录；
- Prompt、模型或 Schema 升级：创建新的 extraction run，可与旧结果对比；
- 聚合档案重新计算不需要再次调用 LLM。
- 场景或事件被重新绑定时间线时，只失效受影响作用域的状态快照，不重跑无关章节；
- `ResolvedCharacterSnapshot` 是派生产物，可按 resolver 版本重建，不作为唯一事实源。

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

---

[← 上一篇](03-domain-data-model.md) · [文档索引](README.md) · [下一篇 →](05-character-render-profile.md)
