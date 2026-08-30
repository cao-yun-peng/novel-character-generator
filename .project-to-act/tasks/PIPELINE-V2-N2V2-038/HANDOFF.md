# N2 v2 纵向切片交接

状态：工程 Gate 通过。

N2 只消费当前 Chunk 和 M1 v2 Artifact，确定性地产生可定位证据或 rejected/deferred 分流，不进行视觉语义解释，也不写入数据库。

## 已实现

- `evidence-grounding-input-v2` → `grounded-evidence-packet-v2`。
- 唯一逐字/仅空白差异唯一：生成 source span、quote hash、句级上下文、context hash 与稳定 candidate ID。
- 重复逐字引文：`deferred_items/ambiguous_evidence`；owner 不用于猜 occurrence。
- 文字或标点改写：`rejected_items/quote_not_in_chunk`。
- 确定性重复候选拒绝，超出上下文预算延后。

## 验证

- 全仓库 96 项测试、Ruff、Mypy、diff check、Schema JSON 与 Project-to-Act 校验通过。
- 未调用 Provider，未接入默认主链，未写数据库。
