# 项目进度

## 当前任务

| 任务 | 状态 | 结果 |
|---|---|---|
| PIPELINE-V3-SIMPLIFIED-039 | completed | 新流程契约和机器 Schema 已建立 |
| PROJECT-V3-CLEAN-START-040 | completed | 旧工程资产已退出当前工作目录，新项目只保留契约和最小治理文件 |
| PIPELINE-MENTION-CLARITY-041 | completed | exact/describe/null、exact×describe M2 和 N3 describe 消费循环已写入契约与 Schema |
| MENTION-SUFFIX-RULE-042 | completed | 用户确认使用 *女子 等泛称后缀规则归一 describe |
| UPSTREAM-NOVEL-CHARACTERS-043 | completed | 固定保存 novel-characters Skill 上游参考副本、许可证和精确 commit，不接入运行时 |
| PIPELINE-V3-REVIEW-HARDENING-044 | completed | 审查与调研边界已进入契约，Schema 升级到 3.2.0-draft1 |
| MODEL-BOUNDARY-BATCHED-M2-045 | completed | M1/M2 已统一四层模型边界；M2 改为每个 exact 一次携带全部 describe；Schema 升级到 3.3.0-draft1 |
| REMAINING-DESCRIBE-PROMOTION-046 | completed | 未被 exact 消费的 describe 单独进入 M2，一个池可建立多个 promoted 本地人物；Schema 升级到 3.4.0-draft1 |
| M1-RUNTIME-FOUNDATION-047 | completed | Python 0.1.0.dev1 骨架、重叠 Manifest、M1 DTO/提示词/Provider 边界、grounding 与 23 项测试已建立 |
| M1-DEEPSEEK-PROVIDER-048 | completed | DeepSeek Responses API/json_schema、脱敏 trace、有界重试、探测 CLI 与 43 项总测试已建立；未运行真实 API |
| M1-DOULUO-LIVE-RUN-049 | completed | DeepSeek smoke 成功；斗罗大陆前20章按 17 块完成 M1，交付模型输出、grounding、Manifest 与 summary；45 项测试通过 |
| M1-OUTPUT-DIAGNOSIS-050 | completed | 对真实 M1 输出完成错误分类：确认缺章输入、quote whitespace false negative、occurrence 锚点缺失、语义噪声、类型冲突和续跑审计失真；形成分级修复路线 |
| M1-GROUNDING-SCOPE-051 | completed | 按用户决策取消 mention occurrence 位置，增加 type/scope、纯空白等价 Grounding、raw quote 回填与 collective quarantine；51 项测试通过 |
| M1-DOUPO-LIVE-RUN-052 | completed | 斗破苍穹前5章按新契约完成 7/7 Chunk；分别交付模型输出与 grounded packet；37 mentions、94 evidence bindings、0 rejected |
| N2-EXACT-PRECEDENCE-053 | completed | exact raw evidence 优先过滤全部 describe；空块删除、hash 重算、独立 trace/summary；斗破离线重放删 37 bindings/13 blocks，57 项测试通过 |
| M2-MINIMAL-FACT-SCHEMA-054 | completed | M2 模型边界精简为肯定事实；60 项测试和 Schema/治理验证通过，运行时待实现 |
| M2-RUNTIME-FOUNDATION-055 | completed | M2 exact attribution 与 remaining-describe promotion 双模式运行时完成；Schema 3.8/runtime dev7，77 项测试通过，真实 Provider 调用 0 |
| M2-DOUPO-LIVE-RUN-056 | completed | 斗破前5章最新 N2 重放后完成 M2 exact attribution 18/18；50 模型事实全部 grounded，0 issue/0 failure；runtime dev8，81 项测试通过 |
| N3-PROMOTION-DOUPO-RUN-057 | completed | N3 7 Chunk/18 target/50 facts；5/5 promotion 成功，接受 4 人物/11 facts，`青衫` 重复 quote 进入 review；runtime dev9，90 项测试通过 |
| DOCUMENT-EVIDENCE-QUOTEHASH-058 | completed | N2 packet v6 删除逐 quote hash；文档绝对 span、回放和重叠安全去重完成；斗破 61→60 facts，96 项测试通过 |
| PROMOTION-PARTIAL-ACCEPTANCE-059 | completed | Promotion 事实级部分接受与离线重放完成；青衫老者安全事实恢复，歧义青衫仍 review；98 项测试通过 |
| CROSS-CHUNK-IDENTITY-060 | completed | 完整 local/promoted 节点、有界候选、M3 最小关系判断、严格 Grounding、cannot-link/N4 注册表、可恢复批处理与离线斗破准备完成；109 项测试通过，真实 Provider/身份质量 Gate 未运行 |
| M3-DOUPO-LIVE-EVAL-061 | completed | DeepSeek M3 19/19 完成；17 same/2 uncertain，11 个全局人物、5 linked、2 review；36 条身份引用全部回放，发现同名证据语义充分性和失败历史覆盖缺口 |
| DOCUMENT-CHARACTER-PROFILES-062 | completed | Schema/CLI/严格 join 与失败路径完成；斗破 11 profiles、61 assigned/0 unassigned facts、62 occurrences、4 conflicts、2 review；118 项测试，Provider 0 |
| DOULUO-END-TO-END-063 | completed | 全链路贯通：M1 17/17、M2 32/32、N3 11/11、M3 63/63；最终 8 profiles、106 assigned/23 unassigned facts、17 review、10 unresolved、1 cannot-link |
| M3-IDENTITY-RESCUE-064 | completed | 全局聚合/bridge/singleton 修复及残余 cluster-level 裁决已接线；斗罗离线得到 5 个有关系原文的任务，Provider 0 |
| M3-IDENTITY-RESCUE-LIVE-065 | completed | DeepSeek 残余裁决 5/5：4 same/1 different、8/8 关系证据回放；发现两项确定性聚合收尾缺口 |
| M3-IDENTITY-FIXPOINT-066 | completed | 无向簇对去重、有效关系覆盖和三轮上限固定点完成；复用旧 5 条裁决只新增 1 调用，斗罗唐三唯一化、男孩儿旧 unresolved 关闭，最终 8 profiles/129 facts |
| APPEARANCE-PROFILE-PLAN-067 | completed | 冻结 Evidence Layer 后的三层产物、068～075 开发顺序、失败关闭规则与 Stage 6 人工质量 Gate |
| LOCAL-COREFERENCE-CLOSURE-068 | completed | `grounded-local-coreference-v1` 完成；斗罗新增 1 条可回放边，8→7 profiles，129 facts/130 occurrences 保持，Provider 0 |
| POST-LINK-FACT-GROUPS-069 | completed | dev18 独立 Schema/CLI 与失败关闭完成；斗罗 129 raw facts→109 groups，129 fact/130 occurrence bindings 零丢失，Provider 0 |
| APPEARANCE-SCOPE-SCHEMA-070 | completed | dev19 最小扁平 Schema/CLI 完成；实际 19 章、109/109 facts 唯一排序分配，life/form/scene 保守 unknown，Provider 0 |
| APPEARANCE-STATE-TRANSITIONS-071 | completed | dev22 DeepSeek 17/17；10 model events→6 grounded/4 隔离，life 28/form 7/scene 1，已关闭已知传播与证据问题 |
| APPEARANCE-STATE-SEGMENTS-0715 | completed | dev23 在同一 appearance-state artifact 内物化 7 人物/14 StateSegments；109/109 facts 唯一 observed binding，Provider 0 |
| APPEARANCE-SEMANTIC-RELATIONS-072 | completed | dev24 生成 37 relations（7 equivalent/5 compatible/25 unclassified）与 103 propositions；只合并 equivalent，新增语义 Provider 0 |
| LABEL-REVIEW-PROJECTION-073 | planned | 修正 title 语义并拆分 audit 与 actionable review 视图 |
| RENDER-PROFILE-COMPILER-074 | planned | 按时期/形态/场景编译可生图的结构化人物卡，保留双层 provenance |
| UPSTREAM-HUMAN-EVAL-GATE-075 | planned | 建立 M1/M2/promotion 及新增状态层的正式人工标注评测和 Stage 6 Gate |

