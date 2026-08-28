# PIPELINE-V2-DESIGN-012 Handoff

- 状态：`semantic-pipeline-v2-design-v1.1` 修订与静态验证完成；Stage 4 架构 Gate 条件通过，Stage 5 ready，未进入生产实现。
- 核心决定：开放字段语义、人物身份、时间作用域和持续性不由确定性规则主导，分别交给 M2、M3、M4；M1 做局部命题发现，M5 做 downgrade-only 联合复核。
- 代码权力：只负责 quote/Schema/ID/硬冲突、状态机、Promotion 和持久化；模型永远不能直接激活 Observation。
- 第一目标：端到端人物档案质量和人物/阶段/形态污染控制；成本与延迟先观测并设置 Run 硬上限，质量通过后再优化。
- 修订重点：M1 全有效 Chunk、M2 semantic unit/referent、M3 component completeness/supersede、M4 scene/event boundary/end condition、M5 character+scope review group；5 输入+5 输出 Schema 含条件约束。
- 产物：`docs/27-semantic-pipeline-v2-contract.md`、五份系统提示词、一个机器可读输入/输出 Schema 集。
- 下一步：新建 P0 离线回放任务；P0 不调用 Provider、不修改 active 业务真值，并冻结 promotion coverage 与人工 review capacity 阈值。
