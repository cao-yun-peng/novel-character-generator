# M1 Prompt v2.9 双集 Provider 检查交接

## 已完成

- 用户授权后完成短集 16 条与真实集 10 条 Provider 检查。
- 短集 16/0/0；真实集最终 1/6/3，完整 outputs、reports、run manifests 与哈希已保存。
- 运行器现在会将 Provider extraction/transport 异常记录为 `provider_failed`，不再因单条 `provider_finish_length` 中止整批。

## 结论

- v2.9 短集无回归。
- 005 的重复裸描述唯一定位问题仍复现，且少年脸貌仍漏；通用 Prompt 规则尚未稳定解决该类问题。
- 006、009 按用户审查不作为缺陷；007 的失败属于 Provider 完成长度异常。
- M1 evidence Gate 仍未通过。

## 下一步

- 若继续优化，保持“类别级规则”约束，避免写入 005 专用词语；可研究更短的唯一性自检指令或拆分生成/校验流程。
- 如需把 007 的 Provider 完成长度纳入稳定性改进，应单独建立运行器/模型配置任务，不与 Prompt 质量混合归因。
