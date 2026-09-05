# WEB-READY-REPAIR-PLAN-076

规划任务完成。产物为 docs/37-web-ready-repair-checklist.md，共 14 项，含优先级、依赖、验收、版本迁移和 Web 接口草案。证据为 E-20260905-WEB-READY-REPAIR-PLAN-076。

本轮由用户明确把后续 Web 使用纳入规划，数据库/服务端必要持久化和接口不再属于规划非目标；没有启动运行时修复或发布。Stage 6 已通过工具启动问题梳理，当前 in_progress / revision 4，075 最终 Gate 尚未通过。

关键边界：Snapshot 复用现有 compiler 的选择器/applicability 能力；衣着状态与叙事场景分开；高召回候选池与模型裁决预算分开；Web 绑定不可变 artifact_set，并处理 Unicode code point 与浏览器 UTF-16 坐标。

后续先执行 R06 标注协议/R12 测试入口与 R01/R02/R05 正确性修复，再实现 R03/R04 快照；按依赖接 R07/R08 身份、R09～R11 Web/证据接口，最后 R13 Viewer 与 R14 基准优化。进入实现前冻结各切片 Schema/迁移和验收，必要时登记已有阶段的重审。

所有新增能力仍是 planned。保留工作区原有 073/074 未提交修改；本轮未修改 src、tests、pyproject 或历史 runs。