## 阻塞项

- 真实 API 链路已验证，但 M1 模型质量尚未通过人工标注集评测。
- 身份层当前无阻塞；同名不同人、`different`/`cannot-link` 和证据充分性属于已知覆盖缺口，按用户决定等真实失败案例出现后重开，而非阻塞下一阶段。

## 下一步

1. 实现 `LABEL-REVIEW-PROJECTION-073`：将 mention 的 exact/describe 与 `label_kind`、`label_stability` 解耦，并把历史 audit 与当前 actionable review 分开。
2. 为 074 准备 active applicability：根据 persistence、transition 和选择器派生事实跨 segment 的有效范围，不复用 `observed_fact_ids`。
3. 只有 applicability 证明同 scope、同属性的事实有效期重叠后，才允许把 072 的 unclassified 候选升级为 true conflict；模型不得读取或输出内部 ID、hash、span、解释或置信度。
4. 075 的标注规范和 evaluator 继续准备；Stage 6 前完成 M1/M2/promotion 正式人工质量 Gate，不以专家评分或确定性档案成功替代。
5. 自然语言人物总结、图像提示词和视觉验收继续留在结构化 Profile Compiler 稳定之后。

## 进度历史

- 2026-09-04：`APPEARANCE-SEMANTIC-RELATIONS-072` 确定性 baseline 完成。dev24/v5 只在同人物、同 StateSegment、同 exact attribute 内生成关系；相等值为 equivalent，安全子串为有方向的 compatible，其余保留 unclassified，再只从 equivalent 连通分量生成 proposition。斗罗 109 observations 得到 37 relations（7/5/25）和 103 propositions；17/17 保存输出离线恢复，新增 Provider 0，重复 artifact SHA-256 一致。171 tests、13 subtests、compileall、Draft 2020-12 真实实例、diff 与治理校验通过。active applicability、完整 true-conflict 判定和 075 人工 Gate 不在本次验收内。
- 2026-09-04：`APPEARANCE-STATE-SEGMENTS-0715` 完成。dev23/v4 为 grounded transitions 生成稳定 ID，并在现有 appearance-state artifact 中物化 7 个人物的 14 个连续 StateSegments；109/109 canonical facts 各自唯一进入一个 `observed_fact_ids`，active applicability 明确推迟到 072/074。斗罗 17/17 保存模型输出离线恢复，新增 Provider 0，重复 state artifact hash 一致。165 tests、13 subtests、compileall、Draft 2020-12 真实实例、diff 与治理校验通过。
- 2026-09-02：`APPEARANCE-STATE-TRANSITIONS-071` 完成。dev22 复用原 M1 17 Chunk，模型 payload 仍只有 characters/name/aliases/text；17/17 得到 10 events，代码接受 6 个连续 Grounded transitions、隔离 4 个改写状态。状态物化为 life 28/form 7/scene 1；life 重置 form/scene，scene 在段落行或章节关闭，蓝银草等外物不进入 form。保存模型输出可零调用重新 Grounding，最终重放新增 Provider 0。160 tests、13 subtests、Schema/实例、compileall、diff 与治理校验通过；不替代 075 人工 Gate。
- 2026-09-02：071 完成首次真实 DeepSeek 执行。用户明确授权发送 17 个原 Chunk；首次 15 成功、2 个 max_output_tokens，8192 预算仅重试 2 个后 17/17 完成。得到 8 model events、7 grounded transitions、1 review，7/7 span 回放。准确找回素云涛退出武魂附体；进入附体因模型拼接不连续段落被拒绝。实跑同时暴露 scene/form 未正确关闭、蓝银草外物状态误入人物 form、转世 after 证据不足，因此任务和质量 Gate 保持 in_progress。
- 2026-09-02：用户要求 071 不重新切 19 个窗口，而复用上游原 17 个 Chunk 及其身份元数据。实现已调整为读取并验证 M1 Manifest，要求 Chunk id/hash/span 与原文完整回放；以 local node 的 `chunk_id` 连接最终人物簇，17/17 Chunk 均生成已绑定人物表。模型 payload 仍只有 characters/name/aliases/text，Chunk 元数据只在代码信封。
- 2026-09-02：`APPEARANCE-SCOPE-SCHEMA-070` 完成。新增 `document-character-appearance-scopes-v1`、确定性章节解析/assignment 构建器和 CLI；斗罗实际 19 章、109/109 canonical facts 唯一分配，life/form/scene 不做词表猜测而全为 unknown，persistence 仅投影 stable 2、persistent_until_changed 13、scene 18、momentary 12、unknown 64。150 tests、Schema/实例、compileall、diff 与治理校验通过，Provider 0。
- 2026-09-02：用户确认 071 不应让模型重复识别人名。规划新增窗口人物表：代码以既有 identity/context/evidence 与窗口交集选择相关人物，只发送 canonical name 和必要 aliases；模型从给定人物中选择 transition 主体，内部 character_id 与唯一绑定仍由信封回填。无法安全列入或同名歧义时进入 review。
- 2026-09-01：用户指出基于人物标签和已知状态词召回 071 窗口会漏掉大量未知表达。071 规划改为源文档有重叠完整扫描：代码只做无语义过滤的切窗与位置保留，模型负责发现窗口内所有人物状态事件；事实锚点/词表降为补充检查，不再是模型入口。输出仍执行逐字 Grounding、身份绑定和失败关闭。
- 2026-09-01：用户收紧 070～072 契约：模型上下文和输出只保留语义判断必需字段，chunk/document/internal ID、span、hash、排序、绑定和 provenance 均由代码信封处理；新 Schema 默认扁平、少层级，字段必须有明确消费方或验证用途。071/072 可使用受约束单次模型节点，但不引入 Agent 循环，也不让模型承担 Grounding 或状态物化。
- 2026-09-01：`POST-LINK-FACT-GROUPS-069` 完成。新增 `document-character-fact-groups-v1` 与 `same-character-span-structure-v1`，严格按 `character_id + span + category + attribute + value` 生成稳定 canonical ID；每个 occurrence 绑定 raw fact hash 与原数组索引。斗罗 129 raw facts→109 groups，10 个 multi-member groups 折叠 20 个成员；老杰克 26→14、素云涛 29→21，其余人物零折叠。129 fact/130 occurrence bindings 全量反向回放，输入 hash 不变、重复输出 hash 稳定，Provider 0。146 tests、Draft 2020-12 Schema/实例、compileall、diff 和两套治理校验通过；Stage 5 保持 in_progress。
- 2026-09-01：`LOCAL-COREFERENCE-CLOSURE-068` 完成。新增 `grounded-local-coreference-v1`：仅在同 Chunk、双方上下文交集和逐字显式关系同时成立时建立 `describe -> exact` deterministic same edge，问句、否定和纯姓名共现拒绝，全局唯一姓名不自动 join，cannot-link 继续失败关闭。复用 dev16 的 63 条 M3 与 6 条 rescue grounded 决策离线重放，`高大的身影 -> 中年男子 -> 这就是唐昊` 在 `[5591,5814)` 建边；斗罗 global characters/profiles 8→7，129 facts、130 occurrences、1 unresolved（看门青年）、2 cannot-link、9 review 保持，Provider calls=0。140 tests、Draft 2020-12 Schema/实例、compileall、diff 和治理校验通过。
- 2026-09-01：`APPEARANCE-PROFILE-PLAN-067` 完成。根据 dev16 复核把后续路线冻结为 068～075：局部确定性身份闭合、post-link fact groups、life/form/scene 状态层、transition、scope 内语义关系、Label/Review 投影、render-ready compiler 和 Stage 6 人工质量 Gate。明确 raw evidence 不删除、全局唯一姓名不自动 join、去重包含 attribute 与 scope、历史 review 只做 actionable 投影。规划任务未修改运行时代码、Provider 调用 0。
- 2026-09-01：`M3-IDENTITY-FIXPOINT-066` 完成。`global-constrained-identity-v3` 让最终 same/different 关闭历史 uncertain，same/different 冲突保守 review；`residual-cluster-adjudication-v2` 对无向簇对去重并最多三轮重建到固定点。斗罗复用 dev15 的 5 条 grounded 裁决，只新增 1 次 DeepSeek 调用（same/name_variant，原文 `[10205,10229)` exact 回放），global characters 9→8，唐三/小三唯一化为 16 members/39 facts，男孩儿旧 unresolved 关闭。最终仅看门青年因无关系原文保持 unresolved；8 profiles、129 assigned facts、0 unassigned。135 tests、Schema 实例、compileall 和治理验证通过，缓存复跑新调用 0。
- 2026-09-01：`M3-IDENTITY-RESCUE-LIVE-065` 完成真实 DeepSeek 执行。5/5 HTTP 200，4 same/1 different、0 Grounding issue，8/8 身份引用同时通过文档 span 回放和所选候选 `relationship_context_quotes` 证据域检查；总计 23,469 tokens，第二次运行 5/5 缓存恢复且新增调用 0。registry 12→9 人物、3→2 unresolved、1→2 cannot-link、129 facts 保持。真实运行暴露两项代码收尾：反向重复唐三任务导致单轮后仍有两个唐三簇；男孩儿 different 已形成 cannot-link 但旧 uncertain 仍残留 unresolved。
- 2026-09-01：`M3-IDENTITY-RESCUE-064` 完成。新增 cluster-level 残余裁决输入/动态输出 Schema、候选专属关系上下文、严格证据域 Grounding、可恢复 DeepSeek 批处理和 supplemental registry 重建。普通 context/fact 只能辅助理解；身份证据只能从所选候选的 `relationship_context_quotes` 逐字取得。斗罗旧 M3 产物离线生成 5 tasks/5 candidates/10 relationship contexts，Provider 0；看门青年因无支撑原文不调用。128 tests 与 compileall 通过；真实补救调用留作独立评测。
- 2026-09-01：`M3-IDENTITY-RESCUE-064` 第一轮完成代码加固。斗罗 5 个 multiple 被确认是顺序 union 假失败；新 N4 全局 same 图在 cannot-link 下离线重放旧决策，bound nodes 33→43、unresolved 10→3、appearance refs 106→129，23 条事实不再丢失，cannot-link 仍为 1。新 bridge 覆盖唐三转生过渡，显式介绍召回新增 `素云涛`→`年轻人`，新准备 64 tasks；122 tests 通过，Provider 0。残余 cluster-level 裁决尚待接线。
- 2026-09-01：`DOULUO-END-TO-END-063` 全链路完成。M1 17/17、M2 32/32、N3 11/11、M3 63/63；130 个 Chunk facts 安全汇总为 129 个文档 facts，最终 8 profiles、106 assigned/23 unassigned facts、130 occurrences、9 conflicts、17 review、10 unresolved、1 cannot-link。首次真实 `different` 为 `大师`↔`战魂大师`，代码保留 20多岁/俊朗与40至50岁两组互斥证据并禁止合并。最终成功任务记录 123 次/426,561 tokens；118 tests、67 个 Schema 实例和事实/来源/身份证据全量回放通过。Stage 5 保持 in_progress，不替代人工质量 Gate。
- 2026-09-01：用户确认 DeepSeek 已充值，`DOULUO-END-TO-END-063` 解除 HTTP 402 阻塞；继续从 N3 8/11 缓存恢复，只重试剩余 3 项。
- 2026-09-01：斗罗全链路 M1 完成 17/17（64 candidate、46 grounded mentions、97 approved evidence、0 rejected）；M2 完成 32/32（84 model facts、84 grounded facts、1 review、0 failure）。N3 完成并缓存 8/11（8 promoted characters、42 grounded facts），两项网络重试耗尽后第三项返回 DeepSeek HTTP 402/余额不足，任务按可恢复语义暂停，未生成部分 document evidence，也未启动 M3。
- 2026-08-31：完成 `document-character-profiles-v1` 和 CLI。构建器验证 registry/evidence 同文档、完整事实 hash、Chunk hash、事实/evidence 绝对 span、引用一致性和单一人物占用；零事实人物与未绑定事实保留。斗破离线生成 11 profiles、61/61 assigned facts、62 occurrences、0 unassigned、4 conflicts、2 review；118 tests、Schema 与全量回放通过，Provider calls=0。
- 2026-08-31：用户确认斗破当前身份结果可接受；同名不同人、`different`/`cannot-link` 不再作为当前阻塞，未来以真实失败案例触发重开和回归。F-NEW-IDENTITY-006 按当前范围完成，下一阶段转向确定性人物档案组装。
- 2026-08-31：斗破前 5 章真实 M3 运行完成。沙箱内预尝试因网络限制 19 项失败且未获得 HTTP 成功；允许联网后首轮 18/19 成功，1 项因 4096 max output 截断；提高到 8192 后恢复 18 项、仅重试 1 项并完成。最终 17 same/2 uncertain/0 different，11 global characters、5 linked、6 singleton、2 review、0 unresolved/cannot-link。36 条身份证据绝对 span 全部回放；成功 trace 汇总 60,610 tokens。人工检查未见明显错组，但确认 same 引用常只是两个上下文分别出现同名，不能替代同名不同人评测。
- 2026-08-31：完成跨 Chunk 身份纵向切片。新增完整 local/promoted 节点目录、有界候选、最小 M3 三态模型边界、严格/纯空白等价身份证据 Grounding、cannot-link、冲突保留、全局注册表和可恢复批处理。斗破现有 N2/N3/文档事实零 Provider 准备得到 23 nodes（含 1 个零事实 exact）、1 deterministic edge、19 tasks，每节点最多 2 个；模型输入系统字段扫描为 0，109 项测试与 Draft 2020-12 实例验证通过。Stage 5 保持 in_progress，真实身份模型质量未评测。
- 2026-08-31：根据明确评测失败实现 promotion 事实级部分接受。唯一事实不再被同人物的歧义事实连带删除；歧义项显式记录 character/fact index、fact quote 与候选 occurrence 数，并保留全部未分配片段。新增无 Provider 的保存模型输出重放 CLI。斗破 5 个旧模型输出离线重放后 promoted characters 4→5、facts 11→12；`青衫老者/浑浊的老眼` 进入文档事实 `[7366,7371)`，两处 `青衫` 仍 review。统一文档事实 60→61；98 项测试、62/62 span 回放和 Schema 校验通过。
- 2026-08-31：实现 `document-character-evidence-v1` 确定性汇总和 CLI。所有事实/evidence 以 `chunk_start + local_span` 换算并逐字回放；只对同来源、同人物标签、同文档位置、同原文和同结构的重叠副本去重，保留全部 source occurrences。斗破 61 条输入事实得到 60 条文档事实（49 exact、11 promoted），`萧熏儿/微笑的小脸` 的两个重叠 Chunk 来源合并为一条；96 项测试、实例 Schema、治理和 Lifecycle 校验通过。N2 packet 升到 v6，取消逐 quote hash；Stage 5 仍因人工质量 Gate 未完成而保持 `in_progress`。
- 2026-08-31：实现 N3 span 仲裁、冲突隔离、剩余池重建及可恢复 promotion 批处理/CLI。斗破 7 Chunk 汇总 18 target/50 exact facts、5 describe pools、0 consumption/0 conflict；5/5 promotion 成功，接受 4 人物/11 facts，`青衫` 因两个 occurrence 进入 review 并保留原片段；90 项测试和 Schema 实例校验通过，实跑不代表人工质量 Gate。
- 2026-08-31：斗破前5章从旧 M1 model output 重放最新 N2（18 exact、5 individual describe、1 collective、57 bindings），完成 DeepSeek M2 exact attribution 18/18；50 条模型事实全部严格逐字 Grounding，45 条 unique quote，0 歧义/越界。首次执行 5 个任务后遭遇 `IncompleteRead`，补齐瞬态重试并恢复完成剩余 13 个；未运行 N3/promotion，实跑不代表人工质量 Gate。
- 2026-08-30：完成 M2 双模式运行时：E 个 exact 各生成一次携带全部 D 个 individual describe 的结构化任务；代码以统一严格/纯空白等价规则回填事实来源，describe 歧义失败关闭；每个 remaining describe 可稳定 promotion 一到多个人物并拦截跨人物重叠。Schema 3.8、runtime dev7，77 项测试通过，未调用真实 Provider；N3 未实现。
- 2026-08-30：按用户决定将 M2 模型输入输出精简为无 ref/span/状态的肯定事实；模型只返回 `belongs_to_target` 下的 `fact_quote/category/attribute/value`，代码负责唯一绑定、归并、冲突和 describe 消费；Schema 目标 3.7，运行时尚未实现。
- 2026-08-30：实现 N2 `exact-evidence-precedence-v1`；Grounding 后 exact 对同文 describe evidence 优先，空 describe block 删除，独立 trace 与 summary 计数落盘；Schema 3.6/runtime dev6，斗破离线重放 94→57 bindings，57 项测试通过。
- 2026-08-30：斗破苍穹前5章完成新契约真实回归；修复 CLI CRLF 归一化并升至 dev5，8192 预算断点续跑后 7/7 Chunk 成功，37 mentions、94 evidence bindings、1 collective、0 rejected；52 项测试通过。
- 2026-08-30：按用户确认的简化边界移除 mention occurrence 数量/位置，M1 增加 `mention_scope`；Grounding 只容忍 Unicode 空白差异并回填 raw source quote，collective 进入 quarantine；契约 3.5、运行时 dev4，51 项测试通过，未调用真实 Provider。
- 2026-08-30：复核真实 M1 输出并对照 `develop-ai-agents` 与上游 `novel-characters`；确认文件实际仅 1–19 章、149 为 evidence bindings 而非独立引文、49/60 mention 块缺 occurrence-specific 锚点、reasoning 占 output 92.4%，并冻结先修确定性层再建回归集的路线。
- 2026-08-30：DeepSeek 真实 smoke 成功；`斗罗大陆前20章` 以 2,500/250 分块策略完成 17/17 M1 Chunk，得到 63 个候选、60 个 grounded mentions 和 149 条已定位证据；新增可恢复批处理器，总计 45 项测试通过。
- 2026-08-30：建立 DeepSeek Responses API Provider，默认 `deepseek-v4-flash` + `json_schema`；实现 HTTPS/环境配置、脱敏 trace、429/5xx/网络错误有界重试、非瞬态失败关闭和显式探测 CLI，总计 43 项测试通过，真实 API 调用为 0。
- 2026-08-30：建立 Python `0.1.0.dev1` M1 运行时基础；Provider 只接收 `chunk_text`，输出经严格字段校验、Chunk 信封回绑和 N2 grounding，23 项确定性测试通过。
- 2026-08-30：用户纠正剩余 describe 的语义：N3 后不再回给 exact，而是每个剩余 describe 单独进入 M2，并允许按剩余证据拆成多个正式本地人物。
- 2026-08-30：用户确认所有模型阶段都应隔离系统字段；M1/M2 改为代码信封、最小模型输入、最小模型输出和代码回填四层，M2 调用粒度改为每个 exact 一次携带全部 describe。
- 2026-08-30：结合技术审查与开源调研补齐 exact 称号边界、evidence relation、四层 span、非重叠仲裁、pair 缓存、原始 hash、重叠分块和显式截断；Schema 升级到 3.2.0-draft1。
- 2026-08-30：按用户要求将 `eternityspring/shuohao-skills` 的 `novel-characters` 固定在 commit `4322897e6d2bdaf66365534fd40194360c75a85f`，作为只读对照资料；当前 M1 优先级和 V3 契约不变。
- 2026-08-30：确认 `红衣女子` 可通过 `*女子` 后缀规则归一为 describe；实现约定使用 `endswith`，明确名称优先拆成最小 exact 提及。
- 2026-08-30：用户新增 exact/describe/null 规则；所有 describe 与所有 exact 组合进入 M2，N3 唯一认领后消费 describe 片段，剩余片段继续细分。
- 2026-08-30：用户确认当前分支不保留旧代码和旧文档，项目按新流程完全重新开始。
