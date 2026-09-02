# 项目验收

## 当前验收结论

设计基线、M1/N2/M2/N3、promotion、文档事实、跨 Chunk 身份、局部确定性身份闭合和人物档案组装均已建立。斗罗 dev17 离线重放把有完整局部关系原文的“高大的身影”并入唐昊，最终 7 个全局人物、129 条已分配事实、130 个来源 occurrence、0 未绑定事实；无关系原文的看门青年仍保守未决。事实/证据/Chunk/身份边回放和 Schema 校验通过。模型质量仍与确定性系统验收分开，不对未覆盖的一般化精度作宣称。

## 验收标准

| 标准 | 状态 |
|---|---|
| 新流程契约存在且可阅读 | 通过 |
| 机器 Schema 通过 Draft 2020-12 校验 | 通过 |
| type/scope 约束和错误组合拒绝 | 通过（设计/Schema/运行时单测） |
| *女子 等 describe 后缀匹配顺序与归一 trace | 通过（设计/运行时单测） |
| 每个 exact 一次携带全部 describe 的 M2 肯定事实输出与 N3 消费结果 | 通过（Schema 3.9/运行时单测/斗破 18 个 exact 任务与 7 Chunk N3）；本样本 describe claim 为 0 |
| M1/M2 代码信封与实际模型输入输出隔离 | 通过（设计/Schema/运行时字段隔离测试） |
| 每个剩余 describe 单独进入 M2 并允许创建多个本地正式人物 | 通过（设计/Schema/运行时单测；真实模型质量待验收） |
| Promotion 单事实失败不连带删除安全人物事实 | 通过（部分/全失败/跨人物重叠单测；斗破青衫老者离线重放） |
| Promotion 歧义事实不猜 occurrence 且独立 review | 通过（review 显式记录 fact quote 与 2 个候选；两个原文片段均保留未分配） |
| Promotion 模型输出与 Grounding 策略解耦 | 通过（5/5 保存输出离线重放，Provider calls=0，来源 artifact hash 保留） |
| exact 称号边界与保守降级策略 | 通过（设计） |
| N2 relation_to_mention 与 evidence occurrence | 通过（设计/Schema/Chunk 局部运行时单测）；mention occurrence 字段按用户决定移除 |
| evidence 严格/纯空白等价 Grounding | 通过（raw quote/span 回填与非空白改写拒绝单测） |
| N2 exact evidence 优先去冗余 | 通过（全/部分重复、空块删除、collective、无 exact、hash、批次 trace/summary 单测；斗破离线重放） |
| collective quarantine | 通过（设计/Schema/运行时路由单测） |
| M2 模型无 ref/span/状态；代码用 fact_quote 回填来源 span | 通过（Schema 3.8/字段隔离/失败关闭测试；斗破 50/50 facts 严格匹配回填） |
| N3 非重叠独立消费与重叠冲突 | 通过（设计/Schema/运行时单测；斗破实跑无 describe claim，因此真实冲突样本待补） |
| task cache、pool/promotion guard 与原始 hash 规范 | 通过（稳定 task_cache_key、pool_hash、promotion_hash 与版本敏感测试）；持久缓存存储待接线 |
| 重叠分块与 complete/truncated 文档覆盖清单 | 通过（设计/Schema/运行时单测） |
| Chunk 局部 span → 文档绝对 span 与原文回放 | 通过（exact/promotion 单测、斗破 61/61 facts 与 evidence 回放） |
| 重叠 Chunk 人物事实安全去重与来源保留 | 通过（同结构同位置合并、不同位置/结构不合并单测；斗破 61→60，合并项保留两个来源） |
| 逐 quote hash 删除 | 通过（grounded packet v6/Schema/字段缺失测试；保留 document/chunk/packet/fact/audit hash） |
| 身份模型最小字段边界 | 通过（输入仅 current/candidate/bridge 原文与事实，输出仅 relation/label relation/evidence；ref/ID/span/hash/cache 字段扫描为 0） |
| 身份候选有界且同名不自动合并 | 通过（默认每节点最多 2 tasks；同名/字形变体/相似事实仅候选；确定性连接只来自共享同一文档 fact_hash 或满足完整局部共指契约的显式关系） |
| 身份证据严格 Grounding | 通过（严格/纯空白等价、非空白改写拒绝、跨 context 同 occurrence 去重和多 occurrence 歧义测试） |
| 残余 cluster-level 身份裁决接线 | 通过（普通 context/fact 不可作为身份证据；只允许所选候选 `relationship_context_quotes` 唯一 Grounding；支持 Provider 0 准备、断点续跑和 supplemental registry 重建） |
| 斗罗残余身份真实模型与证据域 | 通过（5/5 HTTP 200、4 same/1 different、8/8 文档和候选关系上下文回放、0 Grounding issue、缓存恢复 0 新调用） |
| 残余身份最终聚合关闭 | 通过（无向簇对去重、最多三轮固定点、最终关系覆盖和冲突失败关闭；斗罗唐三簇 2→1，男孩儿旧 unresolved 关闭，唯一剩余看门青年无关系证据且不创建调用） |
| 全局人物注册表失败关闭 | 通过（same/alias、different/cannot-link、uncertain/unresolved、多值冲突保留、断点续跑单测；全 uncertain 端到端演练不按同名猜合并） |
| 斗破身份离线准备 | 通过（23 nodes、1 zero-fact exact、1 deterministic edge、19 pending tasks、每节点最多 2、Provider calls=0） |
| 真实 M3 身份模型执行 | 通过（19/19 最终成功；18 项缓存恢复、1 项提高预算后单独重试；模型输出/grounding/trace/registry 分离） |
| 真实 M3 身份引用 Grounding | 通过（36 条 grounded quote 全部绝对 span 回放；1 条多 occurrence 引用被隔离，其余唯一证据部分接受） |
| 真实 M3 身份模型质量 | 当前样本条件通过（五个 linked 组未见明显错人，用户接受当前结果）；不代表同名不同人、different/cannot-link 或一般化 precision 已验收，真实失败时重开 |
| 文档人物档案确定性组装 | 通过（同文档 guard、完整 fact hash 重算、引用/quote/单一占用、Chunk hash 与绝对 span 回放；斗破 11 profiles、61 assigned、0 unassigned、62 occurrences、4 conflicts、2 review） |
| 当前工作目录不再包含旧源码、旧测试、旧数据和旧文档 | 通过 |
| novel-characters 参考副本与固定上游 commit 一致 | 通过 |
| M1 运行时和提示词 | DeepSeek Provider、可恢复全文批处理和真实样本运行已完成；人工质量评测未完成 |
| DeepSeek Key 安全、json_schema、错误分类、重试与脱敏 trace | 通过（81 项总自动测试 + 真实 M1 样本 + 斗破 M2 18 tasks；含 IncompleteRead 恢复） |
| N2/M2/N3 运行时 | Chunk 局部链路、promotion、绝对 span 与重叠事实去重已实现并实跑；真实人工质量验收待完成 |
| 人物记忆 | 文档内身份与结构化人物档案已实现；时间/场景状态、跨文档长期记忆和真实模型一般化质量待后续 |
| 局部确定性身份闭合 | 通过（同 Chunk、上下文交集、显式同位/命名/连续共指、逐字 span 回放；斗罗新增 1 edge，8→7 profiles，129 facts 保持；跨 Chunk、问句、无显式关系与 global unique name 不建边） |
| Post-link canonical fact groups | 通过（`document-character-fact-groups-v1`；斗罗 129 raw facts→109 groups、10 multi-member groups、20 collapsed members；129 fact/130 occurrence bindings 全保留，同 span 不同 attribute 不合并） |
| Appearance Scope / Variant | 待实现（life_stage/form_state/scene_state/persistence/transition，全部可反向引用 raw evidence） |
| 状态内语义关系与 true conflict | 待实现（只在同 scope、同规范属性、有效期重叠时判 true conflict；无法安全分类时保留 unclassified） |
| Label/Review 投影 | 待实现（大师为 title/stable；历史 resolved review 保留 audit，只有真未决进入 actionable queue） |
| Render-ready Profile Compiler | 待实现（按明确状态选择器编译；不得混合唐三生命阶段或素云涛形态；输出双层 provenance） |
| Stage 6 人工质量 Gate | 未通过（尚无冻结人工标注集、正式阈值和可复现 evaluator；专家主观评分不构成 Gate） |

