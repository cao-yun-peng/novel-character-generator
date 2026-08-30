# E-20260830-PIPELINE-MENTION-CLARITY-041

- 时间：2026-08-30，Asia/Shanghai。
- 用户决策：M1 增加 exact/describe/null；所有 describe 与所有 exact 组合进入 M2；N3 消费已归属 describe 证据并让剩余部分再次解析。
- 安全细化：N2 approved evidence 保持不可变，N3 只消费工作池中的最小原文 span；多人物认领冲突不删除；相同 pool hash 停止自动循环。
- Schema：`3.1.0-draft1`。
- Provider 调用：0。
- 运行时修改：0。
- 契约 SHA-256：`6AB5A6F95AB220A37E3F85270463F55EC054944BA091516AC585D3D29602EBEA`。
- Schema SHA-256：`94F34C14FAC62CF777DEAAE976E18345DF220C78BF0010D95DDE43406A53122B`。
- Schema 验证：Draft 2020-12 静态校验通过，版本 `3.1.0-draft1`，15 个定义。
- 行为验证：exact/describe/null 合法样例通过；null 携带 mention、describe 缺少 mention、uncertain 携带 claimed evidence/facts、空 describe ref 携带 assessments 均被拒绝；N2 grounded mention、exact×describe M2 输入输出和 N3 唯一消费样例通过。
- 项目治理：项目台账返回 `valid: true`；工作区和 staged diff check 均通过。
- 结论：契约与机器 Schema Gate 通过；运行时、提示词和模型质量 Gate 未开始。
- 有效期：直到 mention 分类或 describe 归属循环契约变化。
