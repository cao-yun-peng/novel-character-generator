# E-20260829-PIPELINE-V2-M1-V27-GATE-032

## 授权与固定配置

- 用户于 2026-08-29 明确授权将短集 16 条与真实集 10 条小说 Chunk 发送到 `.env` 配置的外部 Provider，用于 Prompt v2.7 评测。
- Provider/model：DeepSeek / `deepseek-v4-flash`；Prompt：`visual-evidence-discovery-prompt-v2.7`，运行时 SHA-256 `b34d45b9193b002640733de21846d5119537ca34175a2a6c0dbde89967ff3cb5`。
- Rubric：`visual-evidence-evaluation-rubric-v2.5`，本轮实现 SHA-256 `3965cadb0a11fc807de7e2a246b002f323c263950ab71241345a9809bd7b3a5e`。
- Deterministic validation / Source Match Policy v2 实现 SHA-256 `2d1f9318085bc7755777004a292962c84a81a8db8f769a0b01e9a61cf8b9745e`。
- 受限网络第一次连接失败且未建立成功请求；用户明确授权后才使用提升网络权限运行。未保存或展示 API key，未写数据库，未产生 active Observation。

## 短集 v2.3-draft

- Dataset SHA-256：`174fec6f05363f2bf001cfc13aed5acfa688143d5a3fd5f9d386e99f1826ddda`。
- 16 次调用完成：12 succeeded、4 completed_with_warnings（空结果边界样本），0 deterministic validation failure；总 token 29,136。
- Rubric：16 pass / 0 review / 0 fail；evidence recall、candidate precision、quote fidelity、required owner recall、owner binding precision、must-be-null accuracy 全部为 1.0。
- Outputs SHA-256：`bb3993ef6c7b626881a64a481bdfe50e467bac365ce0daa853fa2255573536c4`；Report SHA-256：`a855efb7249055550e80a5c33ac43489a994387b850730011e0a41ff8ae86b17`；run manifest SHA-256：`3abb2bc20628f1524008d93a7d94e069b6b9bf756a3f6dcfb6319c606c44e621`。

## 真实集 v2.5-draft

- Dataset SHA-256：`c08440ad746b9dcc2a809ad762cdffc276bca7ec404139d429fdc66e6c13af08`。
- 10 次调用全部 succeeded，0 warning，0 deterministic validation failure；总 token 27,075。
- Rubric：2 pass / 6 review / 2 fail；evidence recall `0.8076923076923077`、candidate precision `0.34328358208955223`、quote fidelity `1.0`、required owner recall `0.9090909090909091`、owner binding precision `0.34328358208955223`、must-be-null accuracy `1.0`。
- Outputs SHA-256：`ba6339759c95744ea60a93d1314e4b9691af4123a6b6d640c8c3175ba2b11436`；Report SHA-256：`fe0b9aab54f79183693297219c0fcfb6640c65637376cc5c3a01fbe9793c0be5`；run manifest SHA-256：`23e0267ad03d4aa7a5e90797f5701f667b3aafdd61daf967a3cf544a446e4717`。

## v2.6 → v2.7 归因

- 短集保持 16/0/0，无回归。
- 008 从 fail 变为 review：铁鞋、年龄发辫、金环和虎牙 4/4 required 全部命中；Prompt 的短视觉线索复扫有效。
- 005 仍为 fail，但 deterministic validation failure 已消失，月白衣袍完整视觉跨度已命中。剩余 `young_face` 与 `qing_robed_steward_clothing`：模型把少年脸貌和青衫老者眼睛合并为一个绑定青衫老者的长候选，形成跨 owner 颗粒度错误；且未召回另一处唯一的“一名青衫老者”。
- 009 从 review 回归为 fail：模型实际召回了 transformation 的大量局部视觉内容，却把三个连续复合跨度拆成多个小候选，当前 Rubric 不聚合多个 actual candidates 共同覆盖一个复合 gold；同时输出 17 个候选，包含若干纯动作，precision 明显下降。这既是 Prompt 颗粒度回归，也暴露是否允许多候选聚合覆盖的待审口径。
- 汇总状态仍为 2/6/2，但 evidence recall 从 `0.8461538461538461` 降至 `0.8076923076923077`，candidate/owner precision 从 `0.46153846153846156` 降至 `0.34328358208955223`；quote fidelity 升至 1.0，required owner recall 从 `0.8181818181818182` 升至 `0.9090909090909091`。
- 对比工件 SHA-256：`5a148d380a4547f17723dc5be332b285d91acb866546cdde7a259474f05aebbf`。

## 工程验证与 Gate

- Pytest：89 passed。
- Ruff：通过。
- Mypy：`src scripts` 共 36 source files 无问题。
- `git diff --check`：通过（见任务完成时复验）。
- Project-to-Act validate：通过（见任务完成时复验）。
- 两份报告的 `quality_gate` 均为 `blocked_pending_user_review`；真实集还有 005/009 fail，因此 M1 evidence Gate 未通过。
- `AGENT_LIFECYCLE.json` 的既有 revision 1/current stage 5 历史问题未由本任务修改，本任务不宣称 lifecycle Gate 或发布 Gate 通过。