## 证据索引

- `.project-to-act/tasks/PIPELINE-V3-SIMPLIFIED-039/evidence/`
- `.project-to-act/tasks/PROJECT-V3-CLEAN-START-040/evidence/`
- `.project-to-act/tasks/PIPELINE-MENTION-CLARITY-041/evidence/`
- `.project-to-act/tasks/MENTION-SUFFIX-RULE-042/evidence/`
- `.project-to-act/tasks/UPSTREAM-NOVEL-CHARACTERS-043/evidence/`
- `.project-to-act/tasks/PIPELINE-V3-REVIEW-HARDENING-044/evidence/`
- `.project-to-act/tasks/MODEL-BOUNDARY-BATCHED-M2-045/evidence/`
- `.project-to-act/tasks/REMAINING-DESCRIBE-PROMOTION-046/evidence/`
- `.project-to-act/tasks/M1-RUNTIME-FOUNDATION-047/evidence/`
- `.project-to-act/tasks/M1-DEEPSEEK-PROVIDER-048/evidence/`
- `.project-to-act/tasks/M1-DOULUO-LIVE-RUN-049/evidence/`
- `.project-to-act/tasks/M1-GROUNDING-SCOPE-051/evidence/`
- `.project-to-act/tasks/M1-DOUPO-LIVE-RUN-052/evidence/`
- `.project-to-act/tasks/N2-EXACT-PRECEDENCE-053/evidence/`
- `.project-to-act/tasks/M2-MINIMAL-FACT-SCHEMA-054/evidence/`
- `.project-to-act/tasks/M2-RUNTIME-FOUNDATION-055/evidence/`
- `.project-to-act/tasks/M2-DOUPO-LIVE-RUN-056/evidence/`
- `.project-to-act/tasks/N3-PROMOTION-DOUPO-RUN-057/evidence/`
- `.project-to-act/tasks/DOCUMENT-EVIDENCE-QUOTEHASH-058/evidence/`
- `.project-to-act/tasks/PROMOTION-PARTIAL-ACCEPTANCE-059/evidence/`
- `.project-to-act/tasks/CROSS-CHUNK-IDENTITY-060/evidence/`
- `.project-to-act/tasks/M3-DOUPO-LIVE-EVAL-061/evidence/`
- `.project-to-act/tasks/DOCUMENT-CHARACTER-PROFILES-062/evidence/`
- `.project-to-act/tasks/DOULUO-END-TO-END-063/evidence/`
- `.project-to-act/tasks/M3-IDENTITY-RESCUE-064/evidence/`
- `.project-to-act/tasks/M3-IDENTITY-RESCUE-LIVE-065/evidence/`
- `.project-to-act/tasks/M3-IDENTITY-FIXPOINT-066/evidence/`
- `.project-to-act/tasks/APPEARANCE-PROFILE-PLAN-067/evidence/`
- `.project-to-act/tasks/LOCAL-COREFERENCE-CLOSURE-068/evidence/`
- `.project-to-act/tasks/POST-LINK-FACT-GROUPS-069/evidence/`

