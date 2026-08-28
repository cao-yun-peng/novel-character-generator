# 项目版本

> 只在版本号、发布状态、升级路径或兼容性发生变化时读取和更新。

## 当前版本

- 版本号：`0.0.0`
- 发布状态：未发布
- 兼容性说明：视觉候选 Schema 为向后兼容输入的 `visual-observation-v3.4`，默认 Prompt 仍为 `visual-extraction-prompt-v2.5`；`visual-extraction-prompt-v2.6` 只保留为未通过切换门禁的实验候选。R2 候选边界为 `character-entity-resolution-v1.1`、Prompt 为 `entity-resolution-prompt-v1.5`。R6 使用 `image-provider-registry-v1`、`canonical-zh-character-v1`、`dashscope/qwen-image-plus` 与通用同步 `openai-compatible-image-v1`（注册 `timicc/gpt-image-2`）；默认 `IMAGE_PROVIDER=disabled`，数据库 head 为 `c4b8a7d219e1`。
- 评测兼容性：当前默认 R1 黄金 rubric 为 `visual-observation-seed-v3.1` / dataset v1.1；旧 v0 永久保留用于复现实验历史。v1.1 修正测量语义，旧 v1 首评与 v1.1 分数不可直接当作模型变化。
- V2 M1 shadow 兼容性：`local-observation-contract-v1.1`、`local-observation-discovery-prompt-v1.1` 保持不变；首次真实开发基线使用 v1，测量修正版为 `m1-local-observation-v1.1-draft2`。它不替代 `visual-observation-v3.4`，不进入 Worker 或数据库；当前模型质量 Gate 不通过。
- 最后更新：2026-08-28

## 下一版本计划

- 目标版本：`semantic-pipeline-v2`（设计中，不是发布版本）
- 当前设计基线：`semantic-pipeline-v2-design-v1.1`
- 计划内容：M1 全有效 Chunk 局部命题、M2 全量字段/载体语义、M3 全量相关身份组件与重开、M4 全量时间/持续性及 scene/event 起止、M5 分组 downgrade-only 联合复核，以及确定性证据/Promotion/分层聚合。
- 发布条件：P0 离线回放、分节点 A/B、shadow、真实跨作品质量 Gate、预算与恢复、V1 回滚演练和用户批准全部完成。

## 版本历史

按时间倒序追加：版本号、日期、状态、主要变更、原因、兼容性、证据 ID 和 Gate 结果。

- `m1-local-observation-v1.1-draft2`，2026-08-28，用户审核待定/模型质量 Gate 不通过：对 v1 真实输出发现的四处标注边界做测量修正，同批输出零调用重评为 11 pass / 0 review / 4 fail；当前 15 case 转为回归集，后续独立 Gate 需要新 held-out。兼容性：仅 dataset/evaluator report 扩展，不修改 M1 Prompt、Worker、数据库或 V1；证据 `E-20260828-PIPELINE-V2-M1-013-REAL1`。

- `local-observation-contract-v1.1` / `local-observation-discovery-prompt-v1.1` / `m1-local-observation-v1-draft1`，2026-08-28，工程 Gate 通过/用户数据 Gate 待审：M1 strict DTO、证据与局部引用校验、shadow artifact、Provider adapter、15-case dataset/evaluator/CLI 完成；R1/R2/M1 合并公共结构化调用层并删除重复 Prompt/循环。兼容性：纯 shadow，无数据库/Worker/默认 Prompt 变化，V1 保留；251 tests、Ruff、125 source Mypy 通过，0 Provider。证据 `E-20260828-PIPELINE-V2-M1-013`。

