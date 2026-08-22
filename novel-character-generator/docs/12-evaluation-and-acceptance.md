# 评测系统与验收门禁

> [← 上一篇](11-security-and-data-governance.md) · [文档索引](README.md) · [下一篇 →](13-observability-logging-and-cost.md)
>
> 文档版本：2.7 · 源章节：15. 测试与验收 · 修订日期：2026-08-22

## 15. 测试与验收

### 15.1 测试分层

| 层级 | 内容 |
|---|---|
| 单元测试 | 分块、偏移映射、时间作用域、快照解析、聚合、冲突、状态机、成本公式 |
| 集成测试 | AsyncSession、Alembic、Repository、任务领取与租约 |
| Provider 契约测试 | mock 响应、超时、429、5xx、异步远程任务恢复 |
| Prompt 黄金测试 | 固定片段与期望结构；允许语义容差但不允许证据错位 |
| Agent 工具契约 | 工具选择、参数、权限、错误处理、幂等和审批行为 |
| Agent 轨迹评测 | 结果正确性、证据、重复调用、越权、停止条件和成本 |
| Agent 对抗测试 | Prompt 注入、恶意工具输出、上下文污染和权限提升尝试 |
| 图像工作流契约 | 节点、模型资产、输入输出 Schema、最小生成 smoke test |
| 防漂移闭环 | 冻结上下文、正/负约束、审计 Schema、hard/soft gate、有界重生成、人工覆盖和失效传播 |
| 故障恢复 | Worker 在提交前/后、保存前/后崩溃，验证不重复收费并保留可关联的 Run/Trace 诊断信息 |
| 可观测链路 | API→Run→Step→Agent/LLM/Tool→Provider→Artifact 的 Span 层级、跨 Worker Trace Context/Span Link、日志关联字段 |
| 日志规则检查 | 固定事件夹具覆盖链路闭合、租约、幂等、费用顺序、context hash、漂移门禁、审批恢复、产物哈希和退出码 |
| 遥测降级 | Collector 断开、导出超时、队列满；业务任务不中断，普通遥测可丢弃且记录丢弃计数 |
| 脱敏测试 | 正文、Prompt、密钥、Authorization、Cookie、人脸 embedding 和签名 URL 不得出现在日志、Trace 或告警中 |
| E2E | 上传→提取→审核→生成→选择基准图 |

### 15.2 EvalCase、数据集与运行模型

评测资产使用项目自己的稳定 Schema；OpenAI Evals、Promptfoo 或其他平台只能作为 Adapter，不能成为历史结果可读性的唯一依赖。该结构与 OpenAI Evals 的 data source schema、testing criteria、grader result 和 eval run 模型兼容。

```python
class EvalCase(BaseModel):
    id: UUID
    dataset_version: str
    source_novel_id: UUID | None       # 故障/安全合成 case 可为空
    source_document_version_id: UUID | None
    split_group_key: str               # 小说ID或合成场景族，整个组只能属于一个split
    split: Literal["dev", "validation", "test"]
    task_type: Literal[
        "observation", "entity_link", "temporal_binding", "conflict",
        "snapshot", "expression", "agent", "image", "recovery", "security"
    ]
    input_refs: list[UUID]
    expected_output: JsonValue
    evidence_spans: list[TextSpan]
    slice_tags: list[str]
    severity: Literal["normal", "important", "critical"]
    rubric_version: str
    annotation_status: Literal["single", "double", "adjudicated"]


class EvalRun(BaseModel):
    id: UUID
    dataset_version: str
    candidate_config_hash: str
    baseline_config_hash: str | None
    model_versions: dict[str, str]
    prompt_versions: dict[str, str]
    agent_spec_versions: dict[str, str]
    tool_versions: dict[str, str]
    schema_versions: dict[str, str]
    workflow_profile_version: str | None
    grader_bundle_version: str
    random_seeds: list[int]
    started_at: datetime
    completed_at: datetime | None
```

每个 `eval_results` 保存 case、grader、原始输出 Artifact、分数、pass/fail、失败原因、token、延迟和费用。模型评分器必须记录模型 revision、Prompt/rubric 和采样参数；人工评分必须记录匿名评审者、盲评顺序和裁决结果。

### 15.3 数据抽样、隔离与人工标注

数据按 `split_group_key` 划分：真实文本使用小说/独立来源作品，合成故障与安全 case 使用场景族。禁止将同一组的不同章节或轻微变体随机分到开发集和测试集，避免同一角色、别名、世界观或攻击模板泄漏：

