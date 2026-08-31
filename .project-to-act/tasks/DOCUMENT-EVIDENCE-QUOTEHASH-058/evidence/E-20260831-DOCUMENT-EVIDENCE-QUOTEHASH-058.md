# E-20260831-DOCUMENT-EVIDENCE-QUOTEHASH-058

## 结论

文档绝对 span、事实/evidence 原文回放、重叠 Chunk 安全去重和统一文档证据产物已实现。N2 grounded packet v6 已取消逐 quote hash；确定性来源链和上层 hash 保留。任务通过验收，人工人物归属质量 Gate 不在本任务范围内，Lifecycle Stage 5 保持 `in_progress`。

## 版本与契约

- Schema：`3.10.0-draft1`
- Runtime：`0.1.0.dev10`
- N2 packet：`grounded-character-packet-v6`
- M1 chunk/summary：`m1-chunk-result-v4` / `m1-batch-summary-v3`
- 文档产物：`document-character-evidence-v1`
- 去重策略：`document-overlap-safe-fact-dedup-v1`

## 实现结果

- 绝对位置严格按 `chunk_source_span.start + local_span` 计算。
- 每条事实与来源 evidence 都回放到完整文档并逐字校验，失败关闭。
- 去重键包含人物来源、人物标签、原文事实、文档事实 span、category、attribute 和 value。
- 相同 quote 的不同人物、文档位置或结构解释不合并。
- 合并项保留全部 `source_occurrences`，含 Chunk ID/hash/span、local/promoted ref、原始 evidence quote、局部与绝对 span。
- N2 不再计算或输出 `quote_hash` / `mention_quote_hash`；保留 document、chunk、packet、fact 和 artifact/audit hash。
- 新旧 M1 chunk 结果版本隔离，历史 runs 未改写。

## 斗破离线汇总

- 输入：既有 M1/M2/N3/promotion 只读产物与 `tests/小说/斗破苍穹前5章.txt`。
- 输入 Chunk facts：61。
- 文档 facts：60，其中 exact 49、promoted 11。
- 重叠副本删除：1；source occurrences：61；source chunks：7。
- 唯一合并项：`萧熏儿` 的 `微笑的小脸`，文档 span `[9130,9135)`；Chunk 4 局部 `[2380,2385)` 与 Chunk 5 局部 `[130,135)` 都保留。
- 输出：`runs/doupo-first5-n3-promotion-dev9-20260831/document-character-evidence.json`。

## 验证

- `python -m unittest discover -s tests -v`：96 tests passed。
- 文档产物通过 Draft 2020-12 `DocumentCharacterEvidence` 实例校验。
- `python -m compileall -q src tests`：退出 0。
- `git diff --check`：退出 0，仅既有 Windows LF/CRLF 提示。
- Project-to-Act `--check`：managed/configured，模板完整。
- Lifecycle `validate`：valid，revision 2，Stage 5 `in_progress`。

## 产物 SHA-256

- `document-character-evidence.json`：`4adc7b8277a6ddf03d76dc2ed59786d8f5dc4428d2fe78f169e5bf35a8a3a020`
- `src/novel_character_generator/document_evidence.py`：`aea3c5e3dc5b03d4bd19718367e9b6872a4818fca1958593bb3779224efa3d98`
- `src/novel_character_generator/grounding.py`：`ecbfd13b524b6991f6a1fae025eec0b3e742e44fd722dd91a237ff7246d874d5`
- `docs/contracts/simplified-character-evidence-v3-model-schemas.json`：`370a68662a14cc978396b499c68aa2f5bc6c8cecb97586d59290fb251fceb261`

## 能力边界

- 本产物只做确定性事实汇总，不按同名执行跨 Chunk 语义人物合并，也不生成全局 `character_id`。
- 结构不同但原文相同的事实会保留，供后续质量统计与人工规则决定，避免误删。
- 本轮不调用模型，不产生 Provider 费用。
