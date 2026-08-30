# PIPELINE-MENTION-CLARITY-041

M1 现在输出 `candidate_mentions[].mention_type`：明确人物名称为 `exact`，泛称和描述性短语为 `describe`，没有人物称呼时为 JSON `null`。只有 exact 生成 `local_character_ref`。

M2 组包包含 exact 自身任务以及每个 exact×describe 组合任务。N3 汇总同一 describe 片段对全部 exact 的认领结果：唯一认领才消费，多个认领保留冲突，无认领保留剩余池；有进展才自动重跑，防止死循环。

当前只完成契约和 Schema，下一步从 M1 DTO、Prompt 与最小测试开始实现。
