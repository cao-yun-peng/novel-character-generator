# M3-IDENTITY-RESCUE-064

已完成。第一轮确定性修复包含 cannot-link 约束的全局 same 图、未决 singleton 事实保留、安全 bridge 和显式介绍召回；旧 M3 决策离线重放得到 bound 43/43、unresolved 3、appearance refs 129/129、cannot-link 1。

残余 cluster-level 裁决现已接线：复用旧 M3 产物构建有界多候选任务，普通 context/fact 只辅助理解，`identity_evidence_quotes` 只能来自所选候选专属 `relationship_context_quotes`，并经唯一严格/纯空白等价 Grounding 后作为 supplemental decision 重建 registry。支持 Provider 0 准备、DeepSeek 断点续跑、分离审计产物与追加历史。

斗罗离线准备生成 5 tasks、5 candidate options、10 relationship contexts，Provider 0；无关系上下文的看门青年不创建任务。128 tests 和 compileall 通过。真实 5 个 DeepSeek 补救调用未执行，留作独立付费质量评测。
