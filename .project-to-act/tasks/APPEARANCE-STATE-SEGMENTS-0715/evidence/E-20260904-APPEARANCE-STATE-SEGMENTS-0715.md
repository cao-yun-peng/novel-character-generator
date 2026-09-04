# APPEARANCE-STATE-SEGMENTS-0715 验收证据

## 架构边界

- M1/N2/M2/N3 的职责与接口未改变；本任务不把其模型质量标记为已冻结或已通过人工 Gate。
- `StateSegment` 集成在 `document-character-appearance-states-v4` 中，是由 Grounded Transition、fact assignment、persistence 和文档边界确定性重建的派生结果，不是新的状态真相源。
- 每个 canonical fact 只保存到一个 `observed_fact_ids`；跨区间有效性与 `active_fact_ids` 明确推迟到 072/074。
- Registry 继续拥有身份与 `appearance_fact_refs` 归属边；ProfileView/render profile 继续是可重建视图。

## 实现证据

- 新增 `appearance_state_segments.py`：验证并生成稳定 transition ID，物化 document/transition/scene-expiry boundary，按 life → form → scene → appearance 回放状态。
- life transition 清空旧 form/scene；scene expiry 只关闭仍由对应 transition 建立的 scene。
- 每个人物的 segment 连续覆盖全文；零事实人物也输出一个 unknown segment。
- 新增独立测试文件，覆盖确定性 ID、连续区间、同位置事件、observation 唯一性、scene expiry、life reset、零事实人物和篡改失败关闭；没有改写用户已有的 transition 测试修改。

## 真实离线重放

- 来源：斗罗 dev22 保存的 17 个 Chunk 模型输出。
- 结果：17/17 resumed，`new_provider_calls=0`，6 grounded transitions，4 review。
- v4 产物：7 characters、14 StateSegments、6/6 唯一 transition IDs、109/109 canonical facts 唯一 observation 绑定。
- 原有 fact state 统计保持 life 28、form 7、scene 1。
- 重复重放 state artifact SHA-256 均为 `91AF34306343800EC250D8CC6E9DED6E1E1E289E646E2F3CD5D8D8ADB5C6ADA0`。

## 验证

- `165 passed, 13 subtests passed`。
- `python -m compileall -q src tests` 退出码 0。
- Draft 2020-12 `DocumentCharacterAppearanceStates` 真实实例校验通过。
- `git diff --check`、Project-to-Act `--validate` 与 Agent lifecycle `validate` 退出码 0。

本任务只验收确定性状态区间与 observation binding，不包含 072 语义关系、active applicability、074 Profile Compiler 或 075 人工模型质量 Gate。