## 说明

本机仍有一个因 Windows ACL 无法移除的已忽略 `.pytest_cache/` 目录；其副本已移到仓库外备份。它不是源码、文档、依赖或新项目运行资产。

## 验收记录

- 2026-09-02：`APPEARANCE-SCOPE-SCHEMA-070` 验收通过。新增 dev19/Schema 3.19 的 `document-character-appearance-scopes-v1`、构建器和 CLI；斗罗实际 19 章，相邻重复标题正确折叠，109/109 canonical facts 按原文顺序唯一分配。life/form/scene 全部保守为 unknown；persistence 分布为 stable 2、persistent_until_changed 13、scene 18、momentary 12、unknown 64。150 tests、compileall、Draft 2020-12 Schema/实例、diff check 和两套治理 validate 通过，Provider 0。本 Gate 不包含 transition 识别或模型质量验收。
- 2026-09-01：`POST-LINK-FACT-GROUPS-069` 验收通过。新增 dev18/Schema 3.18 的独立构建器、CLI 和 `same-character-span-structure-v1`；斗罗 129 raw facts 生成 109 groups，老杰克 26→14、素云涛 29→21，其余人物零折叠。129 source fact hashes、130 occurrences、109 fact quote/span 和 canonical IDs 全量验证；registry/profile 输入 hash 不变，重复输出 hash 稳定，Provider 0。146 tests、compileall、Draft 2020-12 Schema/实例、diff check 和两套治理 validate 通过。本 Gate 只证明结构分组，不包含 scope/语义归一，也不替代人工模型质量 Gate。
- 2026-09-01：`LOCAL-COREFERENCE-CLOSURE-068` 验收通过。`grounded-local-coreference-v1` 只在同 Chunk、双方上下文交集和逐字显式关系成立时建立 `describe -> exact` same edge；问句、否定、无关系陈述、跨 Chunk、篡改证据和 global unique name 均不建边。复用 63 条 M3 与 6 条 rescue grounded 决策零 Provider 重放，斗罗在 `[5591,5814)` 建立 `高大的身影 -> 唐昊`，8→7 profiles；129 facts、130 occurrences、1 unresolved（看门青年）、2 cannot-link、9 review、13 conflicts 保持。140 tests、compileall、Draft 2020-12 Schema/实例、6 个输出哈希稳定性、diff check 和治理 validate 通过。本 Gate 不替代人工模型质量评测。
- 2026-09-01：`APPEARANCE-PROFILE-PLAN-067` 规划验收通过。Evidence Layer 保持不可变，后续冻结为 local coreference closure、post-link fact groups、appearance states、语义关系、Label/Review 投影、render-ready compiler 和人工质量 Gate。Project-to-Act validate、新任务 JSON 解析和 diff check 退出码均为 0。本记录只验收规划一致性，不代表 068～075 任一运行时功能或质量 Gate 已通过。
- 2026-09-01：身份最终聚合关闭 Gate 通过。新增 `global-constrained-identity-v3`、`residual-cluster-adjudication-v2`、旧 grounded run 复用和最多三轮固定点。斗罗复用 5 条旧裁决，仅新增 1 次 DeepSeek 调用；模型以“小三……老杰克向唐三挥手”的 `[10205,10229)` 原文裁决两唐三簇 same/name_variant，Grounding issue 0。最终 8 global characters、唐三唯一、1 unresolved（看门青年，无关系原文）、2 cannot-link、129/129 assigned facts、130 occurrences；135 tests、compileall、两个 Draft 2020-12 实例和治理 validate 通过，缓存复跑新增调用 0。本 Gate 只证明已观察失败被关闭，不替代一般化模型质量评测。
- 2026-09-01：斗罗残余 cluster-level DeepSeek 实跑完成。联网后 5/5 成功，4 same/1 different、0 Grounding issue；8 条身份证据全部逐字回放且全部来自模型所选候选的 `relationship_context_quotes`。成功响应共 23,469 tokens；恢复运行 5/5 命中缓存、新调用 0。registry 从 12 人物/3 unresolved/1 cannot-link 变为 9人物/2 unresolved/2 cannot-link，129 facts 未丢失。模型和证据域 Gate 通过；因反向重复候选及 supplemental different 未清理旧 uncertain，最终聚合关闭 Gate 未通过。
- 2026-09-01：M3 残余 cluster-level 裁决接线完成。代码复用旧 M3 产物，只为残余项构建候选专属关系上下文；模型看不到 ref/ID/span/hash/cache，`identity_evidence_quotes` 只允许在所选候选 `relationship_context_quotes` 内唯一严格/纯空白等价 Grounding。斗罗离线准备得到 5 tasks、5 candidate options、10 relationship contexts、Provider 0；无支撑原文的看门青年保持 unresolved。128 项测试与 compileall 通过；真实 DeepSeek 补救调用未执行，不宣称该节点模型质量已验收。
- 2026-09-01：斗罗指定文件 dev13 全链路真实回归完成。输入 hash `8bcb7305...9741`，实际第1至19章/38,251 字符；M1 17/17、M2 32/32、N3 11/11、M3 63/63，最终 8 profiles、106 assigned/23 unassigned facts、9 conflicts、17 review、10 unresolved、1 cannot-link。首次真实 `different` 为 `大师`↔`战魂大师`，Grounding 引用分别支持20多岁俊朗与40至50岁，代码形成 cannot-link 而未误合并。118 tests、67 个 Draft 2020-12 实例、129/129 document/profile facts、130/130 source occurrences、105/105 identity evidence 回放通过。成功任务记录 123 次、426,561 tokens；不含失败/截断响应无法完整计量的计费量。本任务证明全链路和失败恢复，不代表模型一般化身份/外貌质量 Gate 通过，Stage 5 保持 `in_progress`。
- 2026-08-31：确定性人物档案组装完成。新增 v1 Schema、严格 `fact_hash` join、CLI 与失败关闭验证；斗破 registry/evidence 在 Provider 0 调用下生成 11 profiles、61/61 assigned facts、62 source occurrences、0 unassigned、4 possible conflicts、2 review。118 项测试、Draft 2020-12 实例、61 fact/62 evidence/62 Chunk 回放和 diff check 通过；本结论不替代上游模型人工质量 Gate。
- 2026-08-31：用户接受斗破当前身份结果，决定不为尚未出现的同名不同人和 `different`/`cannot-link` 提前扩展策略。身份功能按当前真实样本范围完成，但不声称一般化身份精度；真实错合并、明确 different/cannot-link 或无法安全聚类将触发功能重开。
- 2026-08-31：斗破真实 M3 批次完成但身份质量 Gate 保持未验收。受限网络预尝试 19 项瞬态失败；联网首轮 18/19 成功、1 项 HTTP 200 后因 4096 输出预算截断；8192 预算断点续跑只新增 1 次调用并完成。最终 17 same/2 uncertain/0 different，11 global characters、5 linked、6 singleton、2 review、0 unresolved/cannot-link。19 个成功 trace 脱敏，36 条身份证据 span 回放与 Schema 校验通过；成功响应累计 60,610 tokens。最终聚类在本样本未见明显错人，但同名不同人和证据语义充分性未覆盖。
- 2026-08-31：跨 Chunk 身份纵向切片完成但不构成身份质量 Gate。运行时新增完整节点目录、有界候选、M3 最小 Schema、严格 quote Grounding、cannot-link、冲突保留、全局人物注册表、可恢复批处理和追加式历史。斗破既有 N2/N3/文档事实离线准备得到 23 nodes（含 1 zero-fact exact）、1 deterministic edge、19 tasks、每节点最多 2、Provider calls=0；模型 payload 系统字段扫描 0，所有 context 绝对 span 原文回放通过。109 项测试与 Draft 2020-12 Schema/身份实例校验通过；真实 DeepSeek 身份判断未运行，Stage 5 保持 in_progress。
- 2026-08-31：Promotion 部分接受修复完成。旧策略因 `青衫` 两处 occurrence 将 `青衫老者` 连同唯一的 `浑浊的老眼` 一并拒绝；新策略只隔离歧义事实。5/5 保存模型输出离线重放、Provider 0 调用，promoted characters 4→5、facts 11→12，review issues 仍为 1。`青衫老者/浑浊的老眼` 文档 span `[7366,7371)` 已进入统一产物，两处 `青衫` 保留未分配且 review 明示候选数 2。98 项测试、5 个 promotion v6 与文档实例 Schema、62/62 绝对 span 回放、治理和 Lifecycle 校验通过；完整人工质量 Gate 仍未完成。
- 2026-08-31：文档级确定性汇总完成。N2 packet v6 删除逐条 quote/mention hash；M1 chunk 结果升级 v4，防止历史 v5 packet 被当作新格式续跑。斗破既有只读 M1/M2/N3 来源产生 `document-character-evidence.json`：61 输入事实、60 文档事实、49 exact、11 promoted、1 个重叠副本删除、61 source occurrences。唯一合并项为 `萧熏儿/微笑的小脸` 文档 span `[9130,9135)`，来源 Chunk 4/5 均保留。96 项测试、Draft 2020-12 实例 Schema、Project-to-Act、Lifecycle 和 diff 校验通过；不构成人工质量 Gate。
- 2026-08-31：N3 + promotion 纵向切片完成。N3 对斗破 7 Chunk 生成 18 target packets/50 exact facts 和 5 describe pools，0 consumption/0 conflict；5/5 DeepSeek promotion 成功，接受 4 promoted characters/11 exact-match facts，collective task 0。`青衫老者` 的 `青衫` 匹配两个 occurrence，代码拒绝人物并保留全部片段，summary 明示 review。断点恢复 5/5 且新调用 0；90 项测试和 35 个阶段对象实例 Schema 校验通过。不构成人工质量 Gate。
- 2026-08-31：斗破前5章 M2 exact attribution 实跑完成。旧 M1 原始输出确定性重放最新 N2 后得到 18 exact、5 individual describe、1 collective、57 bindings；18/18 M2 任务成功，50/50 模型事实严格逐字 Grounding，45 条 unique fact quote，0 issue/0 failure。首次执行因 `IncompleteRead` 在 5 个任务后中断，Provider 补齐 HTTPException 瞬态重试并恢复剩余 13 个。18 条 trace 脱敏、span 全量回放和 Schema 校验通过；81 项测试通过。未运行 N3/promotion，不构成人工质量 Gate。
- 2026-08-30：M2 双模式纵向切片完成。exact attribution 按 E 次调用组包全部 individual describe，target evidence 优先、describe occurrence 唯一绑定、空白等价恢复和非空白改写拒绝均有测试；promotion 支持稳定一对多建人、标签/事实唯一绑定、跨人物重叠复核和未分配残片保留。DeepSeek 使用任务自带 schema name；77 项测试通过，真实调用 0。Schema 3.8/runtime dev7；N3 与模型质量 Gate 未完成。
- 2026-08-30：M2 模型契约按用户决定收敛为肯定事实输出。归属模式只返回 `belongs_to_target`，事实仅含 `fact_quote/category/attribute/value`；所有 ref/span/状态/审计字段留在代码层，歧义绑定失败关闭。Schema 3.7 静态契约与字段隔离测试通过后方可作为 M2 实现基线；本记录不代表 M2 运行时或模型质量完成。
- 2026-08-30：N2 exact precedence 纵向切片完成。所有 grounded exact 的 raw quote 建索引并过滤所有 describe 同文 evidence，空块删除、hash 重算，独立 N2 trace 与 summary 计数可审计；57 项测试通过。斗破旧 M1 输出离线重放删除 37 bindings/13 blocks，未调用 Provider、未修改旧 runs；跨 Chunk N2 仍未完成。
- 2026-08-30：斗破苍穹前5章按 Schema 3.5/runtime dev5 完成 7/7 M1 Chunk；37 candidates/grounded mentions、94 evidence bindings、0 rejected，证据 span 回放 0 失败，1 个 collective 被识别。模型输出与 grounded packet 分开交付；单次实跑不构成人工质量 Gate。
- 2026-08-30：M1 Grounding/scope 契约升级完成。运行时与 Schema 移除 mention occurrence 数量和位置；evidence 严格失败后只容忍 Unicode 空白差异并回填 raw source quote；collective 隔离于单人物 promotion。51 项测试、Schema/台账/Lifecycle 验证通过；真实 Provider 调用 0，模型质量仍未验收。
- 2026-08-30：M1 输出诊断完成但不构成质量验收。发现输入缺第20章、quote whitespace 造成关键外貌 false negative、泛称 occurrence 未精确锚定、集合人物无类型、exact/describe 冲突、149 binding/80 unique quote 的指标混淆，以及续跑覆盖失败历史和 trace 配置不足。修复与人工回归集尚未实施。
- 2026-08-30：DeepSeek smoke 返回 HTTP 200；斗罗大陆前20章以 17 个重叠 Chunk 完成 17/17，断点续跑只重试唯一 `max_output_tokens` 截断块。输出 63 个 schema-valid candidates、60 个 grounded mentions、149 条 approved evidence；模型质量和跨 Chunk 去重仍待验收。
- 2026-08-30：DeepSeek Provider 自动测试通过：Key 不进入 repr/body/trace/异常，默认 HTTPS Responses API 与 `deepseek-v4-flash`，M1 schema 作为 `json_schema` 发送；401/402/422 立即失败，429/5xx/网络/空输出有界重试，不完整输出失败关闭；探测 CLI 在缺 Key 时网络前失败。测试使用 fake transport，真实调用 0，阶段 5 保持 `in_progress`。
- 2026-08-30：M1 运行时基础通过 23 项确定性测试：重叠分块与显式截断、原始 UTF-8 hash/Unicode code-point span、DTO 与 Schema 字段对齐、模型系统字段隔离、exact/describe/null 结构、后缀归一、原文 occurrence/relation 和 packet hash。未调用真实 Provider，不能据此宣称模型质量完成。
- 2026-08-30：Schema 3.4 promotion 样例通过；一个剩余 describe 可创建一个或多个 promoted 本地人物，多人物 claimed span 重叠会被代码拦截，稳定 promotion_index、未认领残片保留和系统字段隔离均已形成契约。运行时和真实模型效果仍未实现。
- 2026-08-30：Schema 3.3 模型边界样例通过；系统字段混入 M1/M2 payload 或模型输出会被拒绝，E 个 exact 各携带全部 D 个 describe 的批量样例通过。当时的“剩余池回到 exact 重跑”语义已被 `REMAINING-DESCRIBE-PROMOTION-046` 替代。
- 2026-08-30：技术审查和开源调研完成静态加固；Schema 3.2 行为样例通过，但跨字段 span 仲裁、缓存和分块覆盖仍需运行时代码验证。
- 2026-08-30：`novel-characters` 参考副本与上游 commit `4322897e6d2bdaf66365534fd40194360c75a85f` 目录级比对无差异，许可证和来源说明齐全；未接入运行时。
- 2026-08-30：用户确认 `*女子` 后缀匹配方案；规则、优先级、最小提及拆分和 N2 归一 trace 已冻结。
- 2026-08-30：exact/describe/null 与 describe 循环完成静态契约验收；运行时和模型效果仍未实现。
- 2026-08-30：完成干净重启。旧工程资产退出当前工作目录；新流程仍只有契约和 Schema，运行时未实现。