```text
dev 60%          调 Prompt、规则和解析器
validation 20%   选择模型、阈值和 WorkflowProfile
test 20%         冻结；只用于候选版本发布评测
```

样本规模分两档：

- PoC：3–5 个合法来源作品、80–120 个精标 case，覆盖核心正例、反例和严重失败模式；
- 一期 Alpha：6–10 个独立来源作品、300–500 个文本/Agent case、200–300 张图像，并保证每个关键 slice 有最低样本数；
- 新发现的线上失败先进入 quarantine，经标注和去重后加入下一数据集版本，不能直接修改冻结测试集。

`slice_tags` 至少覆盖古风/现代/玄幻、同名/别名/省略代词、无外貌留白、倒叙、梦境、传闻、伪装、重生/循环/平行线、持久伤势、瞬时神情、内外情绪不一致和反差设定。20%–30% 的主观或高风险 case 由两人独立标注；一致性使用 Cohen's kappa 或 Krippendorff's alpha 报告，低于 0.70 时先修订标注手册并重新标注，不用模型分数掩盖定义分歧。

### 15.4 文本、实体、时间与快照指标

Observation 的严格匹配键为：

```text
(character_id, field_path, normalized_value,
 effective_temporal_scope, reality_status, evidence_span)
```

同时报告严格和宽松两套结果：严格结果要求字段、值、时间与证据均正确；宽松结果允许受控同义值和证据区间部分重叠。指标定义固定到 `grader_versions`：

| 能力 | 指标 | 说明 |
|---|---|---|
| 分块/偏移 | 可重现率、原文往返准确率 | 偏移映射必须可逆 |
| Observation | micro/macro Precision、Recall、F1 | macro 按字段和 slice 计算，避免高频字段掩盖长尾 |
| Grounding | exact-span、token-span F1、IoU、unsupported fact rate | 无证据事实单独作为风险指标 |
| 实体链接 | mention-level F1、cluster B³/CEAF、严重误合并数 | 主角与配角分开报告 |
| 时间绑定 | timeline/event 准确率、区间 IoU、defer Recall | 复杂分支允许正确 defer |
| 冲突 | conflict Precision/Recall/F1、误覆盖数 | 父子时间线先解析继承域 |
| 快照 | 字段准确率、关键字段 exact-match、状态组合正确率 | 在指定 timeline/event/scene 上评测 |
| 神情 | 外显情绪 Macro-F1、visible-cue span F1、内外情绪混淆率 | 瞬时神情跨场景延续单独计错 |

不得只报告总体平均值；关键 slice、严重等级和置信区间必须出现在报告中。Precision/Recall 的阈值先用 validation 标定，测试集只验证，不再调参。

### 15.5 Agent 结果与轨迹评测

每个 Agent 至少与以下基线之一在同一 EvalCase 上比较：确定性规则、单次 Structured Output、上一发布版本。Agent 评测同时包含：

- 最终任务成功率和 Schema 有效率；
- 事实、证据和引用完整性；
- 正确工具选择率与参数准确率；
- 必须转人工场景的 escalation Recall，以及不必要升级率；
- 重复/无关工具调用率、平均轮次、P95 延迟和单位成功任务成本；
- 权限、预算、最大轮次、停止和审批策略是否遵守；
- Prompt 注入、恶意工具输出和上下文污染下的失败方式。

最终结果正确但使用越权、危险或不可重放路径仍判失败。测试/验证集上的随机任务至少重复 3 次；Provider 不支持 seed 时仍执行重复采样并报告均值、标准差和最差结果。模型 Grader 只能评价难以确定性判断的语义维度，发布前必须在双人标注子集上校准；权限、证据区间、工具参数、费用和停止条件优先使用确定性 Grader。

### 15.6 图像自动评测与人工盲评

图像不使用单一加权总分。评测顺序为：

```text
硬失败规则
  → 身份/主体/属性/状态自动指标
  → 同角色同阶段多 seed 排序
  → 候选与基线的盲测 A/B
  → 人工选择阶段基准图
```

硬失败包括多余人物、缺脸、严重肢体畸形、错误年龄阶段、错误时间线、关键疤痕/发色/伪装缺失以及目标神情相反。ArcFace/InsightFace 只用于清晰且适合该模型域的人脸；非写实或全身角色使用主体裁剪后的 DINO/CLIP-I 辅助，不把相似度当身份真值。VLM 评分器按版本化属性清单输出逐字段结论。

