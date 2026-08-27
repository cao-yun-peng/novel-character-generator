# 项目版本

> 只在版本号、发布状态、升级路径或兼容性发生变化时读取和更新。

## 当前版本

- 版本号：`0.0.0`
- 发布状态：未发布
- 兼容性说明：视觉候选 Schema 升为向后兼容的 `visual-observation-v3.2`（时间信号增加通用 `other` 桶）；Prompt 为 `visual-extraction-prompt-v2.4`、`entity-resolution-prompt-v1.4`；生产持久化链继续使用 `character-entity-resolution-v1`；开发原始响应契约为 `raw-model-response-v1`；数据库 head 为 `f9a1e5c72d30`。
- 最后更新：2026-08-27

## 下一版本计划

- 目标版本：尚未定义
- 计划内容：尚未定义
- 发布条件：尚未定义

## 版本历史

按时间倒序追加：版本号、日期、状态、主要变更、原因、兼容性、证据 ID 和 Gate 结果。

- `raw-model-response-v1`，2026-08-27，开发增量通过：R1/R2 Provider 原始响应按调用持久化并由开发管理员页签读取；数据库需要升级到 `f9a1e5c72d30`，默认关闭且生产拒绝启用；证据 `E-20260827-DEV-RAW-001`，不代表逐 token streaming 或失败响应捕获。
- `character-entity-resolution-v1`，2026-08-27，开发增量通过：逐 Chunk 累计记忆、十章/尾批收敛、final-only Observation、调用审计和恢复；改变自动抽取写入时序，需要升级数据库到 `d9a42b71c305`；证据 `E-20260827-R2-ENTITY-001`，不代表 R2 跨作品质量 Gate 或生产发布。
- `visual-observation-seed-v2`，2026-08-26，开发中：结构/value/evidence 分层、pass/review/fail 三态和局部等价值；兼容生产 `visual-observation-v3`，但评测结果 JSON 增加字段，证据 `E-20260826-R1-EVAL-004`，不代表发布 Gate。
- `visual-extraction-prompt-v2.2`，2026-08-26，开发中：增加通用语义边界、原子拆分、最小证据、原文语言和值规范；兼容 `visual-observation-v3`，证据 `E-20260826-R1-PROMPT-003`，不代表发布 Gate。
- `visual-observation-v3.2` / `visual-extraction-prompt-v2.4` / `entity-resolution-prompt-v1.4`，2026-08-27，开发增量通过：显式姓名门禁、伪年龄与字段语义门禁、通用 transformation/other 信号、age/reincarnation 阶段推导、去重与语义冲突归一化；157 项测试、Ruff、Mypy 通过；首次干净真实 run 总体 Gate 为 review，证据 `E-20260827-R123-REAL-001`。
