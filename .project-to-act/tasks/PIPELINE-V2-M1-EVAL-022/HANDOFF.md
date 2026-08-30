# M1 v2.2 评测契约与真实 Chunk 数据集交接

## 已完成

- Prompt 升级到 `visual-evidence-discovery-prompt-v2.2`：证据必须最小但语义完整、逐字连续并适合 N2 唯一定位；保留否定、推断、年龄、比较、presentation 和 transformation 关系。
- Dataset/Rubric 升级到 v2.2；修正 `inferred-age-006` 和 `explicit-age-007`，owner 金标拆为 `required/allowed/must_be_null`。
- 评分器把非逐字或非唯一可定位引文判为失败；真实运行器逐 case 经过 `VisualEvidenceShadowService` 的 deterministic validation。
- 真实运行清单保存 prompt/dataset/rubric SHA-256、模型配置、请求元数据、尝试次数、延迟和 token usage；不保存 API key 或原始 Provider 响应。
- 从 `tests/测试` 四份原文按生产章节切分与 `target_tokens=1000` 建立 10 条 source-backed 真实 Chunk 数据集，并提供可重放构建脚本。

## 验证

- 相关及全量测试、Ruff、Mypy、`git diff --check` 均通过。
- 短集 16 条、真实集 10 条均可加载；真实集 10/10 来源重建和金标自测通过。
- 未调用真实 Provider，两个数据集均保持 `draft_user_review_required`。

## 后续 Gate

1. 用户审核 16 条短金标和 10 条真实 Chunk 金标，重点核对语义完整跨度与 owner 三态。
2. 审核通过后才可将数据状态改为 `approved` 并运行 Prompt v2.2 真实诊断。
3. `AGENT_LIFECYCLE.json` 的历史结构仍无法通过 lifecycle validator；本任务未伪造 revision 或转换历史。
