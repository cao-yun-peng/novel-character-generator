# R1-DATA-006 Handoff

- 状态：生产修复和自动化 Gate 已完成；待新真实 Run 质量复核。
- Mention：R1 对外只使用 `explicit_name / descriptor / pronoun / unknown`；历史标签保守归一化。泛称只进入 `names`，不进入 `explicit_names`。
- 字段：`age.age → age`、`age.age_stage → age_stage`；其他 `age.*` 拒绝。所有 `clothing.*` 要求衣物/鞋履/覆盖语义，书籍、武器、药物等非衣物拒绝。
- 证据：精确匹配优先，其次空格/软标点唯一匹配，最后只允许唯一低信息单字遗漏；多位置、语义替换和跨句硬标点拒绝。保存原文精确 quote，并记录 `evidence_status` 与 `evidence_repair_kind`。
- 版本：`visual-observation-v3.3`、`visual-extraction-prompt-v2.5`、`character-entity-resolution-v1.1`、`entity-resolution-prompt-v1.5`。
- 兼容性：无需数据库迁移；旧 mention kind 可读取；Worker cursor 改用版本常量。
- 验证：67 项首轮定向、154 项全部单元、193 项完整 Pytest、Ruff、Mypy 均通过；0 真实 API 调用。
- 下一步：重启 API/Worker 后用新 Run 复测短文本，核对四类 mention、字段 warning 和 repaired evidence 审计。
- 证据：`evidence/E-20260827-R1-DATA-006.md`。
