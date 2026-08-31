# 文档

当前保留新流程基线产物和相关技术调研：

- [M1/N2/M2/N3/M3 简化流程契约](33-simplified-character-evidence-pipeline-v3.md)
- [机器可读 Schema](contracts/simplified-character-evidence-v3-model-schemas.json)
- [契约审查后的技术调整](35-v3-contract-review-adjustments.md)
- [小说内容到角色形象：开源项目与 Skill 调研](34-open-source-novel-character-visualization-research.md)

当前契约包含 M1 `exact/describe/null` 类型与 `individual/collective/null` 范围、严格/纯空白等价 Grounding、N2 exact evidence 优先去重、collective 隔离、每个 exact 一次携带全部可用 individual describe 的 M2 归属任务、剩余 individual describe 的独立建人模式，以及文档级绝对 span 换算和重叠 Chunk 事实安全去重。Promotion 对人物内各事实执行部分接受：唯一事实保留，歧义事实逐条 review，不猜 occurrence。M2 模型只返回肯定外貌事实的逐字 `fact_quote` 与结构化属性；ref、span、状态、packet/fact hash 和 trace 全部由代码保留或回填，逐 quote hash 已取消。

目前没有旧版设计文档、旧提示词、旧评测说明或旧运行结果。调研文档只提供后续技术选型参考，不改变当前先实现 M1、再推进 N2/M2/N3 的路线。
