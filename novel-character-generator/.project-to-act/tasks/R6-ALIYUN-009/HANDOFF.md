# R6-ALIYUN-009 Handoff

## 当前状态

可插拔 Provider/PromptRenderer registry、DashScope 适配器、golden/provenance tests 和单张 smoke 已完成；`qwen-image-plus` 首张 1328×1328 候选图及 Prompt sidecar 已保存。任务保持进行中，因为数据库没有 approved/locked 角色档案，可信审批、漂移 Gate 和 baseline 锁定尚未实现。

## 继续方式

1. 查看 `data/diagnostics/live-image-smoke/baseline-candidate-v1-20260828T001904Z.png` 及同名 `.prompt.json`。
2. 由用户决定保留、定向调优或拒绝候选；不要把视觉初检替代用户批准。
3. 把角色字段审批接到 approved/locked Profile，再实现 DriftAudit、GateDecision 和 BaselineSelection。
4. 未批准前不启用批量生成；重新运行 smoke 会产生新的收费任务，必须再次明确授权。

## 证据

- `evidence/E-20260827-R6-ALIYUN-009.md`
- `evidence/E-20260828-R6-ALIYUN-009.md`
