# RENDER-PROFILE-COMPILER-074

任务已完成并通过 Stage 5 退出 Gate。生命周期现为 Stage 6 `ready`、revision 3。

输入边界冻结为 dev18 fact groups、dev24 appearance states 与 dev25 Label/Review projection。编译器只生成可丢弃派生视图，不回写任何来源层，也不增加模型调用。

首版以 `character_id + {life_stage, form_state, scene_state, document_position}` 选择唯一 StateSegment。歧义或无匹配时输出空 traits 和机器可读 warning，不跨 segment 混合。Applicability 将确定 active 与 unknown-persistence provisional 分开；只有确定 active overlap 的 true conflict 才进入冲突列表。

斗罗 dev26 四个 selector 已全部编译，得到 7 active、40 provisional fact bindings，2 stable、33 variant、10 scene traits，4 transitions、0 unresolved conflicts 和 17 个聚合 warnings。大量 provisional 是上游 unknown persistence 的明确暴露，不是失败或静默猜测。重复产物 SHA-256 为 `B0EF3F6F47716F2CE2DBD133EDA5FF8E5738E0E4598BE9B93BBB38DD01629A3B`，Provider 调用为 0。

最终回归为 `191 passed, 13 subtests passed`；compileall、Draft 2020-12 requests/真实实例、diff check、Project-to-Act 与 lifecycle 校验通过。初始新增测试曾把 fact span 的半开 end 当作 active，修正为 provisional 断言；初始真实 Schema 校验曾发现 `identity_labels.character_id` 缺失，字段补齐后关闭。两次失败均保留在证据中。

下一工作为 075 Stage 6 人工质量 Gate：先冻结标注规范、样本与阈值，再评测，不用当前结构化系统 Gate 替代模型准确率。
