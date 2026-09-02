# APPEARANCE-STATE-TRANSITIONS-071 真实运行观察

- Evidence ID：`E-20260902-APPEARANCE-STATE-TRANSITIONS-071-LIVE`
- 日期：2026-09-02
- Provider：DeepSeek（用户已明确授权发送小说原 Chunk）
- 模型：`deepseek-v4-flash`
- 输入：原 M1 Manifest 的 17 个重叠 Chunk；模型 payload 仅 `characters/name/aliases/text`
- 生命周期：Stage 5 `in_progress`，revision 2

## 运行结果

- 首次：15/17 成功，Chunk 2/8 因 `max_output_tokens` 截断。
- 恢复：上限升至 8192，复用 15 个成功缓存，只新增 2 次调用后 17/17 完成。
- 总 Provider 调用尝试：19；最终 17 个成功 trace 的可见 token 合计 46,181，两个截断调用的 usage 未计入该合计。
- 模型事件：8；Grounded transitions：7；Grounding review：1。
- 7/7 Grounded evidence 绝对 span 原文回放；`DocumentCharacterAppearanceStates` Draft 2020-12 实例验证通过。
- 状态产物 SHA-256：`142770FF312DE49C3FD222C899BFACBD0ECA8F4F00AEE2388C9C8BDFB86EC062`
- Chunk 准备产物 SHA-256：`71CBC50BCF21DD52FAC81AE81DC6DC01E66445CEE2EC84A4BC3F0E03E3E74FD0`

## 有效发现

- 准确发现并 Grounding：`素云涛全身青光收敛，收回了自己的武魂附体`，span `[17846,17866)`。
- 模型也发现独狼附体进入事件，但将两个不连续段落拼成一条 evidence；代码以 `evidence_not_found` 拒绝，没有污染 transition。
- 其余 Grounded 项包括唐三转世、体格变结实、赤裸场景、蓝银草收回、老杰克换新衣、唐昊眼含水意。

## 未通过项

- `scene` 没有在生命阶段/章节边界关闭，唐三“全身赤裸”被错误传播到后续事实。
- “蓝银草收回体内”属于武魂/外物状态，不应作为人物 form 长期传播。
- 唐三转世事件的 `after=转世成为五、六岁的男孩` 没有被当前短 evidence 单独充分支持。
- 成功 trace 保存未覆盖两个历史截断调用的 usage，后续需改为追加式 Provider 调用审计。

结论：模型对未知表达的 transition discovery 有实际价值，严格 Grounding 也成功拦住了非连续 evidence；但当前 scope closing、form 边界和语义证据充分性尚未通过质量 Gate，071 不能标记完成。

## dev22 修复与复验

- 运行时：`0.1.0.dev22`；Schema：`3.22.0-draft1`；策略：`full-coverage-roster-grounding-v3`。
- 输入仍为原 17 个 Chunk，每次模型 payload 仍只有 `characters/name/aliases/text`；没有新增 hash、span、ID 或嵌套包装。
- 真实运行 17/17 一次完成，17 个脱敏 trace，10 个模型事件，成功响应合计 46,090 tokens。
- 代码接受 6 个 Grounded transitions，隔离 4 个无法在同一 evidence 内逐字回填的 before/after 改写；6/6 evidence 绝对 span 回放。
- 接受的状态事件：唐三 `life=眼前的这个孩子`；素云涛 `form=独狼，附体` 进入及明确退出；老杰克 `scene=一身新衣服`。
- 物化结果：28 facts 带 life、7 facts 带 form、1 fact 带 scene。scene 只命中换衣同段事实，没有跨段或跨章节传播；蓝银草收回不再进入 form。
- life 更新在代码状态机中同步清空旧 form/scene；form 退出在未明说恢复形态时写为空并物化为 unknown。
- evidence 包含换行会失败关闭；before/after 必须在同一 evidence 内唯一、有序映射。仅省略标点时，代码把状态短语恢复为对应的单一连续原文片段，例如 `独狼附体` 恢复为 `独狼，附体`。
- 保存的模型输出在断点恢复时重新执行当前 Grounding；dev22 离线重放 17/17，新增 Provider 调用 0，Grounded transitions 由 5 更新为 6。
- Provider trace 改为追加式保存，失败调用和后续恢复不会再被最终成功记录覆盖。
- 自动验证：160 tests + 13 subtests，compileall，Draft 2020-12 Schema 与 `AppearanceTransitionChunks` / `DocumentCharacterAppearanceStates` 两个实例，`git diff --check` 全部通过。
- 最终状态产物 SHA-256：`F22B4F29B8E7B3C9D3CEA9AF085140F6A3CFB6CF3850F4F6B799A8508A1EEFFE`。
- 最终 Chunk 产物 SHA-256：`1BFB43AD8B636431FBEA1ACF5B6A809C0691EF2F97FA193D90BCFB9C45F77F87`。

结论：上一轮已知的 life/scene/form 传播、外物误收和非连续证据问题均已关闭，071 在当前范围通过。该结论不替代 075 的正式人工标注质量 Gate。
