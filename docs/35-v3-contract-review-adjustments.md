# V3 契约审查后的技术调整

## 结论

审查意见不要求推翻 V3 主架构。M1 证据发现、N2 确定性定位、M2 逐 exact 批量归属、N3 全局仲裁仍然成立。正式实现前需要把容易产生歧义的工程边界冻结。

## 调整清单

| 审查项 | 处理 | 最终决定 |
|---|---|---|
| exact 的昵称、称号和职务边界 | 已修改 | 正式姓名和词汇化稳定昵称可 exact；开放角色、排行、职务默认 describe；不确定时降级 |
| mention 与 evidence 的包含关系 | 已修改 | 不强制包含；N2 派生 contains_mention/contextual/no_mention，不增加 M1 模型字段 |
| claimed evidence 重复字符串定位 | 已修改 | source、fragment、claimed、support 全部携带 span；禁止按首次字符串匹配定位 |
| describe 冲突规则过粗 | 已修改 | N3 以字符 span 仲裁；同一 evidence 内互不重叠的区间可分别归给不同 exact |
| 剩余池重复处理 | 已修改 | pair cache key 防止 exact×fragment 重复归属；pool hash 与 promotion hash 防止相同剩余池重复调用或重复建人 |
| 模型输入输出边界 | 已修改 | 每个 exact 一次携带全部 describe；系统身份、原文绝对 span、hash 和 cache key 留在代码信封，模型只处理目标、证据、Chunk 正文及片段内局部 span |
| 剩余 describe 的去向 | 已修改 | 不再回给全部 exact；每个剩余 describe 单独进入 M2，可按不重叠证据拆成一个或多个 Chunk 内正式人物 |
| packet hash 的“规范化”不明确 | 已修改 | 基于原始 UTF-8、Chunk hash 和 span；禁止隐式换行、空白、Unicode、标点归一化 |

## 调研报告带来的额外调整

[开源项目与 Skill 调研](34-open-source-novel-character-visualization-research.md) 支持继续保持当前 M1–N3 边界，同时增加两项当前阶段必须具备的工程能力：

| 调研发现 | 当前技术决定 |
|---|---|
| 长文本需要重叠 Chunk，避免边界漏召回 | 增加版本化 `chunking_policy_version`、`chunk_source_span` 和左右重叠字符数 |
| 处理上限不能静默丢尾部 | 增加 `DocumentChunkManifest` 与显式 `complete/truncated`、`truncation_reason` |
| 重叠区会产生重复证据 | N2 仍保存 Chunk 局部包；后续以来源版本、文档绝对 span 和 quote hash 去重 |
| 自动别名归并与人工复核应分开 | 当前只允许 Chunk 内逐字命名关系形成局部 alias；跨 Chunk merge candidates 留到人物记忆阶段 |
| 原著事实、推断设计和改编设计应分层 | 当前 N3 只产生 grounded facts；inferred/adaptation 字段留给后续 Appearance Profile |
| 确定性自测比仅靠真实模型运行更稳定 | 实现顺序先建设 hash/span/Schema/grounding 测试，再接 Provider |

调研中的角色卡、Prompt Compiler、多视角母版、IP-Adapter、ControlNet 和视觉验收属于后续角色资产阶段，不进入当前 M1–N3 Schema，防止重新把项目做成一个大 Agent。

## 关键数据链

```text
Chunk 原文
└── N2 source_evidence_span
    └── M2 fact_quote（模型仅返回逐字事实，不返回 span）
        └── 代码安全匹配并回填 fact_span
            └── N3 使用 Chunk fact span 仲裁与消费
```

内部信封仍保留 source evidence、fragment 和 Chunk 坐标，但不发送给模型。代码只在 `fact_quote` 能安全且唯一绑定允许证据时回填位置；不唯一时进入复核。原始 N2 evidence 不可变，N3 只消费派生工作池中的字符区间。

## exact 的保守策略

- exact：林黛玉、唐三、王熙凤、凤姐、宝二爷。
- describe：红衣女子、年轻剑客、二小姐、教皇、太子、宗主、大师兄。
- 若当前 Chunk 有逐字命名或同位关系，可建立局部 alias；没有局部证据时不借助未来人物记忆猜测。

这个策略的目标不是一次解决所有人物身份，而是保证 V3 的 exact pool 尽量少混入可多人复用的开放称谓。

## 实现顺序

1. 先实现 DocumentChunkManifest、重叠分块、显式截断、原始文本 hash 和 span 工具。
2. 实现 N2 occurrence 展开和重叠区文档绝对 span 换算。
3. 再实现 exact/describe/null 与 relation_to_mention。
4. 实现每个 exact 一次携带全部 describe 的 M2 归属模式；代码按 exact×fragment 缓存，模型结果只回传任务内 ref 和局部 span。
5. 实现 N3 span 验证、区间仲裁、消费与剩余区间重建。
6. 实现每个剩余 describe 单独进入 M2 的一对多独立建人模式、promotion hash 和证据重叠校验。
7. 最后加入 shadow 数据集。

当前仅完成设计与机器 Schema；没有运行时代码或模型质量结果。
