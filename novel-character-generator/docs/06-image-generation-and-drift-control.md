# 图像生成与视觉防漂移

> [← 上一篇](05-character-render-profile.md) · [文档索引](README.md) · [下一篇 →](07-agent-architecture.md)
>
> 文档版本：2.8 · 源章节：9. 图像生成与一致性评测 · 修订日期：2026-08-22

## 9. 图像生成与一致性评测

### 9.1 一期工作流策略

一期先完成技术 PoC，再选择并冻结一套组合。优先验证：

```text
SDXL-compatible checkpoint
  + InstantID（锁定基准图后）
  + 对应 SDXL 的姿态/结构控制节点
  + 固定 ComfyUI 与 custom node commits
```

**[PoC 决策项 POC-IMAGE-01]** 一期只会冻结其中一套完整组合。PoC 使用同一批角色、阶段和场景，比较身份、阶段属性、Prompt 遵循、失败率、时延、显存或费用，并同时审查完整资产许可证。若 FLUX + PuLID-FLUX 更合适，可以整体替换 SDXL + InstantID；不得跨模型族随意拼接节点。

一期生成顺序：

1. 从已批准的全部 `CharacterAppearanceState` 中提出关键阶段候选，人工确认一期需要生成的 2–4 个阶段；
2. 为每个阶段用 `CharacterRenderRequest` 在目标时间线、事件或场景解析独立的 `ResolvedCharacterSnapshot`；
3. 每个阶段从已批准快照生成 4–8 张候选正面肖像；
4. 自动质量筛选后由用户为每个阶段选择阶段基准图；
5. 将所有阶段基准图组织为 `CharacterImageSet`，并选定一个默认代表形象；
6. 默认只基于代表形象生成一张角色设定图；其他阶段设定图按用户选择和预算生成；
7. 保存工作流、模型、Prompt、seed、输入快照、阶段归属和远程请求 ID 的完整快照。

一期支持“一个角色多个历史阶段形象”，但不做每章节、每次换装、每个表情的穷举生成。自动四格切分、同阶段跨姿势量产和 LoRA 进入二期。

### 9.2 WorkflowProfile

```python
class WorkflowProfile(BaseModel):
    id: str
    version: str
    base_model_family: Literal["sdxl", "flux", "other"]
    ui_workflow_file: str
    ui_workflow_sha256: str
    api_workflow_file: str
    api_workflow_sha256: str
    parameter_binding_schema_version: str
    comfyui_commit: str
    comfyui_frontend_version: str
    custom_nodes: list[CustomNodeAsset]
    python_lock_sha256: str
    container_image_digest: str
    model_assets: list[ModelAsset]
    supported_modes: set[str]
    input_schema_version: str
    output_schema_version: str
    evaluator_bundle_version: str
```

工作流注册时运行契约测试，校验 UI JSON 与实际提交的 API JSON、参数绑定、节点、输入端口、模型文件、容器环境和输出结构。运行时禁止直接修改原始模板，必须深拷贝后填参。**[P0]** 每个模型、身份权重、基础 checkpoint、VAE 和 custom node 必须保存来源 URL、版本/commit、SHA-256 与许可证标识；许可证不明确的资产只能用于隔离 PoC，不能进入生产 Profile。

### 9.3 多指标质量评测

CLIP-I 只作为辅助主体相似度，不能单独决定“锁定角色”。建议组合：

| 维度 | 指标示例 | 作用 |
|---|---|---|
| 人脸身份 | ArcFace/InsightFace cosine | 有清晰人脸时评估身份保持 |
| 主体相似 | DINO/CLIP-I，先做主体裁剪 | 非写实或全身场景的辅助指标 |
| 属性一致 | 视觉问答/分类器/人工规则 | 发色、服装、疤痕、配色等 |
| 状态一致 | VLM + 规则 | 年龄阶段、伤势、伪装和目标神情 |
| 图像质量 | 人脸检测、模糊、畸变、重复人物 | 排除明显坏图 |
| Prompt 遵循 | 图文相似或 VLM 审核 | 确认目标描述被体现 |
| 人工确认 | 用户选择 | 最终锁定依据 |

所有阈值必须在项目自己的评测集上标定。配置中保存评测器版本和阈值集版本，不直接把 `0.85` 当作跨模型通用标准。

### 9.4 图像产物

每个生成结果至少保存：

- `artifact_id`、存储 URI、SHA-256、MIME、尺寸；
- `character_id`、RenderProfile 版本、CharacterImageSet 版本、ResolvedCharacterSnapshot 哈希；
- `appearance_state_ids`、阶段标签、阶段显示顺序、是否为阶段基准图及是否为默认代表形象；
- `timeline_id`、目标 event/scene ID、外观状态和神情观察 IDs；
- WorkflowProfile、Prompt 和模型版本；
- seed、完整生成参数、参考图 artifact IDs；
- Provider request ID、耗时和费用快照；
- 各评测分数、评测器版本和人工决策。

### 9.5 视觉防漂移闭环

#### 9.5.1 冻结生成上下文

图像 Provider 不直接读取可变的 `CharacterRenderProfile`。Application Orchestrator 先调用快照解析器，再由 `GenerationContextBuilder` 生成不可变、可哈希、可重放的上下文。该上下文是本次生成和后续审计的共同真值：

