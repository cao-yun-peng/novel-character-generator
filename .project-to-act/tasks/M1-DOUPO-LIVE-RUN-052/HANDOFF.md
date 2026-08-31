# M1-DOUPO-LIVE-RUN-052

真实运行任务已完成。输入固定为 `tests/小说/斗破苍穹前5章.txt`，最终输出位于 `runs/doupo-first5-m1-scope-v4`，采用 2500/250 分块，7/7 Chunk 完成。

首次调用因临时 `.env` 注入保留了 Key 外层引号而产生 7 次 401，脱敏失败产物保存在 `runs/doupo-first5-m1-scope-v4-auth-failed`。随后发现 CLI universal-newline 会把 CRLF 改为 LF，先修复为原始 UTF-8/换行读取并将运行时升至 `0.1.0.dev5`。4096 输出预算下 5 个 Chunk 被 `max_output_tokens` 截断；使用 8192 断点续跑，仅重试失败块，最终完成。

最终产物包含 37 个 candidate/grounded mentions、94 条 evidence bindings、0 rejected；36 个 individual、1 个 collective。94 条 evidence 全部 `match_mode=exact`，span 回放失败 0，人物 occurrence/anchor 禁止字段 0。API Key、Prompt 与 reasoning 未进入产物或台账。本任务不推进生命周期 Gate，模型质量仍需人工评测。
