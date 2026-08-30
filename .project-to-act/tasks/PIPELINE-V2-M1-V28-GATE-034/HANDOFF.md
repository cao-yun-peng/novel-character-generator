# M1 Prompt v2.8 双集回归交接

## 已完成

- 已获用户明确外发授权并完成短集 16 条、真实集 10 条 Provider 运行。
- 短集 16/0/0；真实集 2/5/3；完整 outputs、reports、run manifests 和哈希已保存。
- v2.8 让 009 的前三段连续 transformation 保持复合候选，未再出现 v2.7 的 transformation 原子化缺口；真实 candidate precision 和 evidence recall 均提升。

## 未通过项

- 005：短“青衫老者”引文非唯一，触发 deterministic validation，且少年脸貌仍漏。
- 006：用户复审确认相对年龄内容没有问题；现有 fail 仅由金标跨度口径造成，不作为 Prompt 缺陷。
- 009：用户复审确认连续 transformation 与回到女孩形态内容没有问题；现有 fail 仅由 owner alias 口径造成，不作为 Prompt 缺陷。
- 005：金标 `一名青衫老者` 唯一且正确；模型输出裸 `青衫老者`，该短语在 Chunk 中出现两次，另漏 `少年稚嫩的脸庞`。
- 真实集质量 Gate 仍 blocked_pending_user_review；不得生成 active Observation。

## 下一步

- 用户继续审查 005 的唯一定位规则与少年脸貌召回，决定是否强化 Prompt 或维持当前严格 deterministic validation。
- 006/009 不再作为待修 Prompt 问题；除非用户明确改变测量口径，否则不修改 Dataset/Rubric。
