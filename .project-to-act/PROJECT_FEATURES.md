# 项目功能

## 状态定义

- `completed`：工程与规定验证完成
- `in_progress`：正在开发或等待当前 Gate
- `planned`：仅有设计契约
- `blocked`：前置质量或用户审核未通过

## 功能清单

| ID | 功能 | 状态 | 说明 |
|---|---|---|---|
| F-V2-DESIGN-001 | N0–N11、M1–M5 总契约 | completed | Schema 和失败路由已定义 |
| F-V2-M1-002 | M1 局部观察发现 | blocked | 工程完成；真实质量 5/6 |
| F-V2-N2-003 | N2 本地证据定位 | completed | 确定性 grounding/context 完成 |
| F-V2-M2-004 | M2 字段消歧 | blocked | 工程完成；draft 数据集待审核 |
| F-V2-M3-005 | M3 身份组件解析 | planned | 尚未实现 |
| F-V2-M4-006 | M4 时间与持续性解析 | planned | 尚未实现 |
| F-V2-M5-007 | M5 联合复核 | planned | 尚未实现 |
| F-CLEANUP-V2-008 | V2 仓库精简 | completed | 无关代码、文档、测试和缓存已删除 |

## 功能变更历史

- 2026-08-28：移除与当前 V2 无关的运行能力，只保留 M1/N2/M2 和后续节点设计。
