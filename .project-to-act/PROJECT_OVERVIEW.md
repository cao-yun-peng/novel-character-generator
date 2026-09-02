# 项目总览

## 基本信息

- 项目：Novel Character Generator
- 分支：`v3-simplified-character-evidence`
- 状态：M1/N2/M2/N3/promotion、文档事实汇总、跨 Chunk 身份、局部确定性身份闭合、人物档案组装和 post-link canonical fact groups 均已建立；斗罗 dev18 将 129 raw facts 解释为 109 个结构 groups
- 工作区：`E:\project\agent\novel-character-generator`
- Agent 生命周期：阶段 5（具体功能与纵向切片开发）`in_progress`，revision 2，风险 L1

## 项目目标

从中文小说 Chunk 中提取人物外貌事实，并确保每条进入后续流程的事实都能追溯到原文证据和对应的局部候选人物。

## 范围

- 文档输入：版本化重叠分块、来源绝对位置和显式 complete/truncated 覆盖清单
- 模型边界：所有模型阶段统一拆分代码编排信封、最小模型输入、最小模型输出和代码回填验证
- M1：模型只读取 chunk_text 并输出 type/scope 候选与逐字证据；Chunk 身份由代码信封绑定
- N2：严格验证 mention；evidence 可做纯空白等价恢复并记录 provenance；所有 exact 对同文 describe evidence 优先，describe 空块删除；不保存 mention 位置
- M2：第一模式为每个 individual exact 一次携带全部 individual describe 原文，只返回肯定属于 target 的 `fact_quote/category/attribute/value`；第二模式为每个剩余 individual describe 单独结合 chunk_text 拆出一个或多个正式本地人物；所有 ref/span/状态由代码保留和回填，collective 隔离
- N3：代码安全且唯一绑定 `fact_quote` 后，以 Chunk 字符 span 执行非重叠独立消费、冲突保留，并把未认领 describe 路由到独立建人模式
- 文档汇总：以 `chunk_start + local_span` 换算绝对 span，逐字回放事实与 evidence，按人物标签/来源/文档位置/事实结构安全去重并保留全部来源 occurrence
- 人物身份：exact/promoted 局部引用进入完整节点目录；代码有界召回候选，M3 只返回 same/different/uncertain 与逐字身份证据，N4 Grounding 后生成全局 `character_id`、成员 ref、fact 引用、cannot-link、冲突和 review

## 当前非目标

- 旧版代码、提示词、测试、评测数据和运行结果复用
- 代词消解、跨文档长期人物记忆和自然语言/视觉人物画像
- 数据库、Web API、图像生成和生产发布
- 在尚无真实失败案例时预先扩展同名不同人、`different`/`cannot-link` 的复杂策略

## 当前焦点

指定斗罗大陆文件的 dev13 全链路真实回归已贯通到最终 profiles；文件实际只有第1至19章，完整覆盖结论只针对该文件的 38,251 字符。身份层已针对真实失败完成有效关系覆盖、无向候选去重、有界固定点和局部确定性闭合。post-link 结构层已在不修改 raw profile 的前提下把 129 facts 归为 109 groups，129 fact/130 occurrence provenance 全保留。当前焦点转向章节位置、life/form/scene scope、persistence 和状态选择器，然后继续 transition、render-ready Profile Compiler 及上游人工质量评测。

## 最新路线决定

