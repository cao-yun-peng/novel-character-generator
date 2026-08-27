# DEV-RAW-001 Handoff

- 状态：已完成，待产品侧新 Run 复核。
- 已完成：开发开关、生产失败关闭、R1/R2 原始响应持久化、管理员 API、Run Inspector 页签、旧 Run 提示、迁移和文档。
- 更新粒度：每次 Provider 调用完成并通过结构校验后按 Chunk/收敛批次保存；当前不是逐 token streaming。
- 数据边界：普通 Inspector、RunEvent 和日志不含 raw payload；R3 是代码阶段不显示页签。
- 本地状态：`.env` 已启用开关，数据库已升级到 `f9a1e5c72d30`；需要重启 API 与 Worker，并创建新 Run 才能看到内容。
- 验证：Ruff、Mypy 115 源文件、Node、159 项 Pytest、Alembic head 和浏览器检查通过；浏览器控制台 0 error。
- 证据：`evidence/E-20260827-DEV-RAW-001.md`。
- 未覆盖：Schema 解析失败的 raw 保存、自动清理/保留期限和 token streaming。
