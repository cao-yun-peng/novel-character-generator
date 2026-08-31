# 斗破苍穹前 5 章 N3 + promotion 运行报告

## 运行结论

- 输入原文：`tests/小说/斗破苍穹前5章.txt`
- 上游 M1：`runs/doupo-first5-m1-scope-v4`
- 上游 M2：`runs/doupo-first5-m2-dev7-20260831`
- 文档 hash：`7ca3fd295b5d0d454ca0b0bac2f4a49f2271602fc8e55bca2f120bb11d85172a`
- 7 个 Chunk 均完成确定性 N3；18 个 exact target packet 保留 50 条 grounded facts。
- N3 发现 5 个 individual describe 池；M2 未从这些池认领事实，因此消费 0、冲突 0，5 个池全部进入 promotion。
- collective promotion task 为 0。
- 5/5 个 DeepSeek promotion 调用成功，模型输出 5 个候选人物；代码最终接受 4 个 promoted character、11 条外貌事实。
- 所有接受事实均为 `match_mode=exact`；人物标签没有 `character_label_span`。
- 1 个任务需要 review：`青衫老者` 的 `青衫` 在剩余池中有 2 个原文 occurrence，无法唯一绑定。代码拒绝整个候选人物并完整保留 3 个未分配片段，没有猜测选择位置。

## promotion 结果

| describe | 模型事实数 | 接受人物 | 接受事实 | 结果 |
|---|---:|---:|---:|---|
| 青衫老者 | 2 | 0 | 0 | review：`青衫` 匹配 2 次 |
| 身穿月白衣袍的老者 | 4 | 1 | 4 | 通过 grounding |
| 男子 | 3 | 1 | 3 | 通过 grounding |
| 少女 | 3 | 1 | 3 | 通过 grounding |
| 黄袍老者 | 1 | 1 | 1 | 通过 grounding |

## 调用与验证

- Provider 调用：5
- 输入 token：10,969
- 输出 token：2,724（其中 reasoning 2,157）
- 总 token：13,693
- Provider failure：0
- promotion grounding issue：1
- Schema 验证：18 个 N3 target packet、5 个 N3 describe pool、5 个 promotion grounded result 均通过。
- 自动测试：90 passed，13 subtests passed。

本报告证明链路执行、来源回放与确定性 grounding 成功，不代表人物归属和外貌语义已经通过人工质量验收。
