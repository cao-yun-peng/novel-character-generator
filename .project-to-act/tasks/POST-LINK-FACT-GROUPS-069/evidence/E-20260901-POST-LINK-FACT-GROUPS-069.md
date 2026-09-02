# POST-LINK-FACT-GROUPS-069 验收证据

- Evidence ID：`E-20260901-POST-LINK-FACT-GROUPS-069`
- 日期：2026-09-01
- 基线 HEAD：`85985e3380a755a1cd2e5d99e9cc401b0c22d335`（本任务改动尚未提交，另记录文件哈希）
- 运行时：`0.1.0.dev18`
- Schema：`3.18.0-draft1`
- 生命周期：Stage 5 `in_progress`，revision 2，风险 L1
- Provider 调用：0
- 有效期：直到实现、Schema、输入 registry/profile 或斗罗源文档任一内容变化

## 工件与哈希

- `src/novel_character_generator/fact_groups.py`：`BDFB13E99E53487D1992552E6A1E986FA36C2AE0450BD6F8BF48B06BC56F3D54`
- `docs/contracts/simplified-character-evidence-v3-model-schemas.json`：`CE04812356A36D8FC8E673B3320F1A44DBA1894173FF4D94B2E0C48E09D8A5BA`
- `tests/test_fact_groups.py`：`0AC547DAD219295AA9744EDD8B2609D6E6CC848EF48F1776950BA1109AA4A6CB`
- 输入 registry：`9FF571B51398B734427303BBAAE2803409F6280EA8A2107A15759236543C1EE9`
- 输入 profiles：`9EB5D36A868DEE42F3E414320743CF62ABB664B98C64ACCC5A5ABF037FAEAADE`
- 输出 fact groups：`C5C42C1BDAB21FD5B163E9418B927748EE90815B320158AF04683DC423E3507F`

## 真实纵向切片

使用 `build-document-character-fact-groups` 对斗罗 dev17 registry/profile 离线执行：

- 7 characters；129 assigned raw facts；0 unassigned raw facts；
- 109 canonical fact groups；10 multi-member groups；折叠 20 个 raw duplicate members；
- 老杰克 26 raw facts → 14 groups，5 个 multi-member groups，折叠 12；
- 素云涛 29 raw facts → 21 groups，5 个 multi-member groups，折叠 8；
- 唐三 39→39、唐昊 28→28、大师 5→5、男孩儿 1→1、看门青年 1→1；
- 129 个 source fact bindings 唯一覆盖 129 个 raw fact hashes；
- 130 个 source occurrence bindings 全部按 `source_fact_hash + source_occurrence_index` 精确映射回 raw profile occurrence；
- 109 个 `fact_quote/document_fact_span` 全部逐字回放；109 个 `canonical_fact_id` 全部唯一；
- 同 span 不同 attribute 保持不同 groups；不做语义或状态归一。

执行前后 registry/profile SHA-256 均未变化。相同命令重复执行后输出 SHA-256 仍为 `C5C42C...3507F`。

## 自动验证

```powershell
$env:PYTHONPATH='src'
python -m unittest discover -s tests
python -m compileall -q src tests
```

结果：146 tests 全部通过；compileall 退出码 0。

Draft 2020-12 meta-schema 与 `DocumentCharacterFactGroups` 真实实例校验通过。`git diff --check`、Project-to-Act `--validate` 和 Agent lifecycle `validate` 均要求退出码 0；最终校验结果记录在项目验收条目中。

## 边界

本任务只验收 post-link 结构分组，不把 `高大/高大魁梧`、同义属性、状态变化或冲突做语义合并。`scope_assignment_status` 保持 `unassigned`；life/form/scene scope、persistence 和 transition 由 070/071 实现。069 的成功不替代 M1/M2/promotion 人工质量 Gate，Stage 6 不提前进入。
