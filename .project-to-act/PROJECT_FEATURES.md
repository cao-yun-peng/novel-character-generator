# 项目功能

## 状态定义

- `completed`：契约或工程已完成并通过对应验证
- `planned`：尚未实现

## 功能清单

| ID | 功能 | 状态 | 说明 |
|---|---|---|---|
| F-NEW-DESIGN-001 | 简化人物证据契约 | completed | 包含 exact/describe/null、exact×describe 和 N3 describe 消费循环 |
| F-NEW-M1-002 | 人物提及与证据归拢 | planned | 输出 candidate_mentions/mention_type，并用 describe-suffix-v1 复核；尚无代码 |
| F-NEW-N2-003 | 原文存在性验证 | planned | 验证 mention/evidence，形成 approved evidence |
| F-NEW-M2-004 | exact×describe 外貌拆解 | planned | 每个 describe 分别与每个 exact 组合；尚无代码 |
| F-NEW-N3-005 | 证据三态与 describe 归属 | planned | 唯一消费、冲突保留、剩余池重跑；尚无代码 |
| F-NEW-IDENTITY-006 | 人物记忆绑定 | planned | 只保留接口占位 |

## 功能变更历史

- 2026-08-30：采用泛称后缀匹配；例如红衣女子命中 `*女子` 后归一为 describe。N2 归一不删除 evidence，只记录 trace。
- 2026-08-30：describe 明确为非人物证据池；只有 exact 生成 local_character_ref。N3 以原文片段为粒度消费，N2 原始证据保持不可变。
- 2026-08-30：旧工程功能全部退出当前分支功能清单，新项目从 M1 开始实现。
