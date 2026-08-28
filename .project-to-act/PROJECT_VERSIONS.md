# 项目版本

## 当前版本

- 项目版本：`0.1.0`，未发布
- GitHub 开发分支：`origin/v2-semantic-pipeline`（独立历史，不与旧 `main` 合并）
- 设计基线：`semantic-pipeline-v2-design-v1.2`
- M1：`local-observation-model-wire-v1`、Prompt `v1.6`
- N2：`local-grounding-input-v1`、`grounded-local-packet-v1`
- M2：`field-disambiguation-model-wire-v1`、`visual-field-catalog-v1`

这里的 `v1` 是各 V2 子契约的独立版本号，不代表已删除的旧架构。

## 下一版本计划

审核并实测 M2，然后实现 M3 身份组件解析。任何 active 写入或持久化设计都必须建立独立任务并重新验收。

## 版本历史

- 2026-08-28：提交 `ed8396d` 已推送到 `origin/v2-semantic-pipeline`；旧 `main` 保持不变。
- 2026-08-28：不变更 `0.1.0` 语义版本；修正源码包布局和本机 editable 安装来源，当前仓库可独立运行。
- 2026-08-28：完成 M1、N2、M2 离线工程切片。
- 2026-08-28：清除无关实现、测试、文档、运行数据和历史账本，仓库收敛为 V2 单一路线。
