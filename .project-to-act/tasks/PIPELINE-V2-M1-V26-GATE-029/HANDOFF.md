# M1 Prompt v2.6 双集诊断交接

## 已完成

- Source Match Policy v2 与 Rubric v2.5 已实现并通过工程验证。
- Prompt v2.6 已对 approved 短集和 v2.4-draft 真实集完成共 26 次 Provider 调用。
- 短集最终重评分 15/16；真实集原始评分 2 pass / 3 review / 5 fail。
- 两次运行的 outputs、report、run manifest、hash、usage 和逐 case 状态均已保存。

## 待人工审核

- 短集 003：是否接受“一个红衣少女”作为 owner alias 与证据跨度。
- 真实集 003：`他` 的候选局部 owner；004：`那是一名中年男子`；008：`小女孩儿...` 和 `那女孩儿`；009：`小女孩仙清儿`。
- 005 的青衫老者引文仍不唯一，少年脸貌漏召回；008 的虎牙仍漏召回。

## Gate

本任务完成工程与诊断，但 M1 evidence Gate 未通过；先审核测量缺口，再使用已保存 outputs 离线重评分，不应立即重复调用 Provider。
