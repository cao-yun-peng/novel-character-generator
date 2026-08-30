# E-20260830-MENTION-SUFFIX-RULE-042

- 时间：2026-08-30，Asia/Shanghai。
- 用户确认：红衣女子可以使用 `*女子` 匹配为 describe。
- 规则版本：`describe-suffix-v1`。
- 实现语义：后缀匹配使用 `endswith`；不是非法正则 `*女子`。
- Provider 调用：0。
- 运行时修改：0。
- 契约 SHA-256：`92FC3AA4B77F02B9671D05D36A9B3D146551945B11DD964D478EE77137EC2DB9`。
- 行为样例：15 个首版后缀参与 `endswith` 校验；红衣女子、白衣女子、月袍老人、青衫老者均得到 describe；林黛玉得到 exact；空提及得到 null。
- 验证：Schema `3.1.0-draft1` 静态校验通过；项目台账返回 `valid: true`；工作区和 staged diff check 通过。
- 结论：后缀规则设计 Gate 通过；运行时与提示词尚未实现。
- 有效期：直到 describe 后缀表或匹配优先级变化。
