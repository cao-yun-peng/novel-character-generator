# 项目进度

## 当前任务

| 任务 | 状态 | 结果 |
|---|---|---|
| PIPELINE-V3-SIMPLIFIED-039 | completed | 新流程契约和机器 Schema 已建立 |
| PROJECT-V3-CLEAN-START-040 | completed | 旧工程资产已退出当前工作目录，新项目只保留契约和最小治理文件 |
| PIPELINE-MENTION-CLARITY-041 | completed | exact/describe/null、exact×describe M2 和 N3 describe 消费循环已写入契约与 Schema |
| MENTION-SUFFIX-RULE-042 | completed | 用户确认使用 *女子 等泛称后缀规则归一 describe |

## 阻塞项

- 尚未选择和建立新的运行时工程骨架。
- M1 提示词、DTO、Provider 和测试均未实现。
- 人物记忆绑定策略暂缓。

## 下一步

1. 按 Schema 3.1.0-draft1 实现 M1 mention_type、candidate_mentions 和服务端 local_mention_id。
2. 编写 M1 提示词。
3. 建立只覆盖 M1 契约的最小测试。
4. M1 通过后再实现 N2。

## 进度历史

- 2026-08-30：确认 `红衣女子` 可通过 `*女子` 后缀规则归一为 describe；实现约定使用 `endswith`，明确名称优先拆成最小 exact 提及。
- 2026-08-30：用户新增 exact/describe/null 规则；所有 describe 与所有 exact 组合进入 M2，N3 唯一认领后消费 describe 片段，剩余片段继续细分。
- 2026-08-30：用户确认当前分支不保留旧代码和旧文档，项目按新流程完全重新开始。
