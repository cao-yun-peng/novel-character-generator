# MODEL-BOUNDARY-BATCHED-M2-045

M1 和 M2 统一拆分为代码编排信封、实际模型输入、实际模型输出和代码回填验证。M1 模型只读取 `chunk_text`；M2 每个 exact 一次携带本轮全部 describe 和 `chunk_text`。系统身份、原文绝对位置、hash、cache key、版本及 trace 都留在代码层。

当前仅修改契约与 Schema。下一步实现时，Provider 只能接收 envelope 中的 `model_input`，模型输出必须先完成任务内 ref、逐字 quote 和局部 span 验证，再允许回填进入 N2/N3。
