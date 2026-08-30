# M1 v2.8 条件 Gate 交接

## 决定

- 主 Prompt 回退到 v2.8。
- 005 的非唯一逐字引文和少年脸貌漏召回由用户接受为残余风险，不继续追加 Prompt 规则。
- 历史 v2.8/v2.9 Provider 报告保持原样；“条件通过”是推进授权，不是测评分数改写。

## 下游约束

- N2 必须对非唯一引文失败关闭或延后，不猜测具体 occurrence。
- 非逐字引文仍必须拒绝。
- M1 尚不具备 active Observation 或持久化权限。

## 验证

- 主 Prompt、运行时 Literal、两套 Dataset 元数据与评测类型均为 v2.8。
- 全仓库 96 项测试、Ruff、Mypy、diff check、Schema JSON 与 Project-to-Act 校验通过。
- 未调用 Provider。
