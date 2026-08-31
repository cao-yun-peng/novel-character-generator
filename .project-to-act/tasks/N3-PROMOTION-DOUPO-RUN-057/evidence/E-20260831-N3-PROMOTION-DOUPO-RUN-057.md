# E-20260831-N3-PROMOTION-DOUPO-RUN-057

## 结论

N3 Chunk 内 span 仲裁、剩余池重建、可恢复 promotion 及斗破前5章真实纵向切片完成。执行链路通过本任务验收；一个重复 quote 的 promotion 候选按规则进入 review，人工人物质量与跨 Chunk 去重未验收，Stage 5 保持 `in_progress`。

## 输入与版本

- 原文：`tests/小说/斗破苍穹前5章.txt`
- 原文 SHA-256：`7ca3fd295b5d0d454ca0b0bac2f4a49f2271602fc8e55bca2f120bb11d85172a`
- M1 来源：`runs/doupo-first5-m1-scope-v4`
- M2 来源：`runs/doupo-first5-m2-dev7-20260831`
- Schema：`3.9.0-draft1`
- Runtime：`0.1.0.dev9`
- Provider/model：DeepSeek Responses API / `deepseek-v4-flash`

## 实跑结果

- N3：7 Chunk、18 target packets、50 exact facts、5 describe pools。
- describe 仲裁：consumed 0、conflicted 0、remaining fragments 10。
- promotion：planned/succeeded/failed = 5/5/0；collective task 0。
- 接受 4 个 promoted characters、11 条 grounded facts；全部 `match_mode=exact`。
- `character_label_span` 为 0；标签直接复用已验证 `mention_quote`。
- Review 1：`青衫老者` 的模型事实 `青衫` 对应两个剩余 occurrence，触发 `ambiguous_promotion_fact`；人物未创建，3 个源片段保留在 `unassigned_fragments`。
- Usage：input 10,969、output 2,724、reasoning 2,157、total 13,693 tokens。
- 断点恢复：第二次运行 resumed 5、new provider calls 0。

## 验证

- 90 tests passed，13 subtests passed。
- 7 个 `N3ChunkResolutionResult`、18 个 `N3ValidatedAppearancePacket`、5 个 `N3DescribePoolResolutionResult`、5 个 `M2GroundedPromotedDescribeCharactersResult` 通过 Draft 2020-12 实例校验。
- `failures.json` 为空；5 条 trace 不含 API Key、Prompt、正文或 reasoning 文本。
- `git diff --check` 退出 0；只有既有 CRLF 转换提示。
- 运行报告：`runs/doupo-first5-n3-promotion-dev9-20260831/RUN_REPORT.md`。

## 产物与 SHA-256

- `runs/doupo-first5-n3-promotion-dev9-20260831/n3-chunk-results.json`：`618bd586307d85dea0dfd9107f0ba3adc4eca62c149382d85b806d7f31e41b37`
- `runs/doupo-first5-n3-promotion-dev9-20260831/promotion-model-outputs.json`：`e3482d872223a546e62efd9fbe6e4599ab12d8495571ccbe847575ef5b7603a9`
- `runs/doupo-first5-n3-promotion-dev9-20260831/promotion-grounded-results.json`：`83573e6cb3627716d8a6eae372cfa209cb8a9488f2d7b4ed9ada9503ae1966f8`
- `runs/doupo-first5-n3-promotion-dev9-20260831/summary.json`：`3c82cb82398dfe002cf2aaa6c08fff77a9675b4d112be46b9861a2aabb8ed717`
- `src/novel_character_generator/n3.py`：`caf1408b86f8f36bf6c71d217b6a09cc37c3b33818e74a6ca270efaba41e7046`
- `src/novel_character_generator/n3_batch.py`：`7941f50568b8e39e21518475b1ff98913276901e2ebf901dee0a710944f8f267`

## 能力边界

- N3 只处理 Chunk 局部字符 span，不完成文档绝对 span 换算或跨 Chunk 合并。
- 完整执行表示结构化调用、来源回放、冲突隔离和失败关闭生效，不表示模型人物归属达到人工质量阈值。
