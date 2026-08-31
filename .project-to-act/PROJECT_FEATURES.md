# 项目功能

## 状态定义

- `completed`：契约或工程已完成并通过对应验证
- `in_progress`：已有可运行部分，但仍缺少当前功能的外部接线或验收
- `planned`：尚未实现

## 功能清单

| ID | 功能 | 状态 | 说明 |
|---|---|---|---|
| F-NEW-DESIGN-001 | 简化人物证据契约 | completed | exact 边界、统一模型边界、重叠 Manifest、代码侧 span、task cache、raw hash 与 N3 span 仲裁 |
| F-NEW-M1-002 | 人物提及与证据归拢 | in_progress | DTO、type/scope 提示词、collective quarantine、DeepSeek Provider、CRLF 保真读取、可恢复全文批处理、严格输出校验和 Chunk 信封回绑已实现；斗破前5章新契约实跑通过，待人工评测 |
| F-NEW-N2-003 | 原文存在性验证与确定性去冗余 | completed | occurrence span、严格/空白等价匹配、raw provenance、exact→describe 优先、绝对 span 换算、重叠 Chunk 安全去重与多来源保留已实现；逐 quote hash 已删除 |
| F-NEW-M2-004 | 双模式外貌拆解 | in_progress | exact attribution 与 remaining-describe promotion 已接线；promotion 支持事实级部分接受和离线重放，斗破得到 50 exact Chunk facts 与 12 promoted facts；待人工质量验收 |
| F-NEW-N3-005 | 证据三态与 span 仲裁 | completed | Chunk 内 direct exact 归并、describe 唯一消费、跨 exact 重叠冲突、剩余池重建、collective 隔离及可恢复 promotion 已实现并实跑 |
| F-NEW-IDENTITY-006 | 人物引用与记忆绑定 | completed | 运行时与斗破真实 M3 已完成：19/19 tasks、17 same/2 uncertain、11 global characters、5 linked、2 review；原文 Grounding 全通过，用户接受当前真实样本范围；同名不同人/different/cannot-link 在真实案例触发时重开 |
| F-NEW-PROFILE-007 | 文档人物档案组装 | in_progress | DOCUMENT-CHARACTER-PROFILES-062 已启动；纯代码按同文档 guard + fact_hash join 汇总全局人物、完整事实、绝对 span、原文、多来源、冲突和 review，不新增模型调用 |

## 功能变更历史

