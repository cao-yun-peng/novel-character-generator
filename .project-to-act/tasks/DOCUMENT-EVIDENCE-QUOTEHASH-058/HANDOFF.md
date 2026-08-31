# DOCUMENT-EVIDENCE-QUOTEHASH-058

已完成。N2 grounded packet v6 不再生成 `quote_hash`/`mention_quote_hash`，M1 chunk 结果升级 v4 防止旧包混合续跑。新增纯代码文档汇总与 CLI，完成绝对 span 回放、结构安全的重叠去重、来源 artifact/chunk/fact hash 和全 occurrence 保留。斗破既有只读来源已生成 `document-character-evidence.json`：61→60 facts，唯一合并项保留两个 Chunk 来源。96 项测试和全部确定性校验通过；Stage 5 仍等待人工质量 Gate。
