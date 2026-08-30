# E-20260829-PIPELINE-V2-M1-REAL-OWNER-025

- 时间：2026-08-29，Asia/Shanghai。
- 用户意图：第 3 章真实 Chunk 包含多个老者，需要区分局部 owner，并增加青衫老者样例。
- 数据变更：把原 `elder` 拆为 `qing_robed_steward` 与 `moon_white_elder`；二者均不接受歧义泛称“老者”。
- 新增金标：`qing_robed_steward_clothing`，逐字引文“一名青衫老者”，owner policy 为 required，绑定 `qing_robed_steward`。
- 既有金标重命名：`moon_white_elder_visual_profile` 只绑定 `moon_white_elder`。
- 数据集版本：`m1-visual-evidence-real-v2.3-draft`；Dataset Schema `visual-evidence-evaluation-dataset-v2.2`；Prompt `visual-evidence-discovery-prompt-v2.5`；Rubric `visual-evidence-evaluation-rubric-v2.2`。
- 数据集 SHA-256：`2df289bf84c3b81e88e5f565c5d387dcc5825cbe35ac17a7c1b27ee19f2e0a8a`。
- 构建器 SHA-256：`ff07a9cc3c2f5419bb3dc72e948b9159ac5a7b905c7dcf396770b993c7341bd0`。
- 测试文件 SHA-256：`68acfb3d6cbd00348660f5fafff56ff4304d83499d862c933036f4705ed806c6`。
- 构建验证：运行真实集构建器，输出 10 cases，退出 0。
- 定向验证：visual evidence evaluation service 单测 15 passed，退出 0。
- 全量验证：Pytest 80 passed；Ruff 全仓通过；Mypy strict 通过（36 source files）；`git diff --check` 退出 0。
- 金标验证：10/10 pass、0 review、0 fail，evidence coverage recall 与 quote fidelity 均为 1。
- Provider：未调用；数据状态保持 `draft_user_review_required`，不能作为真实 Chunk 质量或发布 Gate。
- 生命周期限制：既有 `AGENT_LIFECYCLE.json` 不符合当前 validator，本任务未修改其 revision、状态或转换历史。
