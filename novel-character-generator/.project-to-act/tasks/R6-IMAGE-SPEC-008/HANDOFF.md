# R6-IMAGE-SPEC-008 Handoff

- 状态：Mock 纵向切片与自动化 Gate 已完成；待真实上游 provenance/审批适配。
- 范围：期望字段适配、场景简报、三档就绪度、Provider 中立规格、Mock 链路接入。
- 边界：不接真实收费 Provider；不做漂移审计、gate、baseline 锁定；不把当前 R1-R3 真实输出视为已通过。
- 兼容：现有请求默认按探索概念图处理；`ResolvedCharacterRenderFields` 是未来真实字段接线缝，支持目标目录 `subject/eyes/facial_hair` 和显式 stage block。
- 安全：普通请求生成的 `SceneRenderBrief` 固定为 draft，不能自批一致性场景；来源不完整只允许 concept；submit 异常进入 `submission_unknown`，重启禁止盲重提。
- Provider：只接收冻结的 `ImageRenderSpec`，不接收原始 ORM/Profile/context payload；真实收费 Provider 未接入。
- 验证：6 项图像定向测试、202 项完整 Pytest、全仓 Ruff、117 个源码文件 Mypy 均退出 0；0 真实 API 调用、0 数据库迁移。
- 证据：`evidence/E-20260827-R6-IMAGE-SPEC-008.md`。
- 下一步：把 R1–R3 最终真实字段及审批记录映射为 typed provenance；再补 WorkflowProfile、真实 Provider reconcile/download/budget，以及 DriftAudit/Gate/Baseline。
