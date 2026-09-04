# APPEARANCE-STATE-SEGMENTS-0715

任务已完成。Stage 5 保持 `in_progress`，lifecycle revision 仍为 2。

本切片只实现确定性派生的 `StateSegment`：输入为 071 已 Grounding 的 transitions、070 assignments、canonical fact 位置与 persistence；输出继续属于同一个 appearance-state artifact。不会新增模型调用、平行状态存储或 072 语义关系判断。

本任务开始时工作区已有用户修改 `tests/test_appearance_transition.py`。实现必须避开并保留该修改；新增验证写入独立测试文件。

运行时升级为 `0.1.0.dev23`，Schema 升级为 `3.23.0-draft1`，appearance state artifact 升级为 v4。Grounded Transition 现在拥有内容派生的稳定 `transition_id`；7 个注册人物均形成覆盖全文的连续区间，事实只以 `observed_fact_ids` 引用，不复制内容或 provenance。

斗罗保存输出离线重放 17/17，新增 Provider 调用 0；6 个 transitions 生成 6 个唯一 ID、14 个 StateSegments，109/109 canonical facts 唯一 observation 绑定。重复重放的 state artifact SHA-256 均为 `91AF34306343800EC250D8CC6E9DED6E1E1E289E646E2F3CD5D8D8ADB5C6ADA0`。165 tests、13 subtests、compileall、Draft 2020-12 实例、diff 与两套治理校验通过。
