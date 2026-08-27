# R2 人物实体解析与十章收敛契约

## 1. 当前实现

视觉抽取不再按 `representative_name` 直接创建人物。生产主链依次执行：

```text
章节视觉候选抽取
  → 服务端定位 mention 与视觉证据
  → 候选包持久化（尚无正式人物归属）
  → 实体解析模型读取当前章 + 累计人物记忆
  → 每满 10 个 Chunk 固定收敛
  → 文末不足 10 个 Chunk 执行尾批收敛/最终检查
  → 仅 final 人物绑定物化 pending FeatureObservation
  → R3 解析人物阶段与时间作用域
  → 仅 final 作用域激活 Observation
  → 外观聚合
```

`CharacterResolutionChunk` 保存每章候选、逐章判断、输入指纹和判断后的累计记忆；`CharacterConvergenceBatch` 保存十章批次、尾批、输入指纹、最终决策和收敛后的记忆。两者都以 Run 为边界，支持恢复和审计。

## 2. 模型输入

逐章解析调用接收：

- 当前 Chunk 原文；预算允许时使用全文，超限才裁成覆盖所有 mention/事实的局部窗口，并记录 `text_truncated`；
- 当前章已定位的 mention 和视觉事实候选；
- 第 1 章到上一章累积形成的人物记忆，不只读取上一章；
- 上一章尾部；
- 历史记忆中的短证据片段。

模型对每个当前 mention 返回 `link_existing`、`create_candidate` 或 `unresolved`。代码只验证决策覆盖、ID 存在性和引文存在性，不按称呼或外观替模型判断身份。

## 3. 十章收敛

批次大小是代码常量 `10`。第 10、20、30……个 Chunk 后各执行一次；全文结束时若有余数，再执行一次 `final_batch=true` 的尾批。整十章结束时，该十章批次本身标记为最终批。

收敛模型返回：

- `confirm_link`：确认连接到已有 `character_id`；
- `create_character`：从一组 mention 创建新人物；
- `keep_unresolved`：证据不足，继续保留候选；
- `split_candidate`：把错误聚在一起的候选拆开创建；
- `reject_candidate`：拒绝候选。

输出必须恰好覆盖本次所有 provisional/unresolved mention；重复、遗漏、外部 ID 或找不到原文的证据都会失败关闭。

## 4. 防止“另一个男孩”污染唐三

“男孩”“孩子”“男人”“老师”“父亲”“黑衣人”等只是具体位置上的 `mention_text`，不是全书别名。系统没有“看到相同字符串就复用人物”的生产规则。

同名也不是身份键；数据库不再要求 `(novel_id, canonical_name)` 唯一。两个同名人物可以拥有不同 `character_id`，模型必须用 mention、证据和 creation_key 分组。

例如：

```text
第 1 章：山顶上坐着一个男孩，生着黑发。
第 2 章：这个男孩正是唐三。
第 3 章：河边又站着一个男孩，穿着红衣。
```

模型可以用第 2 章的明确身份句把第 1、2 章 mention 收敛到唐三。第 3 章只有相同泛称，没有身份依据，应保持 `unresolved`。因此黑发可以成为唐三的正式事实，红衣不会写给唐三，也不会进入外观聚合。

视觉相似仅允许作为弱辅助证据，不能单独确认身份。

## 5. 成本、恢复与失败策略

- 有候选的 Chunk 至多一次逐章实体解析调用；无候选 Chunk 不调用模型。
- 每个有效十章/尾批至多一次收敛调用；没有 provisional 候选时直接记录空批次。
- 每次 Run 受 `ENTITY_RESOLUTION_MAX_CALLS_PER_RUN` 限制；上下文受 `ENTITY_RESOLUTION_CONTEXT_BUDGET_TOKENS` 限制；输出、截止时间和重试沿用 LLM Provider 门禁。
- 远程调用把 input hash、调用序号、请求 ID、模型和 token usage 写入 RunEvent。
- 视觉候选先于实体调用持久化，恢复不会重复已保存的视觉抽取；Chunk 和批次都有唯一键与 input hash。
- 实体解析或收敛失败时，不会生成正式 Observation；旧 Run 的 active 事实保持不变。

当前实现没有“第一次判断后再调用一次模型复核”的重复节点。人物绑定完成后由独立 R3 步骤决定阶段和时间作用域；高风险歧义进入审核门禁，不得让第二次模型调用直接覆盖业务事实。完整边界见[R3 人物阶段与时间作用域解析契约](25-character-phase-resolution-contract.md)。
