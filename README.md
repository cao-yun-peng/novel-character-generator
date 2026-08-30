# Novel Character Generator

这是一个从零重新开始的中文小说人物外貌证据项目。

当前分支只保留已经确认的新流程契约，不包含旧版源码、测试、评测数据、提示词、依赖配置或运行结果。

## 当前流程

1. M1：从 Chunk 中识别人物提及，标记为 `exact`、`describe` 或 JSON `null`，并把相关原文证据放进该提及块。
2. N2：验证人物称呼和证据是否确实存在于 Chunk，形成 `approved_evidence`。
3. M2：每个 `describe` 分别与每个 `exact` 人物组合解析；`describe` 本身不是独立人物。
4. N3：验证证据并汇总归属。唯一归属的 describe 原文片段从待处理池中消费，剩余片段重新进入 M2；冲突或无进展进入复核。

“张三”“林黛玉”等明确名称属于 `exact`；“老者”“女孩”“红衣女子”“月袍老人”等泛称或描述都属于 `describe`。同一句证据允许暂时出现在多个提及块中。人物记忆目前只预留 `local_character_ref -> character_id` 接口。

`describe` 使用版本化泛称后缀表复核，例如 `红衣女子.endsWith("女子")` 后归一为 `describe`。明确名字优先抽取为最小 exact 提及。

## 当前产物

- [流程契约](docs/33-simplified-character-evidence-pipeline-v3.md)
- [机器 Schema](docs/contracts/simplified-character-evidence-v3-model-schemas.json)
- [文档入口](docs/README.md)

## 当前状态

只有契约，没有运行时代码。下一步从 M1 的数据结构、提示词和最小测试开始实现。
