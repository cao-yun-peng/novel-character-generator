# M1-RUNTIME-FOUNDATION-047

M1 第一批运行时已经建立。`M1Provider` 只接收 system instruction、仅含 `chunk_text` 的 user payload 和严格 response schema；Provider 原始结果通过结构校验后绑定回 `M1OrchestrationEnvelope`，再由确定性 grounding 生成 Chunk 局部 occurrence、原始 hash、relation、后缀归一 trace 与 packet hash。

下一步应选择具体模型 Provider，补充超时/重试/结构化输出适配和真实模型 shadow 评测。N2 还需完成重叠 Chunk 的文档绝对 span 换算和跨 Chunk 去重接口。当前不应宣称 M1 模型效果、M2 或 N3 已完成。

