# M2-DOUPO-LIVE-RUN-056

任务已完成。输入为 `tests/小说/斗破苍穹前5章.txt` 和 `runs/doupo-first5-m1-scope-v4/m1-model-outputs.json`，原文 hash 与旧 manifest 一致。输出位于 `runs/doupo-first5-m2-dev7-20260831/`。

最新 N2 重放得到 18 exact、5 individual describe、1 collective 和 57 evidence bindings。M2 exact attribution 18/18 成功，50 条模型事实全部严格逐字 Grounding，0 issue/0 failure。首次运行在 5 个任务后遇到 HTTP `IncompleteRead`；修复 Provider 瞬态异常分类后恢复完成剩余 13 个，没有重复前 5 次调用。

模型输出和阶段输出分别在 `m2-model-outputs.json` 与 `m2-grounded-results.json`。旧 run 未覆盖。由于 N3 尚未生成 remaining describe pool，本任务未运行 promotion；本次实跑不构成人工质量 Gate。
