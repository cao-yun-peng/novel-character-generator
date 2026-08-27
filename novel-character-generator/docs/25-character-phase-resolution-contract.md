# R3 人物阶段与时间作用域解析契约

## 1. R3 负责什么

R1 提取原子视觉事实和显式时间信号，R2 判断 mention 属于哪个人物，R3 才决定这些事实属于人物的哪个人生阶段、采用何种叙事呈现方式、是否为主观/传闻/假设事实，以及作用范围持续到哪里。

```text
R1：视觉事实 + 显式时间信号
  → R2：mention → character（人物归属）
  → R3：observation → timeline / life phase / presentation / reality / transformation / range
  → 仅 final 作用域激活 Observation
  → 外观聚合
```

因此 R2 完成不等于事实可以聚合。R2 物化的 `FeatureObservation` 初始为 `pending`；R3 写出 `final` 的 `ObservationScopeBinding` 后才转为 `active`。`needs_review` 继续保持 `pending`，不会污染 `AppearanceState`。

## 2. 输入与信号

`VisualCandidateExtractionResult` 支持两类已定位时间信号：

- 事实级信号：只约束所属视觉事实，不允许按同一个 mention 扩散到其他事实；
- mention 级信号：没有事实绑定时，可约束该 mention 对应的观察；没有明确 `entity_ref` 的全局信号保存为 unresolved，进入审核列表。

当前信号种类包括 `age`、`life_phase`、`time_jump`、`presentation` 和 `transformation`。Provider 只提取原文明示信号，不生成数据库 ID，也不推断时间线。

## 3. 确定性解析规则

基础主链由 `character-phase-resolution-v1` 纯服务完成：

- 规范化已知人生阶段，如 `past_life`、`reincarnated_childhood`、`childhood`；未知但明确的阶段生成稳定键；
- 按首次出现章节排序阶段，并用下一阶段起点关闭上一阶段的章节上界；
- 将回忆、预叙、梦境、幻觉、传闻和假设映射到 `presentation_mode` 与 `reality_status`；
- 明确变身/形态信号生成稳定 `transformation_state`，基础实现按当前章节限制作用域；
- 同一事实出现多个阶段、多个呈现模式、多个形态，或只有 `time_jump` 而没有可落地阶段时，输出 `needs_review`；
- 没有高风险时间信号的普通事实可输出 phase-less `unknown` 作用域并激活，保持与既有聚合兼容。

R3 不用章节位置臆造“前世/童年”等阶段，也不会让第二次模型调用静默覆盖歧义。

## 4. 持久化与恢复

迁移 `a3e8c1d4f620` 新增：

- `temporal_signals`：保存原文信号、人物/事实绑定和解析状态；
- `character_life_phases`：保存人物阶段、时间线、章节边界、证据和 revision；
- `observation_scope_bindings`：保存每条观察的最终或待审时间作用域；
- `character_phase_resolutions`：保存每个人物每个 Run 的输入哈希和解析结果。

Worker 步骤固定为 `resolve_character_phases`，位于 `extract_characters` 与 `aggregate_appearance` 之间。它按人物 checkpoint，输入变化会失败关闭；完成后只激活 final 观察，再排队聚合。

## 5. 查询与人工修订

- `GET /api/v1/novels/{novel_id}/temporal-review`：列出未绑定时间信号和 `needs_review` 作用域；
- `GET /api/v1/characters/{character_id}/life-phases`：列出人物有效阶段；
- `POST /api/v1/characters/{character_id}/life-phases/{phase_id}/resolve`：使用 `If-Match` revision 和 `X-Actor-ID` 修订阶段标签/章节范围/状态。

人工修订会写 `DecisionRecord`，同步关联 Observation 的作用域，并使现有外观状态、冲突和渲染档案失效。当前只标记 `reaggregation_required`，尚未自动创建新的聚合 Run。

## 6. 当前边界

本次实现是 R3 基础主链，不代表真实小说阶段解析质量 Gate 已通过。尚待补充跨作品阶段黄金集、时间循环/平行世界事件级解析、条件式语义解析 Provider，以及人工修订后的自动增量重聚合。歧义在这些能力完成前保持可见且失败关闭。
