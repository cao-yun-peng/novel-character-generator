# 项目版本

## 当前版本

- 分支：`v3-simplified-character-evidence`
- 契约：简化人物证据流程 V3 草案
- Schema：`3.30.0-draft1`
- 运行时版本：`0.1.0.dev33`
- 发布状态：未发布

## 版本原则

当前分支不携带旧实现。旧内容只存在于 Git 历史和旧分支，不作为新项目依赖、文档或验收证据。

## 版本历史

- 2026-09-05：dev33 完成 Web 里程碑 C（084）：R11 人工决策提交闭环——追加式决策日志、幂等键、乐观锁 revision、reopen 补偿与决策历史审计，及 R08 subject 指定 run 解析端点。311 tests/19 subtests 与 `scripts/c_milestone_smoke.py` 联调通过；Provider 0，未发布。

- 2026-09-05：dev32 完成 Web 里程碑 A+B（082/083）：FastAPI 只读基座、React 三栏页面、坐标契约、异步任务与 12 阶段流水线执行器（补记，漏登版本历史）。275 tests/19 subtests 与 `scripts/b_milestone_smoke.py` 联调通过；Provider 0，未发布。

- 2026-09-05：dev31 修复模型重复 evidence_quotes 的规范化，保证持久关系可重新 Grounding；模型请求及 Schema 3.30 不变。52 个真实响应离线重放通过，4 个 Snapshot 通过；未发布。

- 2026-09-05：dev30/Schema 3.30 新增 AutomaticEventModelOutput、AutomaticRelationModelOutput 和 automatic-appearance-semantics-v1。Snapshot policy 升为 automatic-semantic-snapshot-v2，新增 narrative_scene 与语义证据/复核，自动产物参与 ID。原 M1/M2/M3、raw facts 和旧关系策略不改；不用自动产物时仍支持确定性基线。未发布。

- 2026-09-05：dev29/Schema 3.29 引入 character-snapshot-v1、fact-applicability-events-v1 与 evidence-interval-applicability-v2；原人物卡由 snapshot-render-adapter-v2 输出。模型 payload、raw facts 和 StateSegment observation 不变；保存状态的 relation v1 需重建到当前策略后查询。保留 LegacyRenderReadyCharacterProfilesV1 的历史 Schema 验证，未发布。

- 2026-09-05：dev28 为 promotion/identity/rescue/transition 代码侧任务记录添加 request_fingerprint 与缓存预检，promotion 恢复时重建 Grounding。模型 payload、领域输出和机器 Schema 未改，Schema 保持 3.27.0-draft1；旧无指纹记录可保留查看但不能普通续跑。未发布。

- 2026-09-05：dev27/Schema 3.27 引入 M2 code-only grounding_policy_version=unique-fact-occurrence-attribution-v2、可追踪歧义 occurrence、关系 v2 否定保护、M1/M2 请求指纹与缓存重验、replay-m2-grounding CLI 和 dev 测试依赖。模型 payload 与原始事实不改；旧 M2 包需离线重放，旧关系 v1 状态需重建后才供新 compiler 使用。R05 跨所有阶段的统一迁移尚未完成，未发布。

- 2026-09-05：新增 docs/37 修复与 Web 接口计划。运行时仍为 0.1.0.dev26，机器 Schema 仍为 3.26.0-draft1，未发布新版本。后续 Snapshot、scene、缓存、subject 映射与 API 均须独立冻结版本及旧产物兼容策略；历史原始事实和旧 run 保留。

- 2026-09-04：Schema 升级到 `3.26.0-draft1`、运行时升级到 `0.1.0.dev26`；新增 render compile requests、`render-ready-character-profiles-v1`、唯一 StateSegment 选择、active/provisional applicability、scope conflict gate、结构化 traits/warnings 与 canonical/raw provenance。纯代码构建，Provider 0。
- 2026-09-04：Schema 升级到 `3.25.0-draft1`、运行时升级到 `0.1.0.dev25`；新增 `document-character-label-review-projection-v1`、正交 label kind/stability、完整 review audit 与由最终 identity graph 派生的精简 actionable 队列。Registry 来源语义保持不可变，Provider 调用为 0。
- 2026-09-04：Schema 升级到 `3.24.0-draft1`、运行时升级到 `0.1.0.dev24`；appearance state artifact 升级 v5，在同人物/StateSegment/exact-attribute 内新增确定性关系图，并只从 equivalent 连通分量派生 normalized propositions。compatible/unclassified 保持独立，active applicability 与完整 true-conflict Gate 延后。
- 2026-09-04：Schema 升级到 `3.23.0-draft1`、运行时升级到 `0.1.0.dev23`；appearance state artifact 升级 v4，为 Grounded Transition 增加稳定 ID，并在同一产物内新增确定性 StateSegment、boundary provenance 与唯一 observed fact binding。active applicability 和语义关系保留给 072/074。
- 2026-09-02：Schema 升级到 `3.22.0-draft1`、运行时升级到 `0.1.0.dev22`；071 Grounding/状态物化升级 v3，新增 life 重置 form/scene、scene 段落行/章节关闭、非身体 form 过滤、单段连续且状态有序回填，以及保存模型输出的零调用重新 Grounding。
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
