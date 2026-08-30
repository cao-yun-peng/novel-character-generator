# E-20260829-PIPELINE-V2-M1-EVAL-V24-027

- 时间：2026-08-29，Asia/Shanghai。
- 用户意图：修改 Dataset/Rubric，形成 v2.4-draft。
- 数据集：`m1-visual-evidence-real-v2.4-draft`，Schema `visual-evidence-evaluation-dataset-v2.4`，状态 `draft_user_review_required`；SHA-256 `5b0516cae57b06955b444b62e1b99e06296e2adf78e12441b5cd526968d915ae`。
- Dataset 变更：001 增加“萧媚”；002 增加“萧薰儿”；003 增加完整人物短语与“男孩儿”；007 增加去掉篇章转折词但保留完整推断关系的逐字跨度，以及唯一的“暗黄的脸色”视觉跨度。
- Rubric：`visual-evidence-evaluation-rubric-v2.4`；实现 SHA-256 `21991e818c7de057469a6b0c8dc67bb3c84c8d53aef8746711466be7d3e27bc9`。
- Rubric 变更：不同局部 owner 不得共享标准化 accepted mention；一个模型候选同时覆盖多个未匹配金标时显式 fail；evidence quote 只有在 Chunk 中恰好出现一次才计入 quote fidelity。
- 向后兼容：加载器仍接受短集 Schema v2.2；短数据集内容、版本和 approved 状态未修改。
- 构建器 SHA-256：`529f931db8d778aab733b6509938d0cbe622e64cda0e7676659996e40cf34389`。
- v2.4 金标自评分：10 pass / 0 review / 0 fail。
- 真实同输出离线重评分：0 pass / 5 review / 5 fail；required evidence 18/26；owner required 14/22；quote unique-valid 80/82；evidence recall 0.6923；candidate precision 0.3585；quote fidelity 0.9756；owner required recall 0.6364；owner binding precision 0.3585。
- 剩余 fail：004/005/006/008/010；001/002/003/007 与 009 为 review，不再因已知 alias/跨度覆盖不足判 fail。
- 真实重评分报告：`data/diagnostics/m1-v2.5-real-v2.3/real-outputs-rescored-v2.4-draft-report.json`，SHA-256 `4655a63e81ae187d51e4b0f8103412e4091aee4dd864889ba3f514a47bb421b1`。
- 短集回放：Rubric v2.4 下 16 pass / 0 review / 0 fail，六项核心指标 100%。
- 短集回放报告：`data/diagnostics/m1-v2.5-real-v2.3/short-approved-outputs-rescored-rubric-v2.4-report.json`，SHA-256 `ebc697386197b570dee65f3678f8da63c81588f66e93f3a02f473c5f6aeebb86`。
- 自动验证：Pytest 83 passed；Ruff 全仓通过；Mypy strict 通过（36 source files）；`git diff --check` 退出 0；Project-to-Act validate 通过。
- Provider：未调用；复用 v2.3 已保存 outputs，Prompt v2.5 未修改。
- Gate：v2.4 数据集待用户审核；M1 真实 Chunk Gate 未通过。
- 生命周期限制：既有 `AGENT_LIFECYCLE.json` 不符合当前 validator，本任务未修改其 revision、状态或转换历史。
