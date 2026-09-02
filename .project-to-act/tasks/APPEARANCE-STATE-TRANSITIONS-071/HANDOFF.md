# APPEARANCE-STATE-TRANSITIONS-071

任务已完成，Stage 5 继续保持 `in_progress`，lifecycle revision 仍为 2。

本任务直接复用原 M1 Manifest 的 17 个重叠 Chunk，以 `chunk_id` 连接该 Chunk 已识别并绑定到最终人物簇的 local/promoted nodes；模型只读取人物 `name + aliases` 和原 Chunk 正文。`chunk_id/hash/span` 留在代码信封，用于严格 evidence Grounding、跨 Chunk 去重、恢复和 fact scope 回填。072 语义关系与冲突分类不在本任务范围。

斗罗离线准备结果为 17/17 原 Chunk，所有 id/hash/span 与 M1 Manifest 完全一致，17/17 均有已绑定人物；单 Chunk 最终人物表为 1～3 人。模型 payload 递归字段只有 `characters/name/aliases/text`。

最终 dev22 真实运行 17/17 一次完成，模型返回 10 events；代码接受 6 个 Grounded transitions，另外 4 个 before/after 改写因无法回填到同一 evidence 被隔离。接受项包含唐三 life、素云涛独狼附体进入/退出、老杰克换新衣 scene 及两条 appearance transition；6/6 evidence 绝对 span 回放。

v3 Grounding/物化规则已经关闭上一轮四个已知失败：life 会重置 form/scene；scene 在段落行或章节边界关闭；蓝银草等不改变身体的武魂/外物状态不进入 form；evidence 必须单段连续，before/after 必须在同一 evidence 内逐字、有序映射，允许只省略标点时回填原文连续片段。保存的模型输出每次恢复都会重新 Grounding，本轮重放 17/17、Provider 新调用 0。最终 28 个 facts 带 life、7 个带 form、1 个带 scene；160 tests、13 subtests、compileall、Draft 2020-12 Schema/两实例和 diff check 通过。
