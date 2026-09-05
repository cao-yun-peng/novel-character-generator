# LABEL-REVIEW-PROJECTION-073 验收证据

## 架构边界

- `document-character-registry-v1` 继续是 identity、来源标签与历史 review 的唯一事实源；投影不回写 Registry。
- `label_kind` 与 `label_stability` 正交，来源 `label_role` 与 `globally_unique` 仅以 `source_*` 字段保留，防止下游把旧语义误当成修正结果。
- `audit_items` 一对一保留全部 Registry review、subject/candidate 引用、issue 和 Grounding 证据；`actionable_review_items` 只保存当前工作队列所需引用，不复制证据。
- review 是否关闭只由最终 identity graph、cannot-link 和 unresolved binding 确定；本任务不新增模型节点或 Provider 调用。

## 实现证据

- 新增 `label_review_projection.py`，实现输入契约验证、稳定 label ID、确定性 kind/stability 映射、preferred label 选择、review 状态投影和引用失败关闭。
- 新增 `build-document-character-label-review-projection` CLI、`document-character-label-review-projection-v1` Draft 2020-12 Schema 与 package exports。
- 单测覆盖 proper name、alias、title、relationship、description 语义，resolved same/different、unresolved actionable，输入数组重排稳定性，以及重复/未知 review 和 unresolved 不一致的失败关闭。
- “大师”保留 `source_label_role=name` 与 `source_globally_unique=true`，派生结果为 `title + stable`；“唐三”为 `proper_name + stable`。

## 真实确定性构建

- 输入 Registry SHA-256：`9FF571B51398B734427303BBAAE2803409F6280EA8A2107A15759236543C1EE9`。
- 输出：7 characters、17 labels、7 preferred labels。
- kind 分布：5 proper name、1 alias、3 title、1 relationship label、7 descriptive labels、0 unknown。
- stability 分布：8 stable、9 contextual、0 temporary、0 unknown。
- 9 条历史 review 全部保留；8 条为 `resolved/audit_only`，唯一 actionable 为“看门的青年”。
- `model_calls=0`；重复生成 artifact SHA-256 均为 `CABCB611F95144C5E29DFC272A3732FD1A6AD64D0D969DD3EBA89F4BF89C459D`。

## 验证

- `180 passed, 13 subtests passed`。
- `python -m compileall -q src tests` 退出码 0。
- Draft 2020-12 `DocumentCharacterLabelReviewProjection` 真实实例校验通过。
- 输入数组重排测试证明 label/review ID、排序与规范化 source registry hash 稳定。
- 最终 `git diff --check`、Project-to-Act `--validate` 与 Agent lifecycle `validate` 退出码均为 0。

新增契约测试时曾因断言插入位置错误出现一次 `KeyError: transition_policy_version`；该测试结构问题已修正，未涉及运行时逻辑，最终全量回归已关闭。

本任务验收 Label/Review 派生视图，不包含 074 active applicability、完整 true-conflict 判定、render-ready Profile Compiler 或 075 人工模型质量 Gate。
