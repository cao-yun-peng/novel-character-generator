# 斗破苍穹前 5 章 M3 身份运行诊断

## 运行结论

- 计划任务：19
- 最终成功：19
- 最终失败：0
- Grounded 关系：17 `same_character`、0 `different_characters`、2 `uncertain`
- 身份引用：36 条，全部按文档绝对 span 逐字回放通过
- 注册表：11 个全局人物；5 个 linked，6 个 singleton
- 复核项：2
- unresolved bindings：0
- cannot-link：0
- Provider：`deepseek-v4-flash`

第一次在受限网络环境中尝试时，19 个任务均为网络瞬态失败且未获得 HTTP 成功响应。允许联网后的首次真实批次完成 18 项；一个“萧炎→萧炎”任务得到 HTTP 200 但因 `max_output_tokens=4096` 截断。把该次进程预算提高到 8192 后断点恢复 18 项，仅重试并完成这一项。

最终成功任务 trace 的 token 汇总为：input 41,423、cached input 10,112、output 19,187、reasoning 17,854、total 60,610。截断响应没有返回可计量 usage，不包含在该汇总内。真实 API 收到 19 个成功响应和 1 个截断响应。

## 最终人物组

### linked

- 萧炎：5 个 local refs，12 个 appearance fact refs
- 萧薰儿：5 个 local refs；合并标签 `萧薰儿 / 萧熏儿 / 熏儿`，21 个 appearance fact refs
- 萧战：3 个 local refs，6 个 appearance fact refs
- 葛叶：2 个 local refs，4 个 appearance fact refs
- 纳兰嫣然：2 个 local refs，2 个 appearance fact refs

### singleton

- 萧媚
- 青衫老者
- 身穿月白衣袍的老者
- 男子
- 少女
- 黄袍老者

本样本中没有发现明显的跨人物错误合并。五个 linked 组与前 5 章故事上下文一致；promoted 泛称没有因为都是“老者/男子/少女”而相互合并。

## 两个 review

1. `萧熏儿` 在 Chunk 4 与早期两个 `萧薰儿` 候选均返回 `uncertain`。该节点后来通过 `熏儿 → 萧熏儿` 和其他 `萧熏儿 → 萧薰儿` 的安全边进入同一全局组，所以没有 unresolved binding，但保留 `insufficient_identity_evidence` review。
2. `熏儿 → 萧熏儿` 的一项模型引用仅为 `萧熏儿`，在可见上下文中有多个 occurrence，因此进入 `ambiguous_identity_evidence`；另一条唯一引用 `熏儿虽然也姓萧` Grounding 成功，关系按部分接受保留。当前 review 汇总会重复列出两条 same decision 共同拥有的相同证据，这是展示层去重缺口，不影响聚类结果。

## 质量风险

### 身份引用真实，不等于身份证明充分

Grounding 能证明模型引用确实来自原文，但不能自动证明这些句子足以支持跨 Chunk 同一身份。多个 same 任务给出的证据只是两个上下文分别出现同一个名字，例如分别引用两处“萧炎”。这符合逐字引用，却没有提供直接的跨上下文桥接关系，实质上仍可能主要依赖同名。

因此本批次证明：

- 结构化输出、断点恢复和原文 Grounding 可用；
- 本样本最终聚类表面上合理；
- 尚不能证明“同名不同人”场景安全，不能据此通过身份质量 Gate。

### 候选集没有覆盖 different/cannot-link

19 个候选全部来自同名、姓名变体、标签包含或共享事实。本批次模型没有返回 `different_characters`，注册表也没有 cannot-link。需要补充“同名不同人物”和“相似泛称不同人物”的人工回归样本。

### possible_conflicts 多为粒度差异

当前 4 个冲突主要是值粒度不同，而非真正矛盾：

- 萧薰儿酒窝：`可爱` / `可爱的小酒窝`
- 萧薰儿面容：`稚嫩俏丽` / `美丽`
- 纳兰嫣然外貌：`美丽` / `美丽娇俏`
- 萧炎脸庞：`清秀稚嫩` / `稚嫩`

保守保留是安全的，后续可增加“兼容值/包含值”分类，但不应覆盖原事实。

## 下一步建议

1. 建立人工 identity gold，先标注本次 19 对关系。
2. 增加同名不同人、称号复用、泛称相同但不同人物、一个节点多 same 候选等对抗样本。
3. 将“逐字引用通过”和“语义上足以证明身份”拆成两项指标。
4. 修复 review evidence 展示去重，并保存每次失败详情的追加式历史；当前 `failures.json` 会在成功恢复后被最终空数组覆盖，只有 `run-history.json` 保留失败计数。
5. 在人工 precision、false-merge 和 review-rate 达到阈值前，Stage 5 与身份功能保持 `in_progress`。