- `semantic-pipeline-v2-design-v1.1`，2026-08-28，Stage 4 架构 Gate 条件通过：在 v1 基础上补齐全 Chunk M1、M2 semantic unit/referent、M3 component completeness/supersede、M4 boundary/end condition、M5 review group、5 输入+5 输出条件 Schema、precision+coverage 联合 Gate、模型/数据/人工/运维边界。兼容性：仅设计工件升级，V1 生产路径和历史 v1 证据不变；未实现、未迁移、未调用 Provider。条件为 P0 冻结 promotion coverage 与 review capacity 数值阈值；证据 `E-20260828-PIPELINE-V2-DESIGN-012-R1`。
- `semantic-pipeline-v2-design-v1`，2026-08-28，设计评审：冻结 N0-N11 输入输出、M1-M5 系统提示词与模型输出 Schema 原型，质量优先于首轮降本；与 V1 并存，未实现、未迁移、未调用 Provider、不得切换生产。证据 `E-20260828-PIPELINE-V2-DESIGN-012`，Gate 为设计待用户评审。
- `visual-observation-seed-v3.1` / dataset `v1.1`，2026-08-28，开发 Gate 通过：修正阶段键层级、值异体、安全 deferred、owner/surface alias、temporal 窄匹配/去重、raw mention 和真实 identity-dependent gold；asserted/deferred 双写进入硬 Gate。74 份保存 candidates 离线重评，0 Provider 调用；236 项完整回归通过。证据 `E-20260828-R1-GOLD-FIX-011`。
- `openai-compatible-image-v1` / `timicc-gpt-image-2`，2026-08-28，真实 smoke 条件通过：官方 Images 请求形状、同步 base64 暂存恢复、严格 URL/host/PNG/hash 与脱敏失败路径已完成；23 项定向、230 项完整 Pytest、Ruff、修改范围 Mypy 通过。一次真实 `gpt-image-2` 调用成功，但请求 1328×1328 返回 1024×1536，Provider 可用性通过、尺寸一致性 Gate 不通过。证据 `E-20260828-R6-ALIYUN-009`。
- `canonical-zh-character-v1`，2026-08-28，开发 Gate 通过/视觉候选待审：六类 `ImageRenderSpec` 字段转为自然中文，24 条 Prompt clause 保留来源，Renderer 可注册替换且版本进入图片评测元数据；一张 `qwen-image-plus` 真实候选成功，尚不构成 baseline。证据 `E-20260828-R6-ALIYUN-009`。
- `visual-observation-seed-v3` / dataset `v1`，2026-08-28，开发 Gate 通过：31 个通用硬黄金 case、6 个真实 source-backed 审计切片；required/allowed/forbidden、mention/deferred/temporal 与重复/双写指标进入评分。v0 未修改，逐 case/A-B 工具默认 v1，无真实调用或迁移；225 项完整回归通过，证据 `E-20260828-R1-GOLD-008`。
- `image-provider-registry-v1` / `dashscope-qwen-image-plus-v1`，2026-08-28，离线实现/真实 smoke 待凭据：统一 Provider 注册、生命周期关闭、同步/异步结果恢复与版本留痕；阿里云异步单图提交、轮询 defer、受限下载与提交未知失败关闭。默认禁用，需迁移到 `c4b8a7d219e1`，211 项回归与迁移往返通过。未生成真实图片，不代表视觉 Gate 或 baseline 通过；证据 `E-20260827-R6-ALIYUN-009`。
- `visual-observation-v3.4` / default `visual-extraction-prompt-v2.5` / experimental `visual-extraction-prompt-v2.6`，2026-08-27，开发与真实 A/B 完成：Schema 增加 inferred/uncertain deferred 分类及配饰、年龄推断、眼睛/肤色、面部、纹身确定性门禁；Provider 支持显式 Prompt/version 注入。三轮 130 次真实 DeepSeek 调用后 v2.6 未通过成本、噪声和拒绝门禁，默认指针保持 v2.5；无数据库迁移，203 项完整回归通过，证据 `E-20260827-R1-PROMPT-AB-007`。
- `visual-observation-v3.3` / `visual-extraction-prompt-v2.5` / `character-entity-resolution-v1.1` / `entity-resolution-prompt-v1.5`，2026-08-27，开发增量通过：四类 mention、旧标签兼容、age/clothing 字段门禁、分级 evidence locator、原文精确 quote 与修复审计；无数据库迁移或额外模型调用；193 项完整回归通过，证据 `E-20260827-R1-DATA-006`，真实新 Run 质量仍待复核。
- `raw-model-response-v1`，2026-08-27，开发增量通过：R1/R2 Provider 原始响应按调用持久化并由开发管理员页签读取；数据库需要升级到 `f9a1e5c72d30`，默认关闭且生产拒绝启用；证据 `E-20260827-DEV-RAW-001`，不代表逐 token streaming 或失败响应捕获。
- `character-entity-resolution-v1`，2026-08-27，开发增量通过：逐 Chunk 累计记忆、十章/尾批收敛、final-only Observation、调用审计和恢复；改变自动抽取写入时序，需要升级数据库到 `d9a42b71c305`；证据 `E-20260827-R2-ENTITY-001`，不代表 R2 跨作品质量 Gate 或生产发布。
- `visual-observation-seed-v2`，2026-08-26，开发中：结构/value/evidence 分层、pass/review/fail 三态和局部等价值；兼容生产 `visual-observation-v3`，但评测结果 JSON 增加字段，证据 `E-20260826-R1-EVAL-004`，不代表发布 Gate。
- `visual-extraction-prompt-v2.2`，2026-08-26，开发中：增加通用语义边界、原子拆分、最小证据、原文语言和值规范；兼容 `visual-observation-v3`，证据 `E-20260826-R1-PROMPT-003`，不代表发布 Gate。
- `visual-observation-v3.2` / `visual-extraction-prompt-v2.4` / `entity-resolution-prompt-v1.4`，2026-08-27，开发增量通过：显式姓名门禁、伪年龄与字段语义门禁、通用 transformation/other 信号、age/reincarnation 阶段推导、去重与语义冲突归一化；157 项测试、Ruff、Mypy 通过；首次干净真实 run 总体 Gate 为 review，证据 `E-20260827-R123-REAL-001`。
