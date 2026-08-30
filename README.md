# Novel Character Generator

面向中文小说角色视觉事实的证据优先语义流水线。目前仓库只保留 V2 开发路线：M1 v2 视觉证据发现 shadow 链、legacy N2/M2 工程切片，以及 M3–M5 的设计契约。

## 当前状态

- 主 M1 Prompt 已按用户决定回退到 v2.8；v2.9 双集结果保留为历史证据。005 的非唯一引文与少年脸貌漏召回作为已接受残余风险，M1 以条件 Gate 进入 N2 开发。N2 v2 已实现确定性 `GroundedEvidencePacket`：唯一引文固化 span/hash/context，重复引文延后，非逐字引文拒绝。
- legacy M1 工程链和审核数据集保留作历史对照；真实模型质量为 5/6，不能作为 v2 Gate。
- N2 确定性 grounding/context 工程 Gate 已通过。
- M2 离线工程 Gate 已通过；9 条测试集仍待审核，尚无真实模型结果。
- M3 身份组件、M4 时间范围、M5 联合复核尚未实现。
- 当前没有 Web API、Worker、数据库、向量库或图像生成运行时。

## 安装与检查

要求 Python 3.12 和 `uv`：

```powershell
uv sync --dev
uv run pytest -p no:cacheprovider
uv run ruff check src tests scripts
uv run mypy
```

离线评分：

```powershell
uv run python scripts/evaluate_m1_local_observation.py <m1-outputs.json>
uv run python scripts/evaluate_m1_visual_evidence.py <m1-v2-outputs.json>
uv run python scripts/evaluate_m2_field_disambiguation.py --dataset tests/evaluation/m2_field_disambiguation_v1.json --outputs <m2-outputs.json>
```

M1 真实模型评测从环境变量读取 `LLM_PROVIDER`、`LLM_API_KEY`、`LLM_MODEL`，可选使用 `LLM_BASE_URL` 等模型参数：

```powershell
uv run python scripts/run_m1_evaluation.py
```

技术入口见 [docs/README.md](docs/README.md)。
