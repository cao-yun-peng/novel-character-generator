# E-20260829-PIPELINE-V2-M1-EVAL-022

- 时间：2026-08-29，Asia/Shanghai。
- 基线 Git：`01a4930`；工作树包含用户此前未提交的 M1 v2 相关改动，本任务未回滚或覆盖无关内容。
- 用户意图：修正年龄金标、三态 owner、语义完整且 N2 唯一可定位的引文规则、确定性真实运行路径与哈希元数据，并从 `tests/测试` 建立 10 条真实 Chunk 数据集。
- Prompt：`visual-evidence-discovery-prompt-v2.2`，SHA-256 `3e814ed502032bec6592ec0d6eaebb5648c41274f90ab8c25a3a1d7a481efd2b`。
- 短数据集：`m1-visual-evidence-short-v2.2-draft`，16 条，SHA-256 `84c9695dc9fb10db2d2de279423f03ea3f02e7eea7755ee724a1abce616ec406`。
- 真实数据集：`m1-visual-evidence-real-v2.2-draft`，10 条，SHA-256 `63d71d834df668fb585a5be4bad1e07018df0c414c58977c32846ab64b6fef97`。
- Rubric：`visual-evidence-evaluation-rubric-v2.2`，实现 SHA-256 `a9df4e73ecd1dbb723c8096efa9bd542f79de8f9be9cb31323644d54c8f0413b`。
- 确定性校验实现 SHA-256：`1a8f8a4dd552b29bba1a07e0f301c618a740c4a0661df1989576ef8eca6eef68`。
- 真实运行器 SHA-256：`1819578746298bba8e5fec63f2ff7d0271085c1260c1d9e8212187e0ada00897`；构建脚本 SHA-256：`394797b6ec223fd918a8e7c3846ac06b26b1db203c9335b3ddfee8e9feb8570f`。
- 真实来源：四份 `tests/测试` 原文，生产 `detect_chapters + build_chunks(target_tokens=1000)`；选择 chunk ordinal `1,2,9,10`、`0,3,4`、`54,55`、`19`，10/10 通过文本、chapter ordinal 与 content SHA-256 回放。
- 确定性行为：非逐字引文抛出 `visual_evidence_quote_not_in_chunk`；重复而不能唯一定位的 evidence 抛出 `visual_evidence_quote_not_unique_in_chunk`；真实运行逐 case 经过 `VisualEvidenceShadowService`。
- 运行清单：成功运行保存 prompt/dataset/rubric 与 deterministic-validation hash，以及 provider/model/wire API/reasoning/max tokens、request id、response model、attempts、latency、token usage、输入输出指纹和产物 hash；不保存 API key、raw response 或 raw message content。
- 验证：Ruff 全仓通过；Mypy strict 通过（36 source files）；Pytest 通过（78 passed）；`git diff --check` 退出 0；project-to-act `--validate` 返回 `valid: true`。
- Provider 状态：本任务未调用真实 Provider；短集和真实集均保持 `draft_user_review_required`，Prompt v2.2 尚无真实质量分数。
- 生命周期限制：任务开始前的 `AGENT_LIFECYCLE.json` 已不符合当前 validator（stage 0–4 状态值、目录型 artifacts、revision/transition revision）。本任务未伪造 revision 或转换历史，因此不能据此声明 lifecycle Gate 通过。
