# M1 v2.8 回退与条件 Gate 证据

- 日期：2026-08-29（Asia/Shanghai）
- 基线 Git：`01a4930`（工作区含用户既有未提交变更）
- 用户决定：主 Prompt 回退 v2.8；005 作为残余风险，不再继续 Prompt 修复，继续 N2。
- Gate：`conditional`。历史 v2.8/v2.9 报告不改写；非逐字引文仍失败关闭；不授权 active Observation。

## 变更与哈希

- Prompt v2.8 SHA-256：`a52b719959f51e6e15765e1f859fcc06bc120f8166432e25bc08a3d1a046f885`
- 短集 v2.3-draft SHA-256：`e7281881a0e9c134996f787a2e2a7e99a6c70b4402066d536e8899b78e8d3430`
- 真实集 v2.5-draft SHA-256：`7d1226b1fb8b113a88beef5409c0a69a728aa8781983167585d629d03da53013`
- Prompt 运行时、评测类型、Dataset 元数据和生成脚本均指向 `visual-evidence-discovery-prompt-v2.8`。
- v2.9 的二次唯一性闭环与同载体独立 cue 新增规则已从主 Prompt 移除；历史任务与诊断工件保留。

## 验证

- `.venv\\Scripts\\python.exe -m pytest`：退出 0，`96 passed`。
- `.venv\\Scripts\\ruff.exe check .`：退出 0。
- `.venv\\Scripts\\python.exe -m mypy`：退出 0，38 个 source files 无问题。
- `git diff --check`：退出 0（仅 Git CRLF 提示）。
- Project-to-Act `--validate`：退出 0。
- Agent lifecycle `validate`：退出 1；为开工前已存在的 revision 1 结构错误（阶段 0–4 状态、宽泛产物路径、revision/history 不一致）。本任务未手改生命周期账本，也不声称完成阶段转换。
- Provider 调用：未运行。
