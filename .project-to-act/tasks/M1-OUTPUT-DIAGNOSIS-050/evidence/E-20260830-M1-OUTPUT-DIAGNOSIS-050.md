# E-20260830-M1-OUTPUT-DIAGNOSIS-050

## 执行结论

当前输出同时存在四类不同问题，不能统一归咎于 Prompt：

1. 输入覆盖事实不符：文件实际只有第 1–19 章，不含第 20 章，而且每章标题重复两次。
2. M1 语义候选噪声：高召回策略与边界提示不足共同带来表情、情绪、动作、年龄事实和集合人物等候选；M2 尚未实现，所以这些中间候选直接暴露给用户。
3. N2 grounding 表示能力不足：逐字校验正确地拒绝改写，但也把只压缩了段落空白的关键证据丢掉；mention 只按表面字符串绑定全部 occurrence，没有绑定证据所对应的具体 occurrence。
4. 批处理审计与成本指标失真：断点续跑覆盖了失败历史，summary 混用“本次 invocation”与“全部成功 Chunk”的统计口径，trace 缺少 Prompt/config hash。

因此最小修复顺序应为：确定性数据与审计修复 → occurrence/quote grounding 修复 → 人工回归集 → 小切片 Prompt/模型/Chunk 对照实验。不要先重跑全文或直接堆 Prompt。

## 可复核事实

### 1. 输入与 Chunk

- 源文件：37,655 Unicode code points，SHA-256 `4dd3d57c99f4b2548c45c69a391918a391782e64a4526971b2e6e34a81e2ed0e`。
- 标题解析只得到唯一章节 1–19；没有第 20 章。每章标题在正文开头连续出现两次。
- 17 个固定窗口中只有第 1 块从章边界开始；其余块从句中或段中开始，多数块跨越章节。250 字重叠降低了断裂风险，但增加重复和上下文混合。

### 2. 输出数量的真实含义

- 63 个 raw candidate mentions；grounding 后 60 个 mention blocks。
- summary 的 `approved_evidence_quotes=149` 实际是 mention–evidence bindings，不是 149 条独立引文。
- grounded 中只有 80 个唯一 quote 文本、84 个 Chunk 内 quote occurrence；同一引文被允许绑定到多个 exact/describe，这是当前契约的有意高召回行为。
- 149 个 binding 中 109 个（73.2%）是 `contextual`。该值只表示 evidence 字符串不含 mention 字符串，不证明人物归属正确。
- 跨 Chunk 有 4 组重复的相同 mention–evidence pair；当前没有文档级去重视图。

### 3. 明确的 quote fidelity 失败

- 4 个 rejected bindings 对应 2 个唯一模型引文。
- 唐昊的关键整段外貌在模型输出中删除了原文段落间空白/换行，字符内容保持一致；严格 substring gate 因此把该证据同时从 `唐昊` 和 `中年男子` 两个块拒绝。这是重要 false negative。
- `唐大先生的眼睛湿润了` 在原文中实际为主语句后再出现 `他的眼睛湿润了`，模型插入了一个“的”；这是真正改写，应继续拒绝。
- 根因：模型自由复制长 quote 会规范化排版或轻微改写；Schema 只能约束类型，不能保证 substring。

### 4. occurrence 绑定缺口

- 60 个 grounded mentions 中有 49 个的 `mention_occurrence_count > 1`。
- 例如一个 Chunk 中 `门房` 出现 23 次、`男孩儿` 出现 9 次，但当前 packet 把同一表面词的全部 span 都放进 mention block；它没有说明某条 evidence 锚定哪一次 mention。
- exact 名称在单 Chunk 内通常仍指同一人，但 `孩子`、`男孩儿`、`年轻人`、`父亲`、`门房` 等 describe 可能指不同 occurrence 或不同人物。
- 根因：当前 Schema 是 mention-level aggregation；`ground_m1_result` 用 `find_occurrences` 收集全部同文字符串，没有 evidence-to-mention occurrence edge。

### 5. 语义噪声与类型不一致

- 明确可疑的候选包括纯年龄事实、笑容/紧张/怒气/目光等瞬时表情、`面不红，气不喘` 等状态，以及只有身份称呼而没有外貌细节的 `看门的青年`。
- `十七道白色的身影` 是集合人物，当前只有 individual exact/describe/null，不能表达 collective；后续 promotion 可能把一群人误建成一个人。
- `老杰克` 在不同 Chunk 中同时被标为 exact 和 describe，是唯一相同 surface 的跨类型冲突。Chunk 独立调用、未使用文档级 alias/type registry 是主因。
- 这些问题中，一部分是模型违反“纯动作/心理不单独作为 evidence”的 Prompt，一部分是“可能包含”“年龄/可见变化”的边界过宽，还有一部分是当前 M1 有意把归属、时间作用域和事实分类推迟给 M2。
- 因此原始 M1 是候选层，不应作为最终人物卡直接展示。

### 6. 成本、波动和审计

- 17 个成功 trace 合计 output 59,321 tokens，其中 reasoning 54,803，占 92.4%；可见 JSON 约 4,518 tokens。
- 单次成功耗时 15.3–54.5 秒，中位数 27.7 秒。
- 第 3 块在 8,192 上限下曾 `max_output_tokens`，随后 16,384 上限重试却只使用 3,297 output tokens，说明 reasoning 长度存在明显运行间波动。
- 最终 `summary.json` 显示 `duration_ms=28,110`、`new_provider_calls=1`，但同时汇总 17 个成功 Chunk 的 usage；17 个成功 trace 自身耗时合计 528,641 ms。统计作用域混杂。
- `failures.json` 在成功续跑后被覆盖为空，最终目录无法单独还原曾经的截断失败。
- trace 没有记录 reasoning effort、max output tokens、Prompt hash、response schema hash 或 runtime config hash，无法仅靠产物完整复现。

