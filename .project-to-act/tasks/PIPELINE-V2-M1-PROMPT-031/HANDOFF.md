# M1 Prompt v2.7 交接

## 已完成

- 根据真实集 005/008 的剩余失败完成根因归类。
- Prompt v2.7 已实现语义边界、引文自身唯一定位和全 Chunk 逐子句覆盖复扫。
- 版本契约、两套 draft Dataset 的被测 Prompt 元数据和自动测试已同步。
- Dataset 金标、Rubric 和 Source Match Policy 未改变。

## 未验证

- 本任务没有调用 Provider，因此不能宣称 v2.7 已修复 005/008，也没有 v2.7 质量分数。
- v2.6 保存 outputs 不能用于评价 v2.7。

## 下一步

- 用户复审两套 draft Dataset 后，明确授权 v2.7 跑短集与真实集。
- 新运行需保存 Prompt/Dataset/Rubric hash、模型元数据和逐 case deterministic validation。
- 只有短集无回归且真实 005/008 的目标缺口关闭，才重新判断 M1 evidence Gate。
