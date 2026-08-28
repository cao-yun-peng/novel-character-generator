# R1-BASELINE-005 Handoff

- 状态：基线冻结完成，生产修复未开始。
- 范围：仅 R1 本地提及类型、视觉字段门禁与原文证据定位；R2 身份解析已拆到独立任务。
- 新增：7-case `r1-quality-regression-baseline:v1` 和对应可执行测试。
- 当前结果：3 个既有边界通过，5 个目标行为按 `strict xfail` 冻结。
- 红灯：`descriptor`、`age.age`、书籍误入 `clothing.type`、唯一单字漏写修复、歧义单字漏写分类。
- 绿灯：语义替换不修复、精确引文保持原文；相关 R1 定向回归共 28 passed / 5 xfailed，完整回归 175 passed / 5 xfailed。
- 生产影响：无；没有修改 Schema、Prompt、Adapter、locator、数据库或 Worker。
- 下一步：按红灯顺序实现 R1 修复；每修复一项即删除对应 `strict xfail` 并转为普通回归。
- 证据：`evidence/E-20260827-R1-BASELINE-005.md`。