## 上游 novel-characters 参考结论

适合吸收：

- 第一趟高召回 roster、第二趟逐角色 profile 的两阶段分工；
- 跨 Chunk 按 name/aliases 归并，并把名字包含等语义关系仅列为 `mergeCandidates`，要求复核而非自动判决；
- 每角色独立卡片和断点续跑；
- 最终逐字 quote validator；
- 把真实失败固化进校验和自测。

不应照搬：

- roster `note` 是自由总结，第二趟依赖 note；V3 不能让未经 grounding 的总结成为事实来源；
- 为画面完整而补全并标注推断适合最终设计层，不适合 M1/N2 证据层；
- 按前 N 名截断角色不符合当前“完整证据扫描”目标，除非显式声明 coverage。

## 建议修复路线

### P0：先修确定性正确性与审计

1. 输入预检：解析章节号、重复标题、缺章和末尾完整性；期望“前 20 章”时发现只到 19 必须显式失败或标记 truncated。
2. 运行历史改为 append-only：保存每次 invocation、失败与恢复；summary 分开 `current_state`、`cumulative_attempts`、`successful_usage`。
3. trace 增加 runtime/model/Prompt/Schema/chunk policy/config hash，以及 reasoning effort、max output tokens。
4. 修正指标名：区分 evidence bindings、unique quote texts、Chunk quote occurrences 和 overlap duplicates。

### P1：修 grounding 表示

1. 对 quote 采用两级 gate：先严格 substring；失败后只允许“删除空白后字符完全一致”的安全恢复，并把 compact 文本映射回原始 raw span。任何增删非空白字符仍拒绝。这样可恢复唐昊段落，不放过“唐大先生的……”改写。
2. approved evidence 增加 occurrence-specific anchor：`evidence_source_span` 对应一个或多个 `candidate_mention_spans`；contains mention 可确定性绑定，contextual 只保留邻近候选并标记 ambiguous，不把全部同文 mention span 当成一个锚点。
3. 增加 `collective` 隔离或 deterministic quarantine，防止集合 describe 直接 promotion 成单个人物。
4. 产出 raw candidates、grounded candidates、document-normalized view 三层文件；原始结果不可覆盖。

### P2：建立小而真实的评测集

从本次输出选取 30–50 个段落，至少覆盖：

- exact/describe/null；同一 surface 类型冲突；别名；
- 多 occurrence 泛称；跨句代词；集合人物；
- 稳定外貌、衣着、变身、年龄外观、瞬时表情、纯动作；
- quote 中换行/空格、重叠边界、无外貌人物和困难负例。

人工标注 mention 类型、evidence 是否为目标范围、raw span、对应 mention occurrence、collective 和 stable/transient。分别报告 mention/evidence precision、recall、quote recovery、类型一致性、归属歧义、延迟、tokens 和失败率；不能再只报告 schema-valid 数量。

### P3：一次只改一个变量做对照

1. 当前 Prompt + reasoning `none` 对比 `low`，先看质量是否下降以及 reasoning/cost/截断改善，不直接改默认值。
2. 固定 2,500 窗口对比章/段落边界切分；保留 raw span，不做正文归一化。
3. Prompt 加少量高信息量正反例，明确“实际年龄不等于年龄外观”“表情/情绪默认不算稳定外貌”“只有称呼无外貌信息不输出”“集合人物隔离”。
4. 若逐字复制仍是主要失败，再比较“预分句并让模型返回 sentence ref”方案；这需要版本化 M1 payload/Schema，不能静默改变冻结契约。
5. 最后才比较模型或条件路由；没有回归集前不更换模型、不微调、不增加 Agent 数量。

## Gate 与限制

- 本轮是 L1 只读诊断，没有重新调用模型，没有修改实现或真实运行产物。
- 没有人工 gold，因此不能声称 precision、recall 或“漏掉 57 段”；关键词扫描只用于发现审查候选，不作为质量指标。
- 阶段 5 revision 2 保持 `in_progress`；本任务完成不代表阶段 5 或 M1 质量 Gate 通过。

## 验证记录

- 时间：2026-08-30（Asia/Shanghai）。
- 版本：runtime `0.1.0.dev3`；Lifecycle stage 5 / revision 2；source run `m1-douluo-20ch-20260830-v3`。
- 方法：以只读 Python/JSON 分析复核 17 个 Chunk、raw model output、grounded packet、manifest、summary、failure file 和逐块 Provider trace；同时对照 V3 契约与固定上游 `novel-characters` 的 roster/profile/validate 设计。
- 验证：Project-to-Act `--validate` exit 0；Lifecycle `validate` exit 0；任务 JSON 解析与 evidence 文件存在性检查 exit 0；`git diff --check` exit 0（仅有现存 CRLF 提示）。
- 证据位置：本文件及 `runs/m1-douluo-20ch-20260830-v3/`；没有复制 API Key、完整 Prompt、reasoning 或大段正文。
- 有效期：对 source hash、runtime、Prompt、Schema、模型配置、grounding 或 batch summary 逻辑任一变化后，量化结论需重新生成；修复后的质量结论必须来自版本化人工标注集。
