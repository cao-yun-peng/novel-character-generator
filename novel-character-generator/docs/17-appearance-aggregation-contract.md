# 外观状态聚合实现契约

> [← 上一篇](16-local-development-and-runbook.md) · [文档索引](README.md) · [下一篇 →](18-image-generation-implementation-contract.md)
>
> 文档版本：2.9 · 修订日期：2026-08-24
>
> 当前状态：核心链路已实现。`aggregate_appearance` 已接入文本 Pipeline，能够从真实 Observation 幂等形成 AppearanceState、Conflict 和待审核 RenderProfile；源版本替换会失效旧观察和派生状态、保留 stale 历史批准档案并生成新草稿。父子时间线继承和人工确认值冲突保护已有集成测试；角色/字段级精细差异重算已延期，当前继续采用整角色保守重建。

## 1. 要解决的问题

文本提取会产生带证据的 `FeatureObservation`，但图像生成不能直接消费零散观察。聚合步骤必须把同一人物、同一故事作用域内兼容的事实整理成部分覆盖的 `CharacterAppearanceState`，检测冲突，并生成可供人工编辑和批准的 `CharacterRenderProfile` 草稿。

```text
FeatureObservation
  → 过滤与证据校验
  → 时间/现实层级归组
  → 字段持续性与优先级合并
  → CharacterAppearanceState(draft)
  → CharacterConflict(open)
  → CharacterRenderProfile(draft)
  → 人工解决冲突、编辑和批准
  → ResolvedCharacterSnapshot
```

聚合器只做确定性整理和冲突发现，不调用图像模型，也不自动批准档案。

## 2. Pipeline 接入

新增稳定 Step：

```text
normalize_and_chunk
  → extract_characters
  → aggregate_appearance
```

`aggregate_appearance` 的输入必须固定到：

- `novel_id`、`source_document_version_id` 和产生观察的 Extraction Run；
- 聚合规则版本 `resolver_version`；
- 时间线继承与 `reality_status` 兼容矩阵版本；
- 字段持续性策略版本；
- 本次受影响的 `character_id` 集合。

Step 成功只表示草稿和冲突已经一致落库，不表示档案已批准。存在开放冲突时 Step 仍可成功，但对应 Profile 保持 `draft/needs_review`，不能进入图像生成。

## 3. 输入选择规则

只有同时满足以下条件的 Observation 才能进入正向聚合：

1. 属于当前有效源文档版本，或经过增量继承规则确认仍有效；
2. `record_status` 有效，没有被重抽取、删除章节或人工操作失效；
3. 证据区间可回查，`grounding_status` 满足当前规则；
4. 已绑定规范人物，未处于待拆分或待合并状态；
5. 时间、场景或现实层级能够解析；不能解析的观察进入待审核队列；
6. 字段属于允许的视觉 Schema，值通过规范化和类型校验。

低置信度推断、身份原型建议和画风默认值可以成为 `field_suggestions`，不能冒充原文事实写入锁定身份锚点。

## 4. 分层与作用域

聚合器按三层保存，不把所有信息压成单一人物 JSON：

| 层 | 典型字段 | 默认持续范围 |
|---|---|---|
| Identity | 稳定脸型、瞳色、先天标记 | 跨阶段持续，直到明确改变或证据失效 |
| AppearanceState | 年龄、发色、长期伤势、长期服装/伪装 | timeline + event/chapter 区间 |
| Scene/Expression | 表情、姿势、污渍、一次性换装 | 当前 scene 或明确短区间 |

每个 `CharacterAppearanceState` 是部分覆盖层，只保存该阶段相对稳定身份锚点发生变化或需要明确表达的字段。目标时点由 Snapshot Resolver 按优先级叠加，不预先生成所有状态组合。

子时间线在 `branch_event_id` 之前继承父时间线状态；分支后独立计算。梦境、传闻、想象和现实使用版本化兼容矩阵，不能只比较 timeline ID 或使用未定义布尔值。

## 5. 字段合并算法

对每个 `character_id + field_path + effective_timeline_domain`：

1. 按故事作用域计算有效区间，不按数据库写入时间覆盖；
2. 过滤被人工否决或已失效的观察；
3. 将相同规范值合并，保留全部证据 ID；
4. 按“用户确认 > 明确原文 > 多证据推断 > 已审核原型 > 画风默认”排序；
5. 同优先级、作用域重叠且值不兼容时创建或复用 `CharacterConflict`；
6. 持久字段延续到明确终止事件，瞬时字段不得跨场景延续；
7. 输出稳定排序的 `appearance` 与 `field_sources`，计算聚合指纹。

人工值不能被后续自动运行静默覆盖。新证据与人工值冲突时创建 `conflict_kind=human_confirmation` 的待审核冲突，并保留当前已批准版本直到用户决定；身份锚点与阶段状态都受此规则保护。

## 6. 幂等与版本

聚合输入指纹：

```text
sha256(
  character_id
  + sorted(active_observation_fingerprints)
  + timeline_graph_version
  + reality_compatibility_version
  + field_persistence_policy_version
  + resolver_version
)
```

相同指纹重复执行必须：

