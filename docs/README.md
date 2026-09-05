# 文档

当前保留新流程基线产物和相关技术调研：

- [M1/N2/M2/N3/M3 简化流程契约](33-simplified-character-evidence-pipeline-v3.md)
- [机器可读 Schema](contracts/simplified-character-evidence-v3-model-schemas.json)
- [契约审查后的技术调整](35-v3-contract-review-adjustments.md)
- [外貌状态层与 Profile Compiler 开发计划](36-appearance-profile-compiler-development-plan.md)
- [源码问题修复清单与 Web 接口规划](37-web-ready-repair-checklist.md)
- [075 人工质量评测协议候选](38-quality-annotation-protocol.md)
- [dev28 缓存续跑兼容说明](39-cache-resume-compatibility.md)
- [dev29 CharacterSnapshot 与有效期契约](40-character-snapshot-and-applicability.md)
- [dev30 自动事件与冲突闭环](41-automatic-events-and-conflicts.md)
- [小说内容到角色形象：开源项目与 Skill 调研](34-open-source-novel-character-visualization-research.md)

当前契约包含 M1 `exact/describe/null` 类型与 `individual/collective/null` 范围、严格/纯空白等价 Grounding、N2 exact evidence 优先去重、collective 隔离、每个 exact 一次携带全部可用 individual describe 的 M2 归属任务、剩余 individual describe 的独立建人模式，以及文档级绝对 span 换算和重叠 Chunk 事实安全去重。Promotion 对人物内各事实执行部分接受：唯一事实保留，歧义事实逐条 review，不猜 occurrence。M2 模型只返回肯定外貌事实的逐字 `fact_quote` 与结构化属性；ref、span、状态、packet/fact hash 和 trace 全部由代码保留或回填，逐 quote hash 已取消。

当前运行时已推进到身份、外貌状态与 render-ready profile。37 记录源码审查后的修复、CharacterSnapshot、场景/换装持续、高召回候选和 Web 接口计划；已实施 077/078 正确性与缓存及 079 有效期/Snapshot 基础切片，其余按项目进度逐步实施。调研文档只提供技术选型参考，不作为功能已完成的依据。

- [R03/R02 真实 API 测试与 Snapshot 验证](42-semantics-live-validation.md)
