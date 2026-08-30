# M1 Prompt v2.8 双集 Provider 回归证据

## 授权与运行范围

- 用户明确确认：允许将短集 16 条与真实集 10 条 Chunk 文本发送至 `.env` 配置的外部 LLM Provider，用于 Prompt v2.8 评测。
- Provider/model：DeepSeek / `deepseek-v4-flash`；wire API `chat_completions`；reasoning effort `none`；max output tokens 4096。
- 未保存 API key 或原始 Provider 响应；无数据库写入、无 active Observation、无生产路由变更。

## 结果

### 短集 `m1-visual-evidence-short-v2.3-draft`

- 运行目录：`data/diagnostics/m1-v2.8-short-v2.3-draft/`
- 16/16 pass，0 review，0 fail。
- evidence recall 1.0；candidate precision 1.0；quote fidelity 1.0；required owner recall 1.0；owner binding precision 1.0；must-be-null accuracy 1.0。
- 16 条均成功经过 Provider 与 deterministic validation；无 deterministic validation failure。

### 真实集 `m1-visual-evidence-real-v2.5-draft`

- 运行目录：`data/diagnostics/m1-v2.8-real-v2.5-draft/`
- 2 pass，5 review，3 fail；10/10 已完成 Provider 尝试。
- evidence recall `0.8461538461538461`；candidate precision `0.4528301886792453`；quote fidelity `0.9880952380952381`；required owner recall `0.8636363636363636`；owner binding precision `0.4528301886792453`；must-be-null accuracy `1.0`。
- deterministic validation：9 条 succeeded，005 为 `visual_evidence_quote_not_unique_in_chunk`；单条失败已保留输出并继续批次。

## 重点案例归因

- 005：v2.8 已不再把少年、青衫管家和月白衣袍客人的外观混成一个候选；但模型输出短引文“青衫老者”，在 Chunk 中出现两次，触发 deterministic validation，且未命中 `young_face`。这是引文唯一定位/召回仍未解决的 Prompt 行为问题，不能用 owner 代替 evidence quote 消歧。
- 006：模型输出“少女年龄和萧炎相仿……”并正确绑定少女。用户复审确认该相对年龄内容没有问题；报告中的 `missing_required_candidate:woman_relative_age` 仅反映当前金标跨度口径，不作为本轮 Prompt 缺陷，也未修改 Dataset。
- 009：前三个连续 transformation 复合候选均已正确召回，v2.7 的 transformation 原子化回归不再出现；回到女孩形态内容和 owner 也已被模型召回。用户复审确认该案例没有问题；报告中的 `returns_to_girl_form` 缺口仅反映当前 alias 口径，不作为本轮 Prompt 缺陷，也未修改 Dataset。

## v2.7 → v2.8

- 短集：16/0/0 → 16/0/0。
- 真实集：2/6/2 → 2/5/3。
- 真实 evidence recall：`0.8076923076923077` → `0.8461538461538461`。
- 真实 candidate precision：`0.34328358208955223` → `0.4528301886792453`。
- 真实 quote fidelity：`1.0` → `0.9880952380952381`，下降原因是 005 的非唯一引文被确定性校验拦截。
- 真实 required owner recall：`0.9090909090909091` → `0.8636363636363636`；下降来自 006 当前金标跨度与 009 alias 尚未覆盖，不代表跨 owner 混绑回归。
- 真实 owner binding precision：`0.34328358208955223` → `0.4528301886792453`。

## 工件与哈希

- Prompt runtime SHA-256：`3d0a85a66b3a52c78304556643dd71cea58f873796fee9ff46c5919a16418543`。
- Short Dataset SHA-256：`4877dc3f4a4fdaf75305437deb96f2297a2f9bb0b0269ba29494334d399c7`。
- Real Dataset SHA-256：`1ad18fde6809d6c90296f8324cac1d19e02b5d72462270b64b28864e99d0ce22`。
- Short outputs/report/run SHA-256：`3be55f9d4d550d9ef2c9467a71c06243d1eb7c556e06e88e5bafd2a4eaeb3e62` / `ef5bc29aa01fa23df0a1adbb2463bcc7d640de9e225026d59458452dedfd7559` / `b6b07839da2365d3d0a9a6f80f15c418537c760a66234959ee04765db51043dd`。
- Real outputs/report/run SHA-256：`4a52abdf223ade3c70f0272b061aa8aa1b0bcdce4be913268ab529ede9498b62` / `6a0e74406e0dfd1501afe138759f87a9e3998e7296e6bba7cacf08ce34fb5f9e` / `508389e39926144d294bda6a58e977592dbb9fb3ff1416cd466b7bc82cacf729`。
- Real run manifest additionally records Rubric SHA-256 `5414a676056afaacd28ad2a85486673626ba96c64207c7f69179159006cd343f` and validation implementation SHA-256 `2d1f9318085bc7755777004a292962c84a81a8db8f769a0b01e9a61cf8b9745e`。

## Gate 结论

- 工程与运行证据完整，但 `quality_gate` 仍为 `blocked_pending_user_review`；M1 evidence Gate 未通过。
- v2.8 对 009 的主要 Prompt 根因已有证据改善；用户复审确认 006/009 不构成问题，当前仅保留 005 的唯一引文与少年脸貌缺口。
