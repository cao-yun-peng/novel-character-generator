# R3-PHASE-001 Handoff

- 状态：待复核
- 目标：把人物归属与人物阶段/时间作用域分开，只有 R3 final 观察可以进入聚合。
- 已完成：时间信号 v3.1 契约与定位持久化、确定性阶段/呈现/形态解析、四张表和 Alembic 迁移、独立 Worker 门禁、审核/阶段/人工修订 API、聚合兼容与失效处理。
- 关键反例：同一 mention 中“前世黑发”只绑定 hair observation 并激活；“三年后白衣”不会继承前世阶段，保持 `needs_review/pending`。
- 验证：Ruff 通过；Mypy 114 个源码文件通过；Alembic 唯一 head 为 `a3e8c1d4f620`；Pytest 135 passed。
- 证据：`evidence/E-20260827-R3-PHASE-001.md`。
- 未覆盖：真实 Provider 的跨作品阶段质量、事件级时间循环/平行世界、条件式语义 resolver、人工修订后自动创建增量聚合 Run。
- 下一建议：构建 R3 阶段歧义黄金集并测 phase/scope F1；随后实现审核后自动增量重聚合。