- 2026-08-31：用户授权开发文档人物档案层。任务冻结为确定性连接：先验证 registry/evidence 文档身份，再按 `fact_hash` 物化完整事实；缺失、冲突或 quote 不一致失败关闭，零事实人物和未绑定事实保留，不调用模型。
- 2026-08-31：用户接受斗破当前身份结果，不提前为尚未出现的同名不同人和 `different`/`cannot-link` 扩展策略；身份功能按当前范围完成，真实失败案例作为重开触发器。下一阶段候选为确定性人物档案组装。
- 2026-08-31：斗破真实 M3 19/19 完成并生成注册表。最终聚合萧炎、萧薰儿/萧熏儿/熏儿、萧战、葛叶、纳兰嫣然五组，六个单例保持独立；36 条身份证据全部原文回放。发现 Grounding 真实性与身份证明充分性必须分开评测，当前同名不同人和 cannot-link 尚无真实覆盖。
- 2026-08-31：完成跨 Chunk 身份运行时纵向切片。模型每次只比较一个 current/candidate，输入输出不含 ref/ID/span/hash；同名、字形相似和相似事实只召回候选。same/different 必须有安全 Grounding 的逐字原文，different 写入 cannot-link，多 same/uncertain 进入 unresolved/review；全局 ID、成员 ref、fact 引用与冲突均由代码生成。斗破离线准备为 23 nodes、1 deterministic edge、19 bounded tasks、Provider calls=0；真实模型精度未验收。
- 2026-08-31：用户授权实现跨 Chunk 身份层。选择本地节点→有界候选→M3 单候选关系判断→N4 Grounding/聚类→全局注册表；同名和泛称不自动合并，模型不处理系统身份字段，人物档案与事实汇总由代码生成。
- 2026-08-31：根据斗破评测将 promotion 改为 `promotion-partial-fact-acceptance-v1`。人物内唯一匹配事实保留，歧义/不存在事实逐条 review 且不猜 occurrence；只有标签无效、零安全事实或跨人物重叠才整人物拒绝。旧模型输出可离线重新 Grounding；斗破 `青衫老者` 保留 `浑浊的老眼`，两处 `青衫` 继续未分配。
- 2026-08-31：新增纯代码 `document-character-evidence-v1` 汇总：Chunk 局部事实/evidence span 换算为文档绝对 span并逐字回放，按人物来源、标签、文档位置和完整事实结构安全去重；斗破 61→60 facts，唯一合并项保留两个 Chunk occurrence。N2 packet v6 删除 `quote_hash`/`mention_quote_hash`，保留 chunk/document/packet/fact 与审计 hash。
- 2026-08-31：实现 N3 Chunk 局部 span 仲裁和可恢复 promotion 批处理。N2/M2 上游产物不可变；唯一无冲突 describe facts 才消费，不同 exact 重叠 claim 隔离，非冲突剩余池才 promotion；人物标签可复用 mention quote 且不保存标签位置。
- 2026-08-31：新增从既有 M1 run 重放最新 N2 并可恢复执行 M2 的批处理/CLI，模型输出、grounded 输出、N2 重放、trace、失败、摘要和运行历史分离；Provider 增加 HTTP chunked `IncompleteRead` 瞬态重试。
- 2026-08-30：实现 M2 双模式运行时。每个 exact 一次携带全部 individual describe；fact_quote 优先绑定 target，否则仅接受唯一 describe occurrence；promotion 支持一池多人物、稳定排序、标签/事实唯一绑定、跨人物重叠拦截与未分配残片保留。模型仍不读取 ref/span/hash/状态。
- 2026-08-30：M2 两种模型模式移除 ref、span、assessments、attribution/epistemic 状态和 support/claimed 字段；归属模式只输出 `belongs_to_target` 外貌事实，代码执行安全唯一绑定、冲突和消费。
- 2026-08-30：N2 新增 versioned exact evidence precedence；过滤所有 describe 同文副本、删除空块、重算 hash，并输出独立 trace/summary 计数。M1 model output 不变。
- 2026-08-30：CLI 文件读取禁止 universal-newline 归一化；斗破苍穹前5章以原始 CRLF 完成 7 Chunk M1 回归，模型/阶段输出分别保存。
- 2026-08-30：M1 新增 `mention_scope`，collective 保留证据但隔离于单人物后续流程；N2 evidence 支持纯空白等价安全恢复并回填 raw quote，人物称谓 occurrence 数量和位置被移除。
- 2026-08-30：新增 `run-deepseek-m1` 可恢复批处理命令，逐块保存 validated model output、grounded packet 与脱敏 trace；真实 37,655 字样本完成 17/17 Chunk。
- 2026-08-30：M1 接入 DeepSeek Responses API；默认 `deepseek-v4-flash`，API Key 由环境注入，trace 不保存 Key、正文、Prompt 或 reasoning，瞬态失败执行有界重试。
- 2026-08-30：M1 运行时基础开始实现；模型可见 payload 限定为 `chunk_text`，系统字段由信封保留，validated output 才能进入确定性 grounding。
- 2026-08-30：剩余 describe 不再进入 exact 归属循环；每个剩余池单独进入 M2，一个池允许按不重叠证据创建多个 promoted 本地正式人物。
- 2026-08-30：所有模型阶段禁止接收/输出来源版本、Chunk ID、hash、cache key 和 trace；M2 从 exact×describe 单独调用改为每个 exact 一次批量携带全部 describe。
- 2026-08-30：审查与调研后将 N3 消费单位冻结为 Chunk 字符 span；重叠分块必须有 Manifest 和显式截断状态；packet hash 禁止隐式文本归一化。
- 2026-08-30：采用泛称后缀匹配；例如红衣女子命中 `*女子` 后归一为 describe。N2 归一不删除 evidence，只记录 trace。
- 2026-08-30：当时将 describe 定义为非人物证据池、只有 exact 生成 local_character_ref；该决定已被 `REMAINING-DESCRIBE-PROMOTION-046` 部分替代：第一轮仍是证据池，N3 后剩余 describe 可以建立 promoted 人物。
- 2026-08-30：旧工程功能全部退出当前分支功能清单，新项目从 M1 开始实现。
