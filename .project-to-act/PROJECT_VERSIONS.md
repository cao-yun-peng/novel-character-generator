# 项目版本

## 当前版本

- 分支：`v3-simplified-character-evidence`
- 契约：简化人物证据流程 V3 草案
- Schema：`3.20.0-draft1`
- 运行时版本：`0.1.0.dev20`
- 发布状态：未发布

## 版本原则

当前分支不携带旧实现。旧内容只存在于 Git 历史和旧分支，不作为新项目依赖、文档或验收证据。

## 版本历史

- 2026-09-02：Schema 升级到 `3.20.0-draft1`、运行时升级到 `0.1.0.dev20`；071 运行时复用原 M1 Manifest 的 17 个重叠 Chunk，以 node.chunk_id 注入已绑定人物，模型边界仅保留 name/aliases/text，系统元数据、Grounding、去重和状态物化均在代码侧。真实模型运行尚未验收。
- 2026-09-02：Schema 升级到 `3.19.0-draft1`、运行时升级到 `0.1.0.dev19`；新增 `document-character-appearance-scopes-v1`、确定性章节解析、canonical fact 顺序分配和保守 persistence 基线，life/form/scene 不确定项显式为 unknown。
- 2026-09-01：Schema 升级到 `3.18.0-draft1`、运行时升级到 `0.1.0.dev18`；新增 `document-character-fact-groups-v1`、`same-character-span-structure-v1`、稳定 canonical fact ID、逐 raw fact/occurrence 双向 provenance、失败关闭构建器和 CLI。
- 2026-09-01：Schema 升级到 `3.17.0-draft1`、运行时升级到 `0.1.0.dev17`；候选策略升级为 `bounded-local-candidate-retrieval-v3`，新增 `grounded-local-coreference-v1` deterministic edge、严格局部关系回放和保存 M3/rescue 决策的零 Provider registry/profile 重建 CLI。
- 2026-09-01：Schema 升级到 `3.16.0-draft1`、运行时升级到 `0.1.0.dev16`；身份聚合升级为 `global-constrained-identity-v3`，最终 same/different 会关闭历史 uncertain，冲突失败关闭；cluster rescue 升级 v2，以无向簇对去重并执行最多三轮的固定点裁决，支持复用既有 grounded run。
- 2026-09-01：Schema 升级到 `3.15.0-draft1`、运行时升级到 `0.1.0.dev15`；新增残余 cluster-level 身份裁决、候选专属 `relationship_context_quotes` 证据域、严格 Grounding、断点续跑和 supplemental registry 重建。
- 2026-09-01：Schema 升级到 `3.14.0-draft1`、运行时升级到 `0.1.0.dev14`；身份聚合升级为 `global-constrained-identity-v2`，全局 same 图受 cannot-link 约束，未决 singleton 保留事实；候选/上下文策略升级 v2，新增显式介绍召回和有界 bridge 过渡窗口。
- 2026-08-31：Schema 升级到 `3.13.0-draft1`、运行时升级到 `0.1.0.dev13`；新增 `document-character-profiles-v1`、`strict-fact-hash-profile-join-v1`、确定性档案构建函数和 CLI。输出物化完整事实与来源，保留零事实人物、未绑定事实、冲突/review/cannot-link，并对文档、hash、引用和 span 失败关闭。
- 2026-08-31：Schema 升级到 `3.12.0-draft1`、运行时升级到 `0.1.0.dev12`；新增 `document-local-character-nodes-v1`、`m3-identity-envelope-v1`、最小 M3 输入输出、`grounded-identity-decision-v1` 和 `document-character-registry-v1`。身份任务支持有界候选、严格 quote Grounding、cannot-link、冲突保留、断点续跑与追加式运行历史。
- 2026-08-31：Schema 升级到 `3.11.0-draft1`、运行时升级到 `0.1.0.dev11`；grounded promotion result 升级 v6 并加入 `promotion-partial-fact-acceptance-v1`。唯一事实部分接受，歧义事实独立 review；N3 task/summary 升级 v2 防止旧 grounded 缓存混用，并新增保存模型输出离线重放 CLI。
- 2026-08-31：Schema 升级到 `3.10.0-draft1`、运行时升级到 `0.1.0.dev10`；N2 grounded packet 升级到 v6，删除 `quote_hash`/`mention_quote_hash`，M1 chunk/summary 升级到 v4/v3 防止旧包混合续跑。新增 `document-character-evidence-v1`、绝对 span 回放、结构安全的重叠去重、来源 artifact/chunk/fact hash 与全 occurrence 保留。
- 2026-08-31：Schema 升级到 `3.9.0-draft1`、运行时升级到 `0.1.0.dev9`；实现 N3 chunk/target/pool DTO、跨 exact span 仲裁、剩余池重建、来源 hash guard、promotion 断点续跑和分离产物。promotion 标签可直接复用已验证 mention quote，不保存标签 span；真实斗破 5/5 promotion 完成，1 个歧义任务进入 review。
- 2026-08-31：运行时升级到 `0.1.0.dev8`；新增既有 M1 run → 当前 N2 重放 → 可恢复 M2 exact attribution 批处理与 CLI、分离产物和追加式运行历史；Provider 将 `http.client.HTTPException`（含 `IncompleteRead`）纳入有界瞬态重试。Schema 保持 `3.8.0-draft1`。
- 2026-08-30：Schema 升级到 `3.8.0-draft1`、运行时升级到 `0.1.0.dev7`；实现 M2 exact attribution 与 remaining-describe promotion 双模式、阶段专用 DeepSeek json_schema 名称、稳定 task/pool/promotion hash、代码侧事实来源回填、promotion 重叠拦截和未分配残片保留。真实 M2 Provider 质量尚未验收，N3 尚未实现。
- 2026-08-30：Schema 升级到 `3.7.0-draft1`；M2 模型输入输出改为无 ref/span/状态的肯定事实边界，归属输出仅含 `belongs_to_target`，事实仅含 `fact_quote/category/attribute/value`；M2 与 promotion envelope 升级到 v4。运行时仍为 dev6，M2 尚未实现。
- 2026-08-30：Schema 升级到 `3.6.0-draft1`、运行时升级到 `0.1.0.dev6`；N2 增加 `exact-evidence-precedence-v1`，grounded packet v5、chunk result v3、batch summary v2，并新增独立 N2 trace 产物。
- 2026-08-30：运行时升级到 `0.1.0.dev5`，CLI UTF-8 文件读取显式保留 CRLF/LF 原始换行；斗破前5章真实回归使用该版本完成。
- 2026-08-30：Schema 升级到 `3.5.0-draft1`、运行时升级到 `0.1.0.dev4`；新增 mention scope、collective quarantine、纯空白等价证据恢复，移除 mention occurrence 数量和位置；grounded packet v4、chunk result v2。
- 2026-08-30：运行时升级到 `0.1.0.dev3`，新增可恢复的 `run-deepseek-m1` 全文批处理、逐块产物、汇总和失败诊断；真实 17 Chunk 样本跑通。
- 2026-08-30：运行时升级到 `0.1.0.dev2`，新增 DeepSeek Responses API/json_schema Provider、环境配置、脱敏 usage trace、有界重试和 `probe-deepseek-m1` 命令；未执行真实付费调用。
- 2026-08-30：建立运行时 `0.1.0.dev1`，包含重叠分块 Manifest、M1 DTO/提示词/Provider 协议、严格输出验证与 Chunk 局部 grounding；具体 Provider 尚未接入。
- 2026-08-30：Schema 升级到 `3.4.0-draft1`，新增 remaining describe 独立建人的一对多模型输入输出、代码信封、promotion hash 和 promoted character ref。
- 2026-08-30：Schema 升级到 `3.3.0-draft1`，统一模型输入输出边界；新增 M1/M2 orchestration envelope，M2 改为每个 exact 一次携带全部 describe 的批量 payload。
- 2026-08-30：Schema 升级到 `3.2.0-draft1`，增加文档覆盖 Manifest、N2 provenance、M2 occurrence/四层 span/pair key 和 N3 绝对消费/冲突 span。
- 2026-08-30：Schema 升级到 `3.1.0-draft1`，加入 exact/describe/null、candidate_mentions、exact×describe M2 输入输出和 N3 describe 池解析结果。
- 2026-08-30：建立干净的新项目基线，只保留新契约和机器 Schema。
