# M1 v2 视觉证据发现实现交接

## 已完成

- 新增 M1 v2 Pydantic DTO、机器 Schema、Prompt、OpenAI-compatible Provider、确定性 ID 物化和不可变 shadow Artifact。
- M1 v2 模型输入只包含当前 `chunk_text`、Prompt 和输出 Schema；`previous_tail` 保留在内部输入信封但不会发送给模型。
- M1 v2 不输出类别、raw proposition、epistemic、signal、reason 或 canonical field；N2/M2 v2 仍未接入默认主链。
- 新增 15 条 `draft_user_review_required` evidence-coverage 测评集、离线评分器和真实运行脚本；旧 v1 数据集与实现保持兼容。

## 验证

- `uv run --project . ruff check src scripts tests`：通过。
- `uv run --project . python -m mypy src scripts`：通过，35 个源文件。
- `uv run --project . python -m pytest -q`：通过，69 项测试。
- `git diff --check`：通过。
- project-to-act `--validate`：`valid: true`。

## 下一步

1. 用户审核 15 条样本的最短证据跨度和 owner 预期；审核前不得把数据集改为 approved。
2. 实现 N2 v2 `GroundedEvidencePacket`，接入 M1 v2 候选并保留 quote/span/hash 失败关闭。
3. 再实现 M2 v2 local semantic parsing；legacy v1 只能在迁移完成后删除。