- `DEC-20260902-REUSE-SOURCE-CHUNKS-071`：用户要求 071 直接复用原 M1 Manifest 的 17 个重叠 Chunk，不重新生成独立窗口。代码验证原 Chunk id/hash/span/覆盖，并以 local/promoted node 的 `chunk_id` 将该 Chunk 已识别且已绑定到最终人物簇的人物加入人物表。Chunk 元数据只存在代码信封，不进入模型；模型输入仍为 `characters: [{name, aliases}] + text`。跨 Chunk 重复 transition 在 Grounding 后由代码合并。
- `DEC-20260902-WINDOW-CHARACTER-ROSTER-071`：用户确认 071 模型输入应显式提供上游身份层已经识别的人物，避免模型在 transition discovery 中重复做人名识别。最终实现以原 M1 `chunk_id` 连接该 Chunk 下的 local/promoted nodes，再投影到最终人物簇；只发送 canonical label 及该 Chunk 必要 aliases，不发送 character_id、ref、span、hash 或全局人物档案。模型事件的 `character` 必须从人物表 canonical label 中选择，代码信封据此回填唯一 character_id。
- `DEC-20260901-FULL-COVERAGE-TRANSITION-SCAN-071`：用户指出“appearance fact 锚点 + 人物标签/状态词”会把 071 限制为已知表达式规则，无法覆盖隐式、跨句、代词承接和未知措辞的状态变化。071 因此复用原 M1 Manifest 的 17 个重叠 Chunk 执行完整语义扫描；appearance facts 和触发词不决定哪些文本进入模型。模型只读取 Chunk 原文及已绑定人物表并输出最小事件语义与逐字证据；代码负责 Chunk 元数据验证、绝对 span、身份绑定、跨 Chunk 去重、状态物化和失败关闭。
- `DEC-20260901-MINIMAL-MODEL-SCHEMA-070-072`：用户确认 070～072 必须继续采用“代码信封、最小模型输入、最小模型输出、代码回填”边界。模型只接收完成当前语义判断所必需的人物标签、原文窗口和少量候选事实文本，不读取或输出 chunk/document/internal ID、span、hash、来源 occurrence、排序或状态机字段；这些全部由代码保存、绑定、换算和验证。模型输出 Schema 优先使用扁平短结构，不返回解释、置信度或重复的输入元数据。新派生产物中的每个字段都必须有明确下游消费方或验证用途；无消费方的 hash、包装层和多层嵌套不加入契约。071/072 允许受约束的单次模型语义节点，但 Grounding、身份绑定、状态物化、provenance 和失败关闭仍由代码负责。
- `DEC-20260901-POST-LINK-FACT-GROUPS-069`：`fact_hash` 继续标识不可变 raw fact；`canonical_fact_id` 使用独立命名空间，只按 `character_id + document_fact_span + category + attribute + value` 生成。每个 group 必须保存全部 source fact hashes，并把每个 occurrence 绑定回 raw fact hash 与原数组索引。不同 attribute/span/value 不合并；语义归一和状态判断推迟到有 scope 的 072。
- `DEC-20260901-LOCAL-COREFERENCE-CLOSURE-068`：局部确定性 same edge 只允许 `describe -> exact`，并要求同 Chunk、双方上下文交集、显式同位/示指命名/连续共指关系以及可从文档和双方上下文逐字回放的证据。问句、否定、纯姓名共现和全局唯一姓名不建立边；cannot-link 仍为硬约束。保存的 M3/rescue grounded 决策可在零 Provider 调用下重放并重建 registry/profile。
- `DEC-20260901-APPEARANCE-PROFILE-PLAN-067`：Evidence Layer 的 raw facts、span、来源 occurrence、冲突和历史 review 保持不可变；不使用 `proper name + global unique` 自动建立身份关系。后续依次实现局部确定性身份闭合、post-link 结构 fact groups、`life_stage/form_state/scene_state/persistence/transition` 状态层、状态内语义关系、Label/Review 投影和按状态选择器编译的 render-ready profile。去重分为结构分组与 scope 内语义归一两步，canonical facts 必须反向引用全部 raw facts。M1/M2/promotion 人工标注评测是 Stage 6 前的正式 Gate，专家主观评分不登记为 Gate。
- `DEC-20260901-M3-IDENTITY-FIXPOINT-066`：残余裁决按无向人物簇对生成，避免 A→B/B→A 重复；每轮 grounded 后重建 registry 并重新产生剩余任务，默认最多三轮，无决定性变化提前停止。当前 unresolved 由最终 union/cannot-link 图派生，历史 uncertain 被 supplemental same/different 消解后只留审计记录；same/different 冲突禁止合并并进入 review。可复用旧 rescue grounded 决策，避免重复模型费用。旧来源候选策略版本保持真实记录，档案连接器只对已知 v1/v2 做显式兼容。
- `DEC-20260901-M3-LAYERED-RESCUE-064`：斗罗真实结果证明 M3 失败不能统一归因于模型。N4 改为先全局处理 grounded same 图，在 cannot-link 硬约束下合并无冲突分量；旧 bridge 的完整上下文并集长度判断改为有界过渡窗口；未决局部人物保留为 provisional singleton，事实不再丢失。仅对上述确定性步骤之后仍 unresolved 的 cluster 使用一次多候选二次模型裁决，模型只看标签、事实和关联原文，不读写内部 ref/ID/span/hash；输出仍需严格 Grounding。
- `DEC-20260831-IDENTITY-CURRENT-SCOPE-ACCEPTED-062`：用户确认斗破当前身份结果可接受，不为尚未出现的“同名不同人”与 `different`/`cannot-link` 案例提前增加复杂策略。F-NEW-IDENTITY-006 按当前范围完成；未来真实数据出现错合并、明确 different/cannot-link 或无法安全聚类时，以该真实案例重开身份功能并增加对应回归。后续优先转向确定性人物档案组装。
- `DEC-20260831-CROSS-CHUNK-IDENTITY-060`：用户授权开始跨 Chunk 人物身份层。身份层采用“代码候选与注册表 + 最小 M3 关系判断 + N4 严格 Grounding/聚类”；模型不读取或输出 ref、ID、span、hash，只返回 same/different/uncertain、标签关系和逐字身份证据。同名、外貌相似、称号或泛称只用于候选召回，不能直接合并；different 形成 cannot-link，多 same 或证据歧义进入 review。全局 ID、事实引用、冲突保留和 unresolved 状态由代码管理。本轮先交付零 Provider 的可测纵向切片，不宣称身份模型质量 Gate 通过。
- `DEC-20260831-PROMOTION-PARTIAL-ACCEPTANCE-059`：用户根据斗破评测确认 promotion 改为事实级部分接受。人物标签有效且至少一条事实能安全唯一 Grounding 时建立人物；唯一事实正常归入，重复/歧义/不存在的事实逐条进入 review 并留在未分配池，不再连带删除安全事实。任何歧义仍不得猜测 occurrence；标签歧义、人物间标签或已接受事实重叠仍失败关闭。模型输出缓存与 grounding 策略版本分离，允许不调用模型地重放旧输出。
- `DEC-20260831-DOCUMENT-EVIDENCE-QUOTEHASH-058`：逐条 `quote_hash` 与 `mention_quote_hash` 从 N2 grounded packet v6 删除；原文真实性继续由 raw quote、source span 回放和 chunk/document hash 验证。文档汇总只合并同来源类型、同人物标签、同文档事实 span、同原文和同结构的事实，合并后保存全部来源 occurrence。`fact_hash` 标识完整文档事实，不重新引入逐 quote hash。本决定不实现跨 Chunk 语义人物合并。