- 不新增重复 AppearanceState；
- 不重复创建同一开放冲突；
- 不增加 RenderProfile 版本或 revision；
- 只恢复缺失但可以由现有业务真值确定性重建的派生记录。

指纹变化时创建新的草稿版本或更新尚未批准的同一草稿，具体策略必须保持历史批准版本不可变。旧 Observation 失效后，受影响 State、Profile、Snapshot 和图像上下文按依赖图标记 stale，不能物理覆盖历史审计。

## 7. 事务边界

单个人物的聚合使用短事务：

1. 读取当前有效观察和当前 Profile revision；
2. 纯函数计算候选 State、Conflict 和 Profile 草稿；
3. 在事务内 compare-and-set 校验 revision；
4. upsert 派生状态和冲突；
5. 写入草稿 Profile、输入指纹与版本；
6. 提交事务后输出结构化日志。

一个人物失败不应回滚同一 Run 中已经成功聚合的其他人物；Step cursor 记录已完成人物和失败分类，以便恢复。所有 Worker 写入必须携带当前 `lease_generation`，陈旧 Worker 不能提交。

## 8. 人工审核状态机

```text
draft
  ├─ 有开放冲突/歧义 → needs_review
  ├─ 用户修改 → draft(new revision)
  ├─ 冲突全部解决 → ready_for_approval
  └─ approve + If-Match → approved(immutable version)

approved
  └─ 新证据/规则版本影响 → 新 draft；旧 approved 保留但标记 superseded/stale
```

批准必须使用 `If-Match` 和 `X-Actor-ID`。角色存在多个已批准阶段而请求没有目标时间时，Snapshot Resolver 返回 `ambiguous_appearance_state`，不能默认选择最新状态。

## 9. API 与代码落点

当前已有 API 保持不变：

- `GET /characters/{id}/appearance-states`；
- `GET /characters/{id}/conflicts`；
- `POST /conflicts/{id}/resolve`；
- `GET/PUT /characters/{id}/render-profile`；
- `POST /characters/{id}/approve`；
- `GET /characters/{id}/snapshot`。

实现时新增：

- `domain/policies/appearance_aggregation.py`：无数据库依赖的合并、持续性和冲突规则；
- `application/services/appearance_aggregation_service.py`：事务、版本和失效传播；
- `workers/handlers/appearance_aggregation.py`：Step 恢复和 cursor；
- `workers/main.py` 中的 `aggregate_appearance` 分发；
- Repository 方法与 Alembic migration，仅在现有字段不足时增加。

不要继续把聚合规则堆进已经复杂的 `AppearanceService`；现有 Service 保留查询、编辑、批准和 Snapshot 解析职责。

## 10. 必打日志

| 边界 | 事件 | 必要字段 |
|---|---|---|
| 聚合开始 | `appearance.aggregation.started` | run/step/character、input fingerprint、resolver version |
| 状态形成 | `appearance.state.derived` | state ID、scope、field count、source count |
| 冲突发现 | `appearance.conflict.detected` | conflict ID、field path、state IDs、scope |
| 草稿形成 | `appearance.profile.drafted` | profile ID/version/revision、state count、open conflict count |
| 聚合跳过 | `appearance.aggregation.unchanged` | input fingerprint、existing profile revision |
| 聚合失败 | `appearance.aggregation.failed` | error code、character、attempt、lease generation |
| 依赖失效 | `generation.dependency.invalidated` | old/new hash、affected snapshot/image count |

日志在事务成功后输出，业务表仍是事实真值。事件规范遵守[可观测性与日志检查](13-observability-logging-and-cost.md)。

## 11. 验收测试

- 相同输入重复运行不会增加 State、Conflict 或 Profile 版本；
- 少年黑发、老年白发形成两个阶段，不产生冲突；
- 同场景同现实层级的蓝眼/黑眼产生开放冲突；
- 梦境状态不污染现实 canonical 状态；
- 子时间线分支前继承、分支后独立；
- 临时表情不跨场景延续，持久疤痕在没有终止证据时继续有效；
- 人工确认值不被后续自动聚合覆盖；
- 源版本替换只重算受影响人物，并保留历史批准版本；
- Worker 在保存前后崩溃均可恢复，不产生重复记录；
- 陈旧 `lease_generation` 和错误 `If-Match` 都被拒绝；
- Profile 有开放冲突时不能批准或进入图像生成；
- Snapshot hash 对同一输入稳定，对有效事实变化敏感。

## 12. 完成定义

只有满足以下条件，才能把[当前实现状态](00-current-status.md)中的“外观状态与冲突”“渲染档案审批”升级为完整闭环：

1. `aggregate_appearance` 已进入 Pipeline；
2. 有迁移、Worker、Service、纯策略和集成测试；
3. 支持幂等恢复、人工值保护和依赖失效；
4. API 可以从真实提取结果走到可批准 Profile，不依赖测试预置 State；
5. `/capabilities` 和追踪矩阵同步更新；
6. 上述关键日志已插桩并有固定夹具。

---

[← 上一篇](16-local-development-and-runbook.md) · [文档索引](README.md) · [下一篇 →](18-image-generation-implementation-contract.md)
