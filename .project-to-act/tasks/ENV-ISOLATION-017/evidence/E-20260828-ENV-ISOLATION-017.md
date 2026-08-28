# E-20260828-ENV-ISOLATION-017

- 时间：2026-08-28（Asia/Shanghai）。
- 确认来源：用户明确要求只保留当前项目，并删除旧项目。
- 代码基线：Git HEAD `1b964f6dcc95815694c4f878201d25c04bf5d42b`；工作树包含本任务的包目录迁移和账本更新。
- 变更：把源码从 `src/application|domain|infrastructure` 归位到 `src/novel_character_generator`；本机 editable `.pth` 与 `direct_url.json` 改指当前工作区。
- 删除：永久删除旧项目根目录 `E:/project/agent/novel-character-generator`；删除后 `Test-Path` 为 `False`。该目录不可由本任务恢复。
- 独立导入：`novel_character_generator` 与 M1 Provider 的 `__file__` 均位于 `E:/project/agent/novel-cahracter-generator/src/novel_character_generator`。
- 验证：`pytest -p no:cacheprovider`，退出 0，59 passed；`ruff check --no-cache src tests scripts`，退出 0；`mypy --no-incremental`，退出 0，29 source files；`git diff --check`，退出 0。
- 哈希：`pyproject.toml` SHA-256 `BEC99BCD97444807371DC844B7CD53318ECD71A69707FF7A1E78D2B659E447EB`；`uv.lock` SHA-256 `CC934147FA27F947C5DF9A58580D4D36E587B95DE525899854750F68B981CF1C`；M1 service SHA-256 `3E78A06B75189EC0363C3771B6B16515D03C19D107E707D0931C96748D0C01A9`；editable `.pth` SHA-256 `BA9306909276F9CE99A305C9B1FF633900E5A19290ED482BF6DAE1B07D3D0F49`。
- 有效期：源码布局、`pyproject.toml`、虚拟环境或依赖再次变化前有效。
