# PIPELINE-V3-SIMPLIFIED-039

已在本地分支 `v3-simplified-character-evidence` 建立简化人物证据 V3 目标契约和机器 Schema。M1 将 evidence 直接嵌套在局部候选人物块；N2 验证 mention/evidence 存在并物化 approved evidence，允许跨人物重复；M2 按单人物并行解析；N3 将 support quote 分为 approved、review_context_only 和 rejected_hallucination。

当前只完成设计静态 Gate。下一任务应从空工程实现 M1/N2 DTO、Prompt、Provider 和服务，再实现 M2/N3。人物记忆只保留 `local_character_ref -> character_id` 占位，等待用户后续决策。
