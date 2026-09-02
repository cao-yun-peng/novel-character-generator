# APPEARANCE-SCOPE-SCHEMA-070 验收证据

- Evidence ID：`E-20260902-APPEARANCE-SCOPE-SCHEMA-070`
- 日期：2026-09-02
- 基线 HEAD：`85985e3380a755a1cd2e5d99e9cc401b0c22d335`（任务改动尚未提交）
- 运行时：`0.1.0.dev19`
- Schema：`3.19.0-draft1`
- 生命周期：Stage 5 `in_progress`，revision 2，风险 L1
- Provider 调用：0

## 实际结果

- 源文件按原文标题解析为 19 章；相邻重复的同章标题被折叠。
- 109/109 canonical facts 各有且仅有一个章节和原文顺序 assignment。
- life/form/scene 均保守初始化为 `unknown`，不使用词表推断状态。
- persistence：stable 2、persistent_until_changed 13、scene 18、momentary 12、unknown 64。
- 产物：`runs/douluo-20ch-e2e-dev13-20260831/appearance-scopes-dev19/document-character-appearance-scopes.json`
- 产物 SHA-256：`1BDA7083D66EC0CC22379C23DF0C5A81F78EF8D5E0673052D9000FF37E5C8E10`
- 实现 SHA-256：`D19C37F65F333BC562F7125D50ADCEDBD7484EC26434EE83E004A2B56C2ED75A`
- 测试 SHA-256：`AD695737CB0F16C3B95A2A1598A52A6EF619AAD367D68083DAE33D4D7AA48F92`
- Schema 文件 SHA-256：`53BBCD29D5F8F7EF0BF7583BB535F24D355365CDDA78028092B083F7B5B7B080`

## 验证

- 全量测试：150 passed。
- `compileall`：通过。
- Draft 2020-12 meta-schema 与真实 `DocumentCharacterAppearanceScopes` 实例：通过。
- 相同输入连续构建输出 SHA-256 稳定。
- `git diff --check`：退出码 0；仅 Git 报告既有 LF/CRLF 转换提示。
- Project-to-Act validate：`valid: true`，issues 为空。
- Agent lifecycle validate：`valid: true`，revision 2，Stage 5。

## 能力边界

本 Gate 只证明确定性章节位置、fact 顺序、保守 persistence 与 unknown scope 基线正确。它不证明 life/form/scene transition 已被识别，也不替代 071 的模型质量评测或 Stage 6 人工 Gate。
