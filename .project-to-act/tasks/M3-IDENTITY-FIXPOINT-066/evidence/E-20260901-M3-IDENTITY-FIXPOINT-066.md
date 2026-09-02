# M3 身份固定点修复与斗罗实跑证据

- 证据 ID：`E-20260901-M3-IDENTITY-FIXPOINT-066`
- 日期：2026-09-01
- runtime/schema：`0.1.0.dev16` / `3.16.0-draft1`
- 输入：`tests/小说/斗罗大陆前20章.txt`
- 基础身份运行：`runs/douluo-20ch-e2e-dev13-20260831/identity`
- 复用裁决：`runs/douluo-20ch-e2e-dev13-20260831/identity-rescue-live-dev15`
- 输出：`runs/douluo-20ch-e2e-dev13-20260831/identity-rescue-fixedpoint-dev16`

## 确定性修复

1. `global-constrained-identity-v3`：历史 uncertain 只有在最终人物分量既未合并、也未被 cannot-link 区分时才继续 unresolved。supplemental same/different 可关闭旧状态；同一关系同时存在 same/different 时 cannot-link 优先、禁止合并并生成 `contradictory_identity_decisions` review。
2. `residual-cluster-adjudication-v2`：候选按稳定的无向人物簇对规范化，A→B 与 B→A 合为一个候选；模型仍不因同名自动合并。
3. 批处理最多三轮：每轮完成后用全部 grounded 决策重建 registry，再生成尚未解决的任务；没有决定性 registry 变化或没有任务时提前停止。支持从旧 rescue run 导入 grounded 决策，避免重复付费。
4. 档案连接器显式兼容已知候选召回策略 v1/v2；不伪造旧来源版本，身份策略、文档、事实 hash、Chunk/hash/span 校验仍严格。

## 斗罗运行

- 复用 grounded 决策：5（4 same、1 different），重复调用 0。
- 复用后预检：9 个全局人物、1 unresolved、2 cannot-link；旧“男孩儿→唐三” uncertain 已关闭；只生成 1 个唐三残余任务、1 个候选、3 条候选专属关系上下文。
- 新 DeepSeek 调用：1，HTTP 200，5,327 tokens（input 4,701、cached input 640、output 626、reasoning 575）。
- 新裁决：`same_character` / `name_variant`。
- 身份证据：“小三，来，让爷爷看看。”老杰克向唐三挥了挥手。
- 文档 span：`[10205,10229)`，exact 回放；Grounding issue 0。
- 固定点：第一轮后无 pending task，`termination_reason=no_pending_tasks`。
- 缓存复跑：1/1 resumed，新增 Provider 调用 0。

## 最终注册表与档案

- 全局人物：9 → 8。
- 唐三簇：2 → 1；唯一人物 `char-f47075b7019563fd8315`，标签 `唐三/小三`，16 members、39 facts。
- unresolved：1，仅“看门的青年”；其与候选间没有可支撑身份判断的关系原文，因此不调用模型、不猜测。
- cannot-link：2；男孩儿与唐三的 cannot-link 保留且不再伴随旧 unresolved。
- appearance facts：129/129 保留；最终 profiles 为 8 人物、129 assigned、0 unassigned、130 source occurrences、13 possible conflicts、9 review。

## 验证

- `python -m unittest discover -s tests`：135 passed。
- `python -m compileall -q src tests`：通过。
- Draft 2020-12：`DocumentCharacterRegistry`、`DocumentCharacterProfiles` 实例通过。
- Project-to-Act `--validate`：valid/managed/0 issues。

## 工件哈希

- `cluster-rescue-model-outputs.json`：`1793ddca665a8a05b6b45f21bdad00443c152a94c70c30e35be6fefb5106cc15`
- `grounded-cluster-rescue-decisions.json`：`b0d9a1ea97d9d16da0d6de87301d558f8c62f555d6452461f0dad3d96563c7b6`
- `document-character-registry.json`：`3a518c460a37a9685d73e1d38a152c0301ea467e91840035aac05772ce8d2b3a`
- `document-character-profiles.json`：`3f1d4a859dc624e47c2d37c5bd4fc53305e1f5fb1c6e81fd10cb6238f8efd5cb`
- `provider-traces.json`：`4240f4c763e153d56e49bce1012b99b9b010a9f2230fa6673c10d6b1d463cd96`
- `run-history.json`：`a6bb4e2ff223a7eda579dd9d4c59d230c61ed5d1caebbe4c4a50a09d9bbe1cae`
