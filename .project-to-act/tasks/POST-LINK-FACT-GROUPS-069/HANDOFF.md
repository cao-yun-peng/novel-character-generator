# POST-LINK-FACT-GROUPS-069

任务已完成，状态为 `completed`。Stage 5 保持 `in_progress`，lifecycle revision 仍为 2；069 不构成 Stage 6 人工质量 Gate。

已交付 `document-character-fact-groups-v1`、`same-character-span-structure-v1`、稳定 `canonical_fact_id`、失败关闭构建器、CLI、Schema 和测试。输入 registry/profile 必须同文档、归属一致；输出保留全部 raw fact hash 和 occurrence binding，不修改输入，不做语义归一或状态推断。

斗罗 dev17 的 129 raw facts 生成 109 groups；10 个 multi-member groups 共折叠 20 个重复成员。老杰克 26→14，素云涛 29→21，其余人物零折叠；129 source fact bindings、130 occurrence bindings 全部反向回放，Provider 0。产物位于 `runs/douluo-20ch-e2e-dev13-20260831/post-link-fact-groups-dev18/document-character-fact-groups.json`。

146 项测试、compileall、Draft 2020-12 Schema/实例、重复输出 hash、输入 hash 不变、diff check 和两套治理 validate 均通过。下一任务为 `APPEARANCE-SCOPE-SCHEMA-070`。
