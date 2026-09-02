# M3 身份补救第一轮证据

## 真实失败归因

- 斗罗 dev13 的 5 个 `multiple_same_character_candidates` 全部来自唐三。
- 把保存的 47 条 grounded same edge 与 1 条 deterministic edge 作为全局图分析后，所有 same 连通分量内部均无 cannot-link；旧失败由逐节点顺序 union 造成，不需要新增模型调用。
- 旧 bridge 对唐三 0/2862 两个节点选择的完整 context 并集长 1950，超过 1200 后整个丢弃；实际两个 context 间隔只有 919，并包含“唐三走了……另一次命运却刚刚开始”。
- “年轻人微笑道：我叫素云涛”是显式介绍，但旧召回只有标签/事实相似，无法召回 `素云涛` 与 `年轻人`。
- singleton unresolved 被旧注册表跳过，造成 23 条已经 Grounding 的事实未分配。

## 实现结果

- `global-constrained-identity-v2`：所有 grounded same edge 全局合并，cannot-link 逐边硬约束；不再产生顺序式 multiple 假失败。
- `identity-evidence-window-v2`：完整 context 并集过长时，在 1200 字符总预算内保留间隔末段和后续过渡。斗罗唐三关键任务得到 660 + 540 字符两段，同时包含“另一次命运却刚刚开始”和“眼前的这个孩子”。
- `bounded-local-candidate-retrieval-v2`：只在介绍标记附近同时出现人物标签时增加弱候选；斗罗新增有效 `素云涛` → `年轻人` 候选，总任务 63 → 64，而不是场景内全配对。
- uncertain singleton 仍写入 registry，继续保留 unresolved/review，但其事实不再成为 unassigned。

## 旧 M3 决策离线重放估算

未调用 Provider，仅将旧 63 条 grounded decision 交给新 N4 聚合语义：

- bound local nodes：33 → 43
- unresolved bindings：10 → 3
- `multiple_same_character_candidates`：5 → 0
- registry appearance fact refs：106 → 129
- profiles 可分配事实：106 → 129，预期 unassigned：23 → 0
- global characters：8 → 12（其中 3 个仍为未决 singleton，等待残余裁决）
- cannot-link：仍为 1，`大师` 与 `战魂大师` 未跨约束合并

剩余 3 个硬 unresolved 是：`唐三`、`男孩儿`、`看门的青年`。另外 `小三`、`唐昊` 等已有同簇节点仍保留 review，但不再丢事实。

## 验证

- `python -m unittest discover -s tests -v`：122/122 通过。
- 新增回归覆盖：全局 same 分支合并、cannot-link 传递阻断、oversized bridge 有界恢复、显式介绍召回、uncertain singleton 事实保留。
- 新策略准备斗罗：43 nodes、1 deterministic edge、64 bounded M3 tasks；Provider calls=0。

## 残余模型节点实现

只对确定性聚合后仍 unresolved 的人物执行 cluster-level 多候选裁决。模型看到当前人物与最多 2–3 个候选簇的标签、事实原文和候选专属关系原文；不读取 ref、ID、span、hash/cache。输出为任务内候选序号、关系、标签关系和逐字身份证据，代码回填真实节点并在 cannot-link 前失败关闭。

证据域采用两层隔离：

- `current_character.context_quotes`、候选 `context_quotes` 和 `appearance_fact_quotes` 只用于理解；
- `identity_evidence_quotes` 只能来自模型所选候选的 `relationship_context_quotes`；
- Grounding 只搜索该候选的关系绑定，要求唯一严格匹配；严格失败后仅允许纯空白等价；
- 仅人物标签、少于 6 个非空白字符、多文档 occurrence、非空白改写或从普通 context 抄取都会被拒绝，关系降级为 uncertain；
- 没有关系上下文的残余人物不创建模型任务。

实现包含 Provider 0 准备命令、可恢复 DeepSeek 命令、模型输出/grounded decision/trace/failure 分离产物、追加式 history，以及将安全结果作为 supplemental decisions 重建 `document-character-registry.json`。

## 斗罗离线准备与验证

- 来源：`runs/douluo-20ch-e2e-dev13-20260831/identity` 的 63 条旧 M3 结果；未重跑基础 M3。
- 输出：`runs/douluo-20ch-e2e-dev13-20260831/identity-rescue-dev15`。
- 生成 5 tasks、5 candidate options、10 relationship context quotes；Provider calls=0。
- 覆盖两组残余唐三→唐三、小三→唐三、素云涛→战魂大师/年轻人/青年簇、男孩儿→唐三。
- `看门的青年` 没有能支撑身份关系的关联原文，因此不生成调用并继续 unresolved。
- `python -m compileall -q src`：通过。
- `python -m unittest discover -s tests -v`：128/128 通过。
- 定向测试覆盖：所选候选关系证据接受、普通 context 证据拒绝、仅标签证据拒绝、最小 payload 字段隔离、supplemental merge、缓存恢复。
- Schema：`3.15.0-draft1`；runtime：`0.1.0.dev15`。

真实 5 个 DeepSeek 残余调用未执行，因此这里证明接线、失败关闭和真实输入可准备，不宣称模型判断质量通过。
