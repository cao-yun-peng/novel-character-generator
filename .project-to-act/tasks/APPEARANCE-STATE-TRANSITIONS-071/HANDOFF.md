# APPEARANCE-STATE-TRANSITIONS-071

任务已启动，状态为 `in_progress`。Stage 5 保持 `in_progress`，lifecycle revision 仍为 2。

本任务直接复用原 M1 Manifest 的 17 个重叠 Chunk，以 `chunk_id` 连接该 Chunk 已识别并绑定到最终人物簇的 local/promoted nodes；模型只读取人物 `name + aliases` 和原 Chunk 正文。`chunk_id/hash/span` 留在代码信封，用于严格 evidence Grounding、跨 Chunk 去重、恢复和 fact scope 回填。072 语义关系与冲突分类不在本任务范围。

斗罗离线准备结果为 17/17 原 Chunk，所有 id/hash/span 与 M1 Manifest 完全一致，17/17 均有已绑定人物；单 Chunk 最终人物表为 1～3 人。模型 payload 递归字段只有 `characters/name/aliases/text`。156 项测试、compileall、Schema/实例、diff check 和两套治理校验通过。原先生成的 19 窗口失败产物已删除并由 `transition-chunks.json` 替代；重新设计后的真实模型运行尚未执行，因此任务继续保持 `in_progress`。

用户明确授权向 DeepSeek 发送 17 个 Chunk 后完成真实运行。首次 15/17 成功，Chunk 2/8 因 4096 输出预算截断；8192 预算断点重试只新增 2 次调用后 17/17 完成。模型返回 8 events，代码接受 7 个逐字 Grounded transitions、拒绝 1 个拼接非连续段落的独狼附体进入事件；7/7 evidence 绝对 span 回放，状态实例 Schema 通过。

本轮不通过质量 Gate：虽然“素云涛全身青光收敛，收回了自己的武魂附体”被准确发现并 Grounding，但 scene/form 状态传播尚未正确关闭；“全身赤裸”错误延续到后续章节，“蓝银草收回体内”被误当成人物 form 并长期传播，转世 after 语义也缺少当前 evidence 的充分支持。071 继续保持 `in_progress`，不得以 `complete: true` 的批处理状态替代语义质量验收。
