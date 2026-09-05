# dev30 自动场景／换装识别与冲突闭环

日期 2026-09-05；任务 AUTO-SEMANTICS-CONFLICT-080；runtime 0.1.0.dev30，Schema 3.30.0-draft1。

## 已实现的运行链路

`build-automatic-semantics` 复用既有完整 Chunk manifest，自动创建两类模型任务：

1. 每个原文块读取已知人物标签、可引用的既有事实和该块全文，识别 scene_boundary、wear、remove、replace、continuity、uncertain_gap、momentary_end。
2. 按同人物、同 category、同 exact attribute 建立不同值的事实对，比较 incompatible／compatible／equivalent／uncertain。候选可跨观察 StateSegment，避免把“观察位置不同”误当成“不会同时有效”。

模型只读取名字、事实语义与连续原文，不读取或输出内部 ID、span、hash。输出 facts 使用原输入的 fact_quote/category/attribute/value；代码必须唯一绑定原有事实。重复证据位置、重复事实描述、跨人物、未来事实、不合法类别或改写证据均进入 review，不默认取首个匹配。

事件识别、Grounding、保存、续跑、离线重放和 Snapshot 消费都已接线；分类 Prompt 明确区分衣着层次、部位、静态观察、穿上、脱下、时间跳跃与段落边界。代码仍不能仅凭逐字回放证明模型语义正确。

## R03 事件如何影响查询

- scene_boundary 建立独立 narrative_scene 边界；它可以关闭非衣着的 scene 持续事实，但不会使衣服或配饰失效。life 切换清空此前叙事场景。旧 StateSegment 的 scene 字段及选择器继续表示历史层，自动识别的叙事场景在 narrative_scene 字段呈现，不回写旧状态源。
- remove/replace 指明要关闭的旧事实，在 evidence.end 生效。内衬、不同层次和其他配饰不一起清空。
- wear 只记录原文范围内已存在的新衣着观察；不会捏造未抽取到的事实，也不会把新衣服当作“所有旧衣服都已脱下”。事件保留在 semantic_events 供证据查看。
- continuity 只在被证据覆盖的半开区间内使指定事实 active；不得用沉默推断持续。
- uncertain_gap 将受影响事实降为暂定；momentary_end 关闭已有瞬时状态。
- 重叠 Chunk 的同一事件按内容去重。未知/失败定位保持复核，不猜部位或 occurrence。

当早期事实在后续块已不再出现时，事件任务仍能引用这些历史观察；首版没有为长篇截断候选，调用预算与长篇优化仍受 R14 管理。

## R02 真冲突的生成与消费

持久化语义输出使用 incompatible，不能仅凭模型说“不兼容”就登记 true_conflict。每条 incompatible 必须有两侧原文证据、覆盖对应 fact span，并且在来源 evidence 域中唯一定位。

Snapshot 再使用 R03 有效期规则计算双方是否纳入：

| 时点结果 | 冲突行为 |
|---|---|
| 两侧都是 active | 生成 true_conflict / active_overlap，引用当前 StateSegment 与两侧 canonical facts |
| 至少一侧 provisional | 不生成真实冲突，产生 provisional_incompatible_relation warning |
| 未来观察、不同 life/form、已替换／脱下、瞬时过期 | 不生成真实冲突 |
| 模型 uncertain 或证据被拒绝 | 保留语义未决或 review，不强判 |

同部位、单件物品、左右差异、否定作用域、比较/假设/传闻等属于受约束模型语义判断；Prompt 要求不明确时 uncertain。equivalent 结果不自动合并旧 propositions，避免把模型输出当作新的可变事实源。对于已明确裁决的事实对，不重复显示旧 baseline 的 unclassified warning。

产物包含 semantic_evidence、semantic_events、semantic_reviews 与 narrative_scene；raw facts、Registry、StateSegment observation、旧关系记录保持不变。查询从自动产物重新校验来源 hash、事件绑定和两侧证据，不信任保存的派生位置。

## 执行方式

既有 DeepSeek Provider 环境配置沿用原项目。以下 PowerShell 参数使用已有斗罗产物：

```powershell
$semanticArgs = @('--input-file', 'tests/小说/斗罗大陆前20章.txt', '--fact-groups-file', 'runs/douluo-20ch-e2e-dev13-20260831/post-link-fact-groups-dev18/document-character-fact-groups.json', '--appearance-states-file', 'runs/douluo-20ch-e2e-dev13-20260831/snapshots-dev29/document-character-appearance-states.json', '--label-projection-file', 'runs/douluo-20ch-e2e-dev13-20260831/label-review-projection-dev25/document-character-label-review-projection.json', '--chunk-manifest-file', 'runs/douluo-20ch-e2e-dev13-20260831/m1/manifest.json')
python -m novel_character_generator build-automatic-semantics @semanticArgs --output-dir 'runs/semantic-dev30/douluo-live' --max-new-calls 52
```

上面命令会调用模型，需预先配置 Provider 环境变量。081 已通过加载本地环境的任务脚本完成实跑，结果见 [实测报告](42-semantics-live-validation.md)。

预览时使用新目录和 `--prepare-only`，不创建 Provider、不读取密钥。当前斗罗计划为 17 个原文块事件任务、35 个关系任务，共 52 个；已保存于 `runs/semantic-dev30/douluo-preparation/`。

续跑使用原输出目录，预检全部已规划任务的完整请求指纹后才允许新调用；模型/Prompt/生成参数变化需新目录。预算不足时在任何新调用之前拒绝整批缺失任务。已保存模型响应会重新 Grounding，即使上次定位失败也保留原响应供复核。

离线重放添加 `--replay-dir <原结果目录>`，输出必须是尚不存在的新目录；所有响应必须已保存。离线模式不创建 Provider、不补缺失调用、不冒充新模型结果。失败 Provider 使产物 complete=false，Snapshot 拒绝消费；已返回模型的部分语义被拒绝时保留 review 并在快照显式 warning。

查询或旧人物卡编译时添加：

```text
--automatic-semantics-file runs/semantic-dev30/douluo-live/automatic-semantics.json
```

两个命令 `build-character-snapshot` 和 `build-render-ready-character-profiles` 均已接线；Python 对应参数为 automatic_semantics。新 Snapshot policy 为 automatic-semantic-snapshot-v2，精确自动产物参与 artifact_set/snapshot ID；缺少该参数时继续使用原确定性基线。

## 验收和限制

工程回归：259 tests、19 subtests 通过。测试覆盖自动事件到 Snapshot、语义判断到 true_conflict、暂定不冲突、替换不冲突、证据两侧校验、重复定位、模型 metadata 隔离、预算、缓存、离线重放、失败产物和 Schema。

`runs/semantic-dev30/scripted-conflict-regression/` 保存了注入可控模型响应的工程样例：provisional.json 为 0 冲突，active-conflict.json 为 1 冲突。它验证代码链路，不作为模型准确率证据。

081 更新：真实小说 52 个任务已完成，累计 Provider 调用 53 次（含一次截断失败），dev31 零调用重放并通过 4 个 Snapshot；R03/R02 工程链路已交付，真实识别召回率、事件绑定率、同槽位判断、否定精度与总体模型质量仍需 R06 冻结集评测。未新增远程发布、人工决策 API 或 R09 原子 run 发布 manifest。全量事实对在长篇可能较多，先用 prepare-only 审查预算再实跑。

实测发现重复 evidence_quotes 会导致保存关系与重新定位不一致；dev31 在 Grounding 时按首次出现顺序去重。原 dev30 实跑产物保留审计，查询应使用 `runs/semantic-dev30/douluo-live-replay-dev31/automatic-semantics.json`。