## 路线变更记录

- `DEC-20260830-M2-MINIMAL-FACT-SCHEMA-054`：用户确认 M2 模型不读取或输出 `describe_ref`、`fragment_ref`、`evidence_ref`、assessments、归属状态、claimed/support quote/span 或 epistemic 状态，只返回肯定属于当前 exact 的 `fact_quote/category/attribute/value`。内部 ref、来源、span、hash、缓存和 trace 留在代码信封；代码优先绑定 target evidence，否则仅在一个 describe occurrence 中安全且唯一匹配时回填来源。唯一 exact 认领的 fact span 才归并并从派生 describe 工作池消费；匹配不唯一或多个 exact 重叠认领时不删除并进入复核。该决定由用户于 2026-08-30 明确确认。复审条件：M2 运行时实现时用真实输出验证唯一绑定召回率和歧义率。
- `DEC-20260830-N2-EXACT-PRECEDENCE-053`：用户确认 N2 在完成原文 Grounding 后，以当前 Chunk 全部有效 `exact` evidence quote 为优先集合，逐条删除所有 `describe` 块中的同文 evidence；若 describe 的 approved evidence 被删空，则删除整个 describe grounded block。M1 原始模型输出保持不变；exact↔exact、describe↔describe、null 和跨 Chunk 不参与此规则。比较使用 Grounding 回填后的 raw `evidence_quote` 完全相等，因此纯空白恢复到同一原文后也会去重。删除写入 code trace，packet hash 必须基于过滤后的 evidence 重算。该决定由用户于 2026-08-30 明确确认。复审条件：M2 输入组包时验证只消费过滤后的 N2 packet。
- `DEC-20260830-M1-SCOPE-GROUNDING-051`：用户确认人物 `mention_quote` 只需验证在正文中准确存在，不再保存或统计人物名称的 occurrence 数量与位置；evidence 仍保留原文 span。Evidence grounding 在严格匹配失败后，可接受仅 Unicode 空白差异并回填真实原文 quote；任何非空白字符变化继续拒绝。M1 增加与 `mention_type` 正交的 `mention_scope`，集合提及标为 `collective` 并隔离于单人物 promotion。该决定替代 `M1-OUTPUT-DIAGNOSIS-050` 中“增加 occurrence-specific mention anchor”的建议，由用户于 2026-08-30 明确确认。复审条件：M2/N3 实现前检查 collective routing 和 evidence span 契约。
