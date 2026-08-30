# E-20260828-PIPELINE-V2-M1V2-020-REAL-RERUN

- 时间：2026-08-28，Asia/Shanghai。
- 用户授权：明确确认允许将 15 条测评样本文本发送到 DeepSeek API。
- 运行配置：`LLM_PROVIDER=deepseek`、`LLM_MODEL=deepseek-v4-flash`、`LLM_BASE_URL=https://api.deepseek.com`；API key 未写入日志或账本。
- 运行命令：`uv run --project . python scripts/run_m1_visual_evidence_evaluation.py --allow-draft-diagnostic --output data/diagnostics/m1-v2/outputs.json --report data/diagnostics/m1-v2/report.json`，退出码 0，15/15 case 完成。
- 评分命令：`uv run --project . python scripts/evaluate_m1_visual_evidence.py data/diagnostics/m1-v2/outputs.json --report data/diagnostics/m1-v2/report.json`，复用同一批真实输出，未重复调用 API。
- 结果：13 pass、0 review、2 fail；`evidence_coverage_recall=0.833333333333333`、`candidate_precision=1.0`、`quote_fidelity=1.0`、`owner_anchor_recall=1.0`、`owner_anchor_precision=0.6`；12 个 required candidates 匹配 10 个，20/20 引文位于当前 Chunk。
- 失败样本：`m1-v2-negated-004`（否定外貌漏召回）、`m1-v2-transformation-008`（变身外貌漏召回）。
- Gate：数据集仍为 `draft_user_review_required`，报告 `quality_gate=blocked_pending_user_review`；本次结果是开发诊断，不是发布批准。
- 产物哈希：`data/diagnostics/m1-v2/outputs.json` SHA-256 `94F52EEFD1FF130BD945A65E7EA4977B40FE0D2321466AECA282B2683E8888B5`；`report.json` SHA-256 `327DCC0E4841F38410F6C13AB6B9FD6BA0B44A01F3BC840B53832BF51678B385`。
- 有效期：直到重新运行真实评测、数据集金标或 Prompt/合约版本发生变化。
