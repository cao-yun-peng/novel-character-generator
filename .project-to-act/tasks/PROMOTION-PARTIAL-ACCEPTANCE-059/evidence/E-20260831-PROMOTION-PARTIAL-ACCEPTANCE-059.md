# E-20260831-PROMOTION-PARTIAL-ACCEPTANCE-059

## 结论

Promotion 已从“人物内任一事实失败则整人物拒绝”改为事实级部分接受。严格 Grounding 没有放宽：唯一 occurrence 才接受；歧义 occurrence 不猜测，单独进入 review 并留在未分配池。任务通过验收，Lifecycle Stage 5 因完整人工质量 Gate 未完成而保持 `in_progress`。

## 版本

- Schema：`3.11.0-draft1`
- Runtime：`0.1.0.dev11`
- Grounded promotion：`grounded-promoted-describe-characters-v6`
- Grounding policy：`promotion-partial-fact-acceptance-v1`
- N3 promotion task/summary：v2

## 行为验证

- 人物标签有效且至少一条事实安全唯一：建立人物并保留安全事实。
- 重复、歧义或不存在事实：逐条 review，不影响同人物安全事实。
- 所有事实失败：不建立人物。
- 标签歧义、跨 promoted 人物标签/已接受事实重叠：继续失败关闭。
- Review 明示 `character_index`、`fact_index`、`fact_quote` 与 `candidate_occurrence_count`。
- 保存的 envelope + model output 可在 0 Provider 调用下重新 Grounding，来源文件 hash 写入 replay manifest。

## 斗破重放结果

- 来源 run：`runs/doupo-first5-n3-promotion-dev9-20260831`（只读）。
- 新 run：`runs/doupo-first5-n3-promotion-dev11-partial-20260831`。
- 模型输出重放：5/5；Provider calls：0。
- promoted characters：4→5；promoted facts：11→12。
- Review：1 条 `ambiguous_promotion_fact`，`fact_quote=青衫`，候选 occurrence=2。
- `青衫老者` 已创建；接受 `浑浊的老眼`，Chunk span `[616,621)`，文档 span `[7366,7371)`。
- 两个 `青衫` occurrence `[567,569)`、`[598,600)` 均保留在 `unassigned_fragments`。
- 文档汇总：62 Chunk facts → 61 document facts；exact 49、promoted 12、source occurrences 62。

## 验证

- 全量单测：98 passed。
- Python compileall：退出 0。
- Draft 2020-12 Schema 本体、5 个 promotion v6 结果和文档实例：通过。
- 文档绝对 span/原文回放：62/62 通过。
- `git diff --check`：退出 0，仅 Windows LF/CRLF 提示。
- Project-to-Act `--check`：managed/configured，模板完整；Lifecycle `validate`：valid，revision 2，Stage 5 保持 `in_progress`、不转换。

## 产物 SHA-256

- `promotion-grounded-results.json`：`3a29aee2622e12e0c6154dbac2761e6e327795b655acf05cad73ef3317b5267c`
- `document-character-evidence.json`：`f7553293ad89eb3b89a00ee67ab7c201f775fc1388d207d45314ac3e858c43c1`
- `summary.json`：`dea07d5aa889ac440b363dd18d75c0b508d2c28cff17f03a02e850efdee3269e`
- `src/novel_character_generator/m2.py`：`280b6b5f1a20c8d6ca4e5bb2e9af2ef5ae41e9efe710bf27a019454a9af72a1f`
- `src/novel_character_generator/promotion_replay.py`：`8ec7dc7ea732ecb01c255e058bcd40f3771eadfe139981f1ff665b6e6c8d859d`
- Schema：`6c7fbf285e803427c60d215f00c4464652fc5e6824b7d22773d7220c83af68d7`

## 未覆盖

- 本轮没有重新调用 DeepSeek，不评估新模型输出变化。
- 当前单样本证明已修复已知失败，不代表 promotion 全量人工质量阈值已达标。