```python
class GenerationContextSnapshot(BaseModel):
    id: UUID
    schema_version: str
    character_id: UUID
    render_profile_id: UUID
    render_profile_version: int
    character_image_set_version: int
    target_timeline_id: UUID
    target_event_id: UUID | None
    target_scene_id: UUID | None
    target_chapter_ordinal: int | None
    resolved_snapshot_hash: str
    identity_constraints: list[VisualConstraint]
    stage_constraints: list[VisualConstraint]
    scene_constraints: list[VisualConstraint]
    negative_constraints: list[VisualConstraint]
    evidence_ids: list[UUID]
    baseline_artifact_ids: list[UUID]
    workflow_profile_version: str
    prompt_template_version: str
    evaluator_bundle_version: str
    token_or_payload_budget: int
    context_hash: str


class VisualConstraint(BaseModel):
    field_path: str
    expected_value: JsonValue
    severity: Literal["critical", "high", "medium", "low"]
    source_ids: list[UUID]
    rule: Literal["must_match", "must_include", "must_not_include", "reference_only"]
```

约束按以下顺序组装：人工批准的本次覆盖 > 已批准的场景状态 > 已批准的目标阶段状态 > 锁定身份锚点 > 仅允许填充的画风默认值。低置信度推断、未解决冲突、其他时间线状态、已失效观察和未经批准的身份原型不得进入正向事实约束；必要时以 `negative_constraints` 明确阻止模型混入错误年龄、旧伤、其他伪装或分支状态。

上下文构建必须保存字段选择清单、裁剪原因、来源 ID 和 `context_hash`。超出预算时先删除低优先级参考说明，再缩短证据摘要，最后拆分任务；不得裁掉 `critical` 身份属性、目标时间线和硬性负约束。完整 Prompt 可以只保存在受限业务表或加密产物中，普通日志只记录版本和哈希。

#### 9.5.2 生成后漂移审计

每个候选图生成后必须产出结构化 `DriftAuditResult`，不能只保存一个总分：

```python
class DriftAuditResult(BaseModel):
    id: UUID
    generated_image_id: UUID
    generation_context_id: UUID
    context_hash: str
    evaluator_bundle_version: str
    identity_drift: list[DriftFinding]
    stage_drift: list[DriftFinding]
    scene_drift: list[DriftFinding]
    timeline_drift: list[DriftFinding]
    unsupported_additions: list[DriftFinding]
    deterministic_checks: dict[str, JsonValue]
    overall_decision: Literal["pass", "soft_fail", "hard_fail", "needs_human"]
    decision_reason_codes: list[str]


class DriftFinding(BaseModel):
    field_path: str
    severity: Literal["critical", "high", "medium", "low"]
    expected: JsonValue | None
    observed: JsonValue | None
    evidence_or_constraint_ids: list[UUID]
    evaluator: str
    confidence: float | None
    suggestion: str | None
```

审计至少覆盖五类漂移：

| 类别 | 检查内容 | 典型硬失败 |
|---|---|---|
| 身份漂移 | 脸部身份、稳定体貌、独特标记、主体数量 | 换脸、关键胎记/疤痕消失、多余人物 |
| 阶段漂移 | 年龄、持续伤势、发色、长期伪装、阵营服饰 | 少年阶段生成成年形象、使用其他阶段伤势 |
| 场景漂移 | 本场景服装、污渍、即时神情和姿态 | 目标神情相反、明确要求的伪装缺失 |
| 时间线漂移 | timeline/event/scene 与状态来源是否一致 | 主线图混入分支或梦境状态 |
| 无依据新增 | 显著但快照未授权的新属性 | 新增角、纹身、武器等影响身份的特征 |

确定性检查、人脸/主体相似度、属性模型和 VLM Critic 的输出并列保存，不让 VLM 总分覆盖明确的硬规则。Critic Prompt 必须使用与生成相同的 `GenerationContextSnapshot`；若审计读取了不同 `context_hash`，直接返回 `audit_context_mismatch`，不得继续判分。

#### 9.5.3 门禁、重生成与人工覆盖

门禁决策由确定性策略层完成：

```text
hard_fail
  → 禁止成为阶段基准图
  → 若预算、次数和截止时间允许，按 finding 生成修订参数并最多重生成一次
  → 仍失败则 needs_human

soft_fail
  → 可保留为候选，但不能自动锁定
  → 由用户接受、拒绝或带理由覆盖

pass
  → 进入人工候选池
  → 只有人工选择后才能成为 baseline_image_id
```

人工覆盖必须创建 `HumanApproval` 或 `DecisionRecord`，记录被覆盖的 finding、理由、操作者、时间和影响范围。出现以下任一情况时禁止无审批自动放行：错时间线、错年龄阶段、身份明显变化、关键锁定属性缺失、多余人物、未解决事实冲突、快照已失效或审计上下文不一致。

#### 9.5.4 幂等、失效和防止自我污染

- 每次生成尝试使用稳定幂等键：`context_hash + workflow_profile_version + seed + attempt_index`；重复回调只关联既有尝试，不新增产物或费用记录。
- Drift Audit 以 `generated_image_hash + context_hash + evaluator_bundle_version` 生成稳定指纹；同版本重跑覆盖同一审计尝试的状态，不重复累计 finding。
- RenderProfile、AppearanceState、目标时点或关键证据发生变化时，依赖旧 `context_hash` 的候选图标记为 `stale`；已锁定基准图不物理删除，但必须进入重新确认队列。
- 重生成产生的新图和 Critic 观察不得自动成为 `FeatureObservation`、`CharacterAppearanceState` 或身份锚点。视觉产物只能通过明确的人工决策作为参考图进入下一版档案。
- 回滚档案或实体合并/拆分后，按依赖图重新计算受影响角色、阶段和快照；禁止仅回滚展示层而保留旧审计或旧费用关联。

---

[← 上一篇](05-character-render-profile.md) · [文档索引](README.md) · [下一篇 →](07-agent-architecture.md)
