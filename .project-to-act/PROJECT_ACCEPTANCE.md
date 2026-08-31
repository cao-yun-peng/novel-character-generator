# 项目验收

## 当前验收结论

设计基线、M1/N2/M2/N3、promotion、文档级事实汇总和跨 Chunk 身份运行时已建立。斗破真实 M3 19/19 完成：17 same、2 uncertain，生成 11 个全局人物、5 linked、6 singleton、2 review；36 条身份引用全部绝对 span 回放。人工检查未见明显错组，用户接受当前真实样本范围；同名不同人、different/cannot-link 和证据充分性不作一般化质量宣称，在真实失败案例出现时重开。

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
| 身份候选有界且同名不自动合并 | 通过（默认每节点最多 2 tasks；同名/字形变体/相似事实仅候选，只有共享同一文档 fact_hash 可确定性连接） |
| 身份证据严格 Grounding | 通过（严格/纯空白等价、非空白改写拒绝、跨 context 同 occurrence 去重和多 occurrence 歧义测试） |
| 全局人物注册表失败关闭 | 通过（same/alias、different/cannot-link、uncertain/unresolved、多值冲突保留、断点续跑单测；全 uncertain 端到端演练不按同名猜合并） |
| 斗破身份离线准备 | 通过（23 nodes、1 zero-fact exact、1 deterministic edge、19 pending tasks、每节点最多 2、Provider calls=0） |
| 真实 M3 身份模型执行 | 通过（19/19 最终成功；18 项缓存恢复、1 项提高预算后单独重试；模型输出/grounding/trace/registry 分离） |
| 真实 M3 身份引用 Grounding | 通过（36 条 grounded quote 全部绝对 span 回放；1 条多 occurrence 引用被隔离，其余唯一证据部分接受） |
| 真实 M3 身份模型质量 | 当前样本条件通过（五个 linked 组未见明显错人，用户接受当前结果）；不代表同名不同人、different/cannot-link 或一般化 precision 已验收，真实失败时重开 |
| 当前工作目录不再包含旧源码、旧测试、旧数据和旧文档 | 通过 |
| novel-characters 参考副本与固定上游 commit 一致 | 通过 |
| M1 运行时和提示词 | DeepSeek Provider、可恢复全文批处理和真实样本运行已完成；人工质量评测未完成 |
| DeepSeek Key 安全、json_schema、错误分类、重试与脱敏 trace | 通过（81 项总自动测试 + 真实 M1 样本 + 斗破 M2 18 tasks；含 IncompleteRead 恢复） |
| N2/M2/N3 运行时 | Chunk 局部链路、promotion、绝对 span 与重叠事实去重已实现并实跑；真实人工质量验收待完成 |
| 人物记忆 | 文档内身份运行时已实现；跨文档长期记忆和真实模型质量待后续 |

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

## 说明

本机仍有一个因 Windows ACL 无法移除的已忽略 `.pytest_cache/` 目录；其副本已移到仓库外备份。它不是源码、文档、依赖或新项目运行资产。

## 验收记录

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
