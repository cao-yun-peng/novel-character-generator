# APPEARANCE-SEMANTIC-RELATIONS-072 验收证据

## 架构边界

- 关系候选只来自同 `character_id`、同 `state_segment_id`、同 exact `attribute` 的 observed facts。
- 先保存保留原值、方向和规则来源的 relation graph，再从 `equivalent` 连通分量派生 normalized proposition。
- `compatible` 与 `unclassified` 不触发合并；raw `category/attribute/value`、canonical fact 和 provenance 不被覆盖。
- 没有 active applicability 时不自动生成 `true_conflict`；本任务不新增模型节点或 Provider 调用。

## 实现证据

- 新增 `appearance_semantic_relations.py`，实现稳定 relation/proposition ID、确定性 pair 分类、equivalent 连通分量归并和引用完整性失败关闭。
- `document-character-appearance-states-v5` 在原状态产物内新增关系策略、归一策略、`relations` 和 `normalized_propositions`，没有建立第二份可编辑事实源。
- 完全相同值输出 `equivalent + symmetric + exact_value`；安全子串输出有方向的 `compatible + value_containment`；其余输出 `unclassified + unknown + no_safe_deterministic_rule`。
- 单测覆盖三条分类路径、跨人物/segment/attribute 隔离、输入重排稳定性，以及重复 observation、assignment state 篡改和越界 observation 的失败关闭。

## 真实离线重放

- 来源：斗罗 dev23 保存的 17 个 Chunk 模型输出。
- 结果：17/17 resumed，`new_provider_calls=0`，6 grounded transitions，4 review。
- v5 产物：7 characters、14 StateSegments、109 observed facts、37 relations、103 normalized propositions。
- 关系分布：7 equivalent、5 compatible、25 unclassified、0 temporal change、0 state change、0 true conflict。
- 原状态统计保持 life 28、form 7、scene 1；`semantic_model_calls=0`。
- 重复重放 artifact SHA-256 均为 `83D1A87EDFE83A8591122AEC5754861AFEE26D5531D0506C2639B74577071CDB`。

## 验证

- `171 passed, 13 subtests passed`。
- `python -m compileall -q src tests` 退出码 0。
- Draft 2020-12 `DocumentCharacterAppearanceStates` 真实实例校验通过。
- `git diff --check`、Project-to-Act `--validate` 与 Agent lifecycle `validate` 退出码 0。

本任务验收确定性 relation/proposition baseline，不宣称 25 条 unclassified 已解决，也不包含 active applicability、完整 true-conflict 判定、074 Profile Compiler 或 075 人工模型质量 Gate。
