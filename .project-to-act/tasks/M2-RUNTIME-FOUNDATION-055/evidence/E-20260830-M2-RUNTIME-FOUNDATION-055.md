# E-20260830-M2-RUNTIME-FOUNDATION-055

## 结论

M2 双模式纵向切片已完成，任务级实现验收通过。Stage 5 保持 `in_progress`，未执行生命周期 Gate；真实模型质量与 N3 仍是后续工作。

## 已实现

- Exact attribution：每个 individual exact 一次携带当前全部 individual describe；D=0 仍执行，E=0 不创建任务，collective/null 不进入单人物输入。
- 最小模型边界：输入只有 target/describe quote 和 `chunk_text`；输出事实只有 `fact_quote/category/attribute/value`。
- 安全绑定：target evidence 优先；否则 describe 必须唯一 occurrence；严格匹配整体失败后才允许 Unicode 空白等价；非空白字符改写拒绝。
- Promotion：每个 remaining describe 独立任务；标签/事实唯一绑定；一池可建多人；跨人物标签或事实重叠时不建相关人物并进入 review；按最早事实位置稳定编号；未认领字符片段保留。
- 幂等：实现稳定 `task_cache_key`、`pool_hash` 与 `promotion_hash`，上下文或 resolver 版本变化会失效。
- Provider：DeepSeek 请求改为读取任务自带的 schema name/response schema，M1 行为保持兼容。
- Schema/版本：Schema `3.8.0-draft1`，runtime `0.1.0.dev7`，grounded promotion result v4。

## 验证

- `pytest -q`：77 passed，13 subtests passed。
- JSON Schema Draft 2020-12 meta 校验：通过。
- 四个实际运行时 packet 校验：`M2OrchestrationEnvelope`、`M2GroundedCandidateAppearanceParsingResult`、`M2RemainingDescribePromotionEnvelope`、`M2GroundedPromotedDescribeCharactersResult` 全部通过。
- Project-to-Act validate：`valid=true`，issues 为空。
- Agent lifecycle validate：`valid=true`，revision 2，Stage 5 `in_progress`。
- `git diff --check`：通过；仅输出 Git 的 LF→CRLF 工作区提示，无 whitespace error。
- Provider 调用：0；测试全部使用 fake Provider/fake transport。

## 保留边界

- M2 不修改 N2 grounded packet。
- M2 不执行跨 exact 冲突仲裁，也不从 describe 派生工作池消费字符；这些属于 N3。
- 未进行真实 DeepSeek M2 调用或人工质量 Gate，不能据此宣称模型效果完成。
