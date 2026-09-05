# LABEL-REVIEW-PROJECTION-073

任务已完成。Stage 5 保持 `in_progress`，lifecycle revision 仍为 2。

真实 registry 审计得到 7 个 characters、17 个 labels、9 个历史 review 和 1 个 unresolved binding。8 条 `partial_identity_evidence_grounding` 的 subject 已与 candidate 收敛到同一最终 character；“看门的青年”仍是唯一真正需要人工处理的 unresolved。

dev25 已交付纯代码派生视图：保留 Registry 原始标签与 review，新增正交 `label_kind + label_stability`，并把完整 `audit_items` 与精简的 `actionable_review_items` 分开。不会修改 Registry，也不会新增模型节点。

真实输出包含 7 个 characters、17 个 labels、9 个 audit items、8 个 resolved/audit-only 和 1 个 actionable；“大师”投影为 `title + stable`，唯一 actionable 是“看门的青年”。重复生成的 artifact SHA-256 稳定为 `CABCB611F95144C5E29DFC272A3732FD1A6AD64D0D969DD3EBA89F4BF89C459D`，Provider 调用为 0。

最终验证为 `180 passed, 13 subtests passed`；compileall、Draft 2020-12 真实实例、diff check 与两套治理校验均通过。测试过程中曾因新增契约测试的插入位置错误触发一次 `KeyError: transition_policy_version`；该测试结构错误已修正，未涉及运行时逻辑，最终全量回归已关闭。

下一任务为 074：先建立 active applicability 与有效期重叠，再编译 render-ready profile。不得把 observation 位置当成跨 StateSegment 有效性，也不得在有效期重叠未知时把 072 的 unclassified 强制标为 true conflict。
