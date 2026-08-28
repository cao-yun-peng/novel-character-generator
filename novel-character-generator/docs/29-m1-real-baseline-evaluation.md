# M1 局部观察发现：首次真实效果基线

> 结论：工程可靠性通过，模型语义效果未通过。当前不得启动 M2，也不得把 M1 接入生产主链。

## 1. 运行边界

- 日期：2026-08-28；
- Provider / 模型：`deepseek` / `deepseek-v4-flash`；
- 契约 / Prompt：`local-observation-contract-v1.1` / `local-observation-discovery-prompt-v1.1`；
- 运行数据：用户授权的 `m1-local-observation-v1`，15 个 case，每个 case 1 次；
- 运行方式：真实 Provider、`chat_completions`、thinking 关闭、最多 1 次重试；
- 隔离：只运行 M1 开发集，不写数据库、不修改 Worker 路由、不保存密钥或完整 Provider 响应。

首次受限环境运行全部停在网络传输层，只作为环境失败记录，不计模型效果。获授权的联网重跑 15/15 成功，且每项均一次成功。

## 2. 结果

真实输出暴露了四处测试标注/评分边界问题：合法 descriptor `红衣少女`、自然表达 `红色的衣服`、最小 transformation 引文 `化作`，以及可安全保留为 Chunk 局部 descriptor 的 `其中一人`。这些只修正测量层，并对同一批保存输出零调用离线重评为 `m1-local-observation-v1.1-draft2`。

| 指标 | 结果 | 解释 |
|---|---:|---|
| Case | 11 pass / 0 review / 4 fail | 73.3% case 通过 |
| 必出事实召回 | 13 / 15 = 86.7% | 漏掉 2 个年龄事实 |
| 已支持事实精度 | 13 / 13 = 100% | 输出事实均有当前标注支持 |
| 引文忠实度 | 100% | entity、fact、signal、unresolved 引文均来自当前 Chunk |
| 认知状态准确率 | 100% | 已命中的 asserted / negated / uncertain / inferred 均正确 |
| 时间/状态信号召回 | 1 / 4 = 25% | 仅 transformation 完整命中 |
| 时间/状态信号精度 | 1 / 4 = 25% | 两个 age 绑定错误，一个 presentation 分类错误 |
| unresolved | 期望 0，实际 1，匹配 0 | 当前集不能验证正向 recall；出现 1 个非视觉误报 |
| 调用可靠性 | 15 / 15 | 无重试、无 Schema/服务端契约失败 |
| 延迟 | 平均 3.04s；P50 3.09s；P95 4.26s | 15 次串行总墙钟 45.8s |
| Token | 输入 28,948；输出 2,749；总计 31,697 | 输入 cache hit 23,296；reasoning 0 |

这里的 11/15 是“修正后的开发集诊断分”，不是独立验收分。因为修订由本轮输出触发，当前 15 case 此后只能作为回归集；修复 Prompt 后还需要一组用户审核的新 held-out case 才能做无泄漏验收。

## 3. 四个真实失败

| Case | 实际问题 | 归因 |
|---|---|---|
| `m1-inferred-age-006` | 找到白发，却漏掉 inferred 年龄事实；age signal 错绑到白发事实 | Prompt 没有明确要求“外观推断年龄同时输出事实与 signal”，`fact_ref` 约束不够直观 |
| `m1-explicit-age-007` | 找到瘦小体型，却漏掉明确年龄事实；age signal 错绑到体型事实 | 同上，模型把年龄只当 signal，没有保留为 `physical_identity` raw fact |
| `m1-ambiguous-owner-012` | 青铜面具事实与 `其中一人` owner 正确，但又把非视觉的“兄弟二人并肩而立”放进 unresolved | unresolved 的“只接显式视觉命题”边界还不够强 |
| `m1-presentation-change-015` | 白裙事实正确，但把“进入宴会前”标成 `other_state`，漏掉“换上”对应的 `presentation` | presentation 与普通时间背景的分类/证据边界不够明确 |

## 4. 已经可靠的能力

- 同一人物的头发/服装原始命题拆分与多人 owner 分离；
- descriptor、pronoun、explicit name 的局部表示；
- negated、uncertain 认知状态保持；
- 非视觉空结果、内心情绪、手持物、previous-tail 复制和正文指令污染的排除；
- transformation 事实、信号和最小原文证据；
- JSON Schema、局部引用、原文引文和服务端契约稳定性。

## 5. Gate 与下一步

当前 M1 模型质量 Gate 为 `failed_pending_dataset_review_and_m1_fix`。问题集中在 Prompt 的输出关系与分类边界，不需要扩宽 M1 职责，也没有证据支持把开放语义改成关键词规则。

建议下一增量只做三类最小修复：

1. 明确 age 内容必须同时保留 raw fact 与 age signal；`fact_ref` 只能指向被该信号直接限定的事实，没有对应事实时必须为 null；
2. 用通用定义和正反例区分 `presentation`、`other_state` 与纯时间背景；
3. 强化 unresolved 只接无法安全表示的显式视觉命题，并补至少一个真正应 unresolved 的正向测试。

修复后先跑 4 个失败 case 加 11 个回归 case；用户审核一组新的 held-out case 后，再做一次真实质量 Gate。达到该 Gate 前不开始 M2。

## 6. 可复核工件

- 原始真实运行元数据：`data/diagnostics/m1-local-observation/20260828-deepseek-v4-flash-baseline1-online/run.json`；
- 保存的结构化输出：`data/diagnostics/m1-local-observation/20260828-deepseek-v4-flash-baseline1-online/outputs.json`；
- 测量修正版报告：`data/diagnostics/m1-local-observation/20260828-deepseek-v4-flash-baseline1-online/report-v1.1-draft2.json`；
- 待用户审核数据集：`tests/evaluation/m1_local_observation_discovery_v1.json`。
