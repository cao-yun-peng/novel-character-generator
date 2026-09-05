# RENDER-PROFILE-COMPILER-074 验收证据

## 架构边界

- 输入限定为完整 dev18 fact groups、dev24 appearance states、dev25 Label/Review projection 和显式 compile requests；来源层不回写。
- `character_id + life/form/scene + document_position` 必须唯一命中一个半开 StateSegment。缺位置、歧义或无匹配时 traits 为空，不跨时期/形态混合。
- 未来 observation 被 position cutoff 排除。stable/persistent、scene/momentary 与 unknown 使用版本化 applicability 规则。
- unknown persistence 和仅有章节上界的 scene 只能成为 provisional，并在主 traits、fact IDs、provenance 和 warning 中显式标记。
- 只有两侧均确定 active 的 `true_conflict` 才进入 `unresolved_conflicts`；provisional overlap 与 `unclassified` 只生成 warning。
- 本任务只输出结构化人物卡，不生成性格、性别、服装补全、视觉风格或自然语言 Prompt；Provider 调用为 0。

## 实现证据

- 新增 `render_profile_compiler.py`、`build-render-ready-character-profiles` CLI、`render-profile-compile-requests-v1` 与 `render-ready-character-profiles-v1` Schema。
- 编译前重新验证文档 hash/coverage、fact quote 与 raw occurrence span、Chunk hash、transition ID、StateSegment 重建、relation/proposition 重建和 label roster。
- 输出包含 identity labels、active/provisional fact IDs、stable/variant/scene traits、相关 transitions、scope conflicts、聚合 warnings 与逐 fact 完整 provenance。
- 单测覆盖四状态分卡、未来/跨状态隔离、momentary/unknown 规则、selector_required/no_match 空输出、active true-conflict gate、unclassified warning、跨层篡改失败关闭、数组重排稳定性和文件运行器。

## 真实确定性构建

- Requests SHA-256：`EAC5431555DC6FB042CB6E0DFF3E89D53E406A36077978AA623971A84CB8F685`。
- 四个 selector：唐三前世位置 300、唐三儿童位置 37690、素云涛普通位置 13990、素云涛独狼附体位置 17845。
- 4/4 compiled，均因 unknown state/persistence 或未分类关系带显式 warning；0 selector-required，0 no-match。
- 7 active、40 provisional fact bindings；2 stable traits、33 variant traits、10 scene overrides；4 相关 transitions。
- 0 unresolved conflicts；17 聚合 warnings，分布为 unknown life 3、unknown form 3、unknown scene 4、provisional applicability 4、active unclassified 1、provisional unclassified 2。
- 重复构建 artifact SHA-256 均为 `B0EF3F6F47716F2CE2DBD133EDA5FF8E5738E0E4598BE9B93BBB38DD01629A3B`；`model_calls=0`。

## 验证

- `191 passed, 13 subtests passed`。
- `python -m compileall -q src tests` 退出码 0。
- Draft 2020-12 meta-schema、`RenderProfileCompileRequests` 与真实 `RenderReadyCharacterProfiles` 实例通过。
- 重排 fact/state/label/request 数组后输出对象完全相同；真实 CLI 连续两次输出字节级 hash 一致。
- 最终 `git diff --check`、Project-to-Act `--validate` 与 Agent lifecycle `validate` 退出码均为 0；Stage 5 Gate 决策为 `passed`，当前 Stage 6 `ready`、revision 3。

## 已关闭的中间失败

- 首轮新增测试在 fact span 的半开 `end` 位置要求 unknown fact 为 active，得到 1 failed/8 passed；按半开区间契约修正为 provisional，最终通过。
- 首轮真实 Schema 校验发现复用的 `identity_labels` 少了 `character_id`；补齐该字段、增加回归断言并重新生成后，Schema 通过。
- 最终复验首次调用因系统 pytest 临时目录无权限以及 PowerShell 展开 `$defs` 而失败；测试切换到工作区专用 `--basetemp`，Schema 引用改为运行时拼接后，同一检查分别以 191 tests/13 subtests 和真实实例通过关闭。

本证据已支持 Stage 5 工程纵向切片退出，不替代 Stage 6 的冻结人工标注集、正式阈值或模型一般化质量结论。
