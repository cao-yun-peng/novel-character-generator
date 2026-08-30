# M1 Prompt v2.8 交接

## 已完成

- Prompt v2.8 已固化跨 owner 拆分、同 owner 连续外观事件合并以及覆盖复扫去重规则。
- 运行时版本、评测模型、构建脚本、两套 Dataset Prompt 元数据和测试已同步。
- Dataset 金标/版本、Rubric v2.5 与 Source Match Policy v2 均未改变。
- 真实集可从原始章节稳定重建为 10 条，全量工程验证通过。

## 尚未验证

- 本任务没有调用 Provider，不能宣称 005 或 009 已修复。
- 最近真实质量基线仍是 Prompt v2.7：短集 16/0/0、真实集 2/6/2。
- v2.7 outputs 不能离线重评分为 v2.8 结果，因为 Prompt 行为已经变化。

## 下一步

- 用户复审当前两套 draft Dataset。
- 用户再次明确授权数据外发后，固定 Dataset/Rubric/Source Match Policy，用 v2.8 跑短集 16 条和真实集 10 条。
- 重点比较 005、008、009，并检查整体 recall、precision、owner binding 与 deterministic validation。