一期 Alpha 至少包含 20–30 个评测角色、每个 2 个阶段、每阶段不少于 4 个 seed，并形成不少于 150 组盲测比较。评审者看不到模型、Prompt、工作流和候选顺序；至少 20% 图片由第二评审者复核，分歧进入裁决。报告身份保持、阶段属性、神情遵循、严重缺陷率、首次可用率、重生成率、人工接受率、延迟和单张/单阶段成本。

### 15.7 基线、消融与统计判定

候选版本必须冻结模型 revision、Prompt、AgentSpec、工具、Schema、resolver、WorkflowProfile、EvaluatorBundle 和依赖哈希。至少执行以下对照：

- 单次结构化调用 vs Extraction Agent；
- 当前发布版本 vs 候选模型/Prompt；
- 单一代表形象 vs 2–4 阶段形象集；
- 图像工作流 A vs B；
- 自动 Critic 关闭 vs 开启一次受控修订。

质量差异报告 95% bootstrap 置信区间；样本过少时明确标记 exploratory，不声称显著提升。降低成本、延迟或工具调用数只有在质量门禁仍通过时才算改进。不得用总体平均提升掩盖 critical slice 回归。

### 15.8 一期发布门禁与运行频率

以下数值为第一版门槛，PoC 后只能通过版本化决策记录修改：

| 模块 | 发布门槛 |
|---|---|
| 分块/偏移 | 可稳定重现；原文偏移往返准确率 100% |
| Grounding | 字段证据定位准确率 ≥ 95%；unsupported fact rate ≤ 2% |
| 实体 | 主要角色 mention F1 ≥ 0.90；高影响自动误合并数为 0 |
| Observation | 外貌字段 precision ≥ 0.90；同时报告 recall 与 macro-F1 |
| 时间/快照 | critical case 的 canonical 跨时间污染数为 0；关键字段 exact-match ≥ 0.90 |
| 神情 | 可见线索定位准确率 ≥ 90%；内外情绪混淆率单独报告并不劣于基线 |
| Agent | 权限违规和未经审批收费/合并/发布数为 0；必须升级 case 的 Recall ≥ 0.95 |
| 图像 | 错时间线/年龄等 critical mismatch ≤ 5%；人工接受率不劣于冻结基线 |
| 防漂移门禁 | hard-fail 候选无审批锁定数为 0；生成、审计、基准图的 context hash 不一致数为 0；重生成超限数为 0 |
| 恢复 | 故障注入不产生重复外部提交或重复计费；未知提交可进入对账/人工状态 |
| 追溯 | 图像、事实和审批可回到 source、配置、模型、工作流、seed 和费用；critical E2E 链路无断点 |
| 日志检查 | critical E2E 的 `log-check --strict` 无 FAIL；关键业务事件缺失、陈旧租约写入和费用对账失败数为 0 |
| 安全 | 正文、完整 Prompt、密钥、认证 Header、人脸 embedding 和签名 URL 泄漏数为 0 |

执行频率：

- PR Smoke：20–50 个固定低成本 case，运行单元、Schema、关键安全和文本黄金测试；
- Nightly：完整文本、Agent、恢复、对抗和遥测降级集；
- Release Candidate：冻结 test split、全部图像盲评、Provider 契约、故障恢复、安全和成本报告；
- 生产监控：只记录经批准的聚合指标和人工反馈，不把未经标注的线上接受率直接当离线准确率。

任一安全硬门槛失败、critical slice 回归或数据泄漏即阻止发布；普通质量指标只有在置信区间、成本和人工审核负担均可接受时通过。

### 15.9 评测报告、失败回流与预算

每次 EvalRun 生成机器可读 JSON 和人工可读报告，至少包含配置 diff、数据集版本、总体及 slice 指标、置信区间、失败样本、成本/延迟、Grader 版本、人工一致性和发布结论。失败样本先进入 quarantine；确认不是标注错误或重复样本后，才加入下一版 dev/validation 集。冻结 test case 不因候选版本表现而修改。

测试不以代码行数估算。建议将 30%–40% 的一期工程量用于自动测试、标注、评测集、图像盲评、故障注入和报告脚本，并为至少一名额外标注/审核人员预留时间。AI 系统的主要风险来自数据、模型随机性与外部服务行为，不是代码能否运行。

---

[← 上一篇](11-security-and-data-governance.md) · [文档索引](README.md) · [下一篇 →](13-observability-logging-and-cost.md)
