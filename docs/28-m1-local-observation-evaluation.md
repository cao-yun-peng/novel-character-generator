# M1 v1 局部观察发现：历史测试集审核说明

> 当前状态：15 条短回归集 `m1-local-observation-v1.2` 与 6 条 source-backed 真实集 `m1-local-observation-real-v1.1` 曾按 M1 v1 职责批准，并绑定 Prompt v1.6。自 `semantic-pipeline-v2-design-v1.3` 起，本文件只保留为历史测量说明，不再是 M1 v2 验收口径。
>
> M1 v2 只评分视觉证据覆盖、逐字引文和局部 owner；事实拆分、coarse family、epistemic 与显式 signal 已转交 M2。新边界见 [`32-m1-m2-evidence-semantic-boundary-v2.md`](32-m1-m2-evidence-semantic-boundary-v2.md)。

## 1. 本节点到底测什么

本节描述旧 M1 v1 口径：“当前 Chunk 原文明确说了哪些人物局部外观命题、归谁、是什么认知状态，并出现了哪些显式时间或形态信号？”

这些职责在 v1 中曾用于诊断，但 v2 已进一步收窄 M1。现有样本可以迁移为 evidence coverage 金标，不能直接沿用 required facts、coarse family、epistemic 和 signal 分数作为 v2 Gate。

## 2. 当前 15 个审核项

| Case | 主要把关点 |
|---|---|
| `m1-direct-two-facts-001` | 头发与整件服装拆分；服装内部不按字段过拆 |
| `m1-multi-owner-002` | 两个人物 owner 不串线 |
| `m1-descriptor-owner-003` | 少女等泛称保持 descriptor |
| `m1-negated-scar-004` | “没有伤疤”保持 negated |
| `m1-uncertain-accessory-005` | “似乎”保持 uncertain |
| `m1-inferred-age-006` | 白发 asserted，估龄 inferred，并保留 age 信号 |
| `m1-explicit-age-007` | 明确年龄事实与 age 信号绑定 |
| `m1-transformation-008` | 变形事实与 transformation 信号，不判断持续性 |
| `m1-nonvisual-empty-009` | 非视觉文本允许空结果 |
| `m1-held-object-exclusion-010` | 手持武器排除，腰带保留 |
| `m1-internal-emotion-empty-011` | 内心情绪不推断表情 |
| `m1-ambiguous-owner-012` | “其中一人”保留为 Chunk 局部 descriptor；非视觉动作不得误入 unresolved |
| `m1-previous-tail-is-context-only-013` | `previous_tail` 不发送给 M1，不复制只存在于前文的事实 |
| `m1-untrusted-instruction-014` | 正文中的指令样文本不改变契约 |
| `m1-presentation-change-015` | 换装事实与 presentation 信号，不判断作用范围 |

## 3. 请重点审核的内容

请直接审阅 [`m1_local_observation_discovery_v1.json`](../tests/evaluation/m1_local_observation_discovery_v1.json)：

1. `chunk_text` 是否代表你关心的真实困难；
2. `required_facts` 是否该必出，有没有漏掉合法视觉命题；
3. `evidence_quotes` 的允许边界是否合理；
4. `coarse_family` 和 `epistemic_status` 是否正确；
5. 哪些 case 应补充、删掉或改成 `allowed_facts`；
6. ambiguous owner 是否确实应该 unresolved。

用户已通过“验证 M1 效果”授权真实基线。短集历史 v1.1 修正了 descriptor、等价命题、最小 transformation 引文和 Chunk 局部 owner。随后用户又确认四条真实集口径：安全的较长逐字引文可以命中较短金标；同一 Chunk 的 `仙清儿 / 这个小女孩 / 庙中的怪物` 可共同命中一个局部 owner，但不声明跨 Chunk 身份；`脱掉铁鞋` 是 presentation；叙述者直接给出的 `二十左右 / 十一二岁 / 年龄相仿` 为 asserted，只有显式认知不确定为 uncertain，外观推龄为 inferred。上述变化形成 v1.2/v1.1 approved 数据版本，旧运行结果保留在证据中。

当前 Prompt 与下一组真实 Chunk 的字段、评分和审核方式见 [`30-m1-prompt-and-output-guide.md`](30-m1-prompt-and-output-guide.md)。

## 4. 评分解释

- `required_fact_recall`：必出原始事实找回率；
- `supported_fact_precision`：模型事实中能被 required/allowed 标注支持的比例；真实长 Chunk 的未穷举合法事实可标为 unscored，不进入分母；
- `quote_fidelity`：所有 mention/evidence quote 是否逐字存在于当前 Chunk；
- `epistemic_accuracy`：asserted/negated/uncertain/inferred 是否保持；
- `temporal_signal_recall`：显式时间/呈现/变形信号召回；
- `temporal_signal_precision`：输出信号中类别、owner、fact 绑定与证据均匹配的比例；
- `unresolved_item_recall/precision`：该 defer 的是否保留，以及是否把可安全事实或非视觉内容错误送入 unresolved；报告同时给出分子分母，零期望样本时不能把数值 1.0 解读为该能力已验证；
- `review`：结构、owner、证据和类别已匹配，但 raw proposition 使用了测试集未覆盖的表达，需要人工看，不自动算错。

允许“较长模型引文包含较短金标引文”，但只在 owner、类别等条件一致且候选唯一时生效；若一个长引文可能同时命中多个金标，评分器拒绝自动配对。

这套评分器不使用字符串规则替代生产语义判断。字符串只用于比较已经人工批准的测试期望；生产 M1 的开放语义仍由模型负责，确定性代码只做证据和结构门禁。

## 5. 离线评分命令

准备一个以 case id 为键、M1 输出对象为值的 JSON 文件，然后运行：

```powershell
.\.venv\Scripts\python.exe scripts/evaluate_m1_local_observation.py .\saved-m1-outputs.json --report .\m1-report.json
```

该命令只读取保存输出，不访问 `.env`，不调用 Provider，也不写数据库。
