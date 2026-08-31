# 项目总览

## 基本信息

- 项目：Novel Character Generator
- 分支：`v3-simplified-character-evidence`
- 状态：M1/N2/M2/N3/promotion、文档事实汇总和跨 Chunk 身份运行时均已建立；斗破真实 M3 19/19 完成并生成 11 个全局人物，当前真实样本范围已接受，同名不同人/different/cannot-link 延后到真实案例触发时再加固
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

身份层按当前真实样本范围收口。下一阶段建议实现纯代码的人物档案组装：把全局 `character_id`、人物标签和 `document-character-evidence.json` 中的完整事实、安全来源、绝对 span、原文与冲突/review 汇总成统一 `document-character-profiles.json`。这一阶段先提供结构化、可追溯档案，不调用模型生成自然语言画像；待用户确认后进入实现。

## 最新路线决定

- `DEC-20260831-IDENTITY-CURRENT-SCOPE-ACCEPTED-062`：用户确认斗破当前身份结果可接受，不为尚未出现的“同名不同人”与 `different`/`cannot-link` 案例提前增加复杂策略。F-NEW-IDENTITY-006 按当前范围完成；未来真实数据出现错合并、明确 different/cannot-link 或无法安全聚类时，以该真实案例重开身份功能并增加对应回归。后续优先转向确定性人物档案组装。
- `DEC-20260831-CROSS-CHUNK-IDENTITY-060`：用户授权开始跨 Chunk 人物身份层。身份层采用“代码候选与注册表 + 最小 M3 关系判断 + N4 严格 Grounding/聚类”；模型不读取或输出 ref、ID、span、hash，只返回 same/different/uncertain、标签关系和逐字身份证据。同名、外貌相似、称号或泛称只用于候选召回，不能直接合并；different 形成 cannot-link，多 same 或证据歧义进入 review。全局 ID、事实引用、冲突保留和 unresolved 状态由代码管理。本轮先交付零 Provider 的可测纵向切片，不宣称身份模型质量 Gate 通过。
- `DEC-20260831-PROMOTION-PARTIAL-ACCEPTANCE-059`：用户根据斗破评测确认 promotion 改为事实级部分接受。人物标签有效且至少一条事实能安全唯一 Grounding 时建立人物；唯一事实正常归入，重复/歧义/不存在的事实逐条进入 review 并留在未分配池，不再连带删除安全事实。任何歧义仍不得猜测 occurrence；标签歧义、人物间标签或已接受事实重叠仍失败关闭。模型输出缓存与 grounding 策略版本分离，允许不调用模型地重放旧输出。
- `DEC-20260831-DOCUMENT-EVIDENCE-QUOTEHASH-058`：逐条 `quote_hash` 与 `mention_quote_hash` 从 N2 grounded packet v6 删除；原文真实性继续由 raw quote、source span 回放和 chunk/document hash 验证。文档汇总只合并同来源类型、同人物标签、同文档事实 span、同原文和同结构的事实，合并后保存全部来源 occurrence。`fact_hash` 标识完整文档事实，不重新引入逐 quote hash。本决定不实现跨 Chunk 语义人物合并。

## 路线变更记录

- `DEC-20260830-M2-MINIMAL-FACT-SCHEMA-054`：用户确认 M2 模型不读取或输出 `describe_ref`、`fragment_ref`、`evidence_ref`、assessments、归属状态、claimed/support quote/span 或 epistemic 状态，只返回肯定属于当前 exact 的 `fact_quote/category/attribute/value`。内部 ref、来源、span、hash、缓存和 trace 留在代码信封；代码优先绑定 target evidence，否则仅在一个 describe occurrence 中安全且唯一匹配时回填来源。唯一 exact 认领的 fact span 才归并并从派生 describe 工作池消费；匹配不唯一或多个 exact 重叠认领时不删除并进入复核。该决定由用户于 2026-08-30 明确确认。复审条件：M2 运行时实现时用真实输出验证唯一绑定召回率和歧义率。
- `DEC-20260830-N2-EXACT-PRECEDENCE-053`：用户确认 N2 在完成原文 Grounding 后，以当前 Chunk 全部有效 `exact` evidence quote 为优先集合，逐条删除所有 `describe` 块中的同文 evidence；若 describe 的 approved evidence 被删空，则删除整个 describe grounded block。M1 原始模型输出保持不变；exact↔exact、describe↔describe、null 和跨 Chunk 不参与此规则。比较使用 Grounding 回填后的 raw `evidence_quote` 完全相等，因此纯空白恢复到同一原文后也会去重。删除写入 code trace，packet hash 必须基于过滤后的 evidence 重算。该决定由用户于 2026-08-30 明确确认。复审条件：M2 输入组包时验证只消费过滤后的 N2 packet。
- `DEC-20260830-M1-SCOPE-GROUNDING-051`：用户确认人物 `mention_quote` 只需验证在正文中准确存在，不再保存或统计人物名称的 occurrence 数量与位置；evidence 仍保留原文 span。Evidence grounding 在严格匹配失败后，可接受仅 Unicode 空白差异并回填真实原文 quote；任何非空白字符变化继续拒绝。M1 增加与 `mention_type` 正交的 `mention_scope`，集合提及标为 `collective` 并隔离于单人物 promotion。该决定替代 `M1-OUTPUT-DIAGNOSIS-050` 中“增加 occurrence-specific mention anchor”的建议，由用户于 2026-08-30 明确确认。复审条件：M2/N3 实现前检查 collective routing 和 evidence span 契约。
