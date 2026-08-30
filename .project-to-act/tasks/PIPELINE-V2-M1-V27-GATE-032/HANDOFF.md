# M1 Prompt v2.7 双集回归交接

## 已完成

- 在用户明确数据外发授权后完成短集 16 条与真实集 10 条 Provider 调用。
- 26/26 输出均通过 deterministic validation；outputs、report、run manifest、hash、usage 和逐 case 状态已保存。
- 短集保持 16/0/0；真实集仍为 2/6/2。

## 关键变化

- 008 的虎牙召回修复，case 从 fail 改为 review。
- 005 唯一定位和月白衣袍完整跨度修复，但跨 owner 合并候选导致少年脸貌仍未正确绑定，且青衫管家服饰仍漏。
- 009 出现 transformation 原子化回归，从 review 变为 fail；视觉内容大多存在，但与当前复合跨度 Rubric 不匹配且额外候选过多。

## 下一决策

- 先人工决定 009 应由 Prompt 强制同 owner 连续 transformation 合并，还是由 Rubric 支持多个小候选聚合覆盖复合 gold。
- 若继续改 Prompt，建议同时明确：跨 owner 的视觉短语必须拆分并分别绑定；同 owner 的连续 transformation 不因覆盖复扫而原子化。
- 下一实验只能改变 Prompt 或 Rubric 其中之一，并同时回归短集、005、008、009。
