# 项目进度

## 当前任务

| 任务 | 状态 | 结果 |
|---|---|---|
| PIPELINE-V3-SIMPLIFIED-039 | completed | 新流程契约和机器 Schema 已建立 |
| PROJECT-V3-CLEAN-START-040 | completed | 旧工程资产已退出当前工作目录，新项目只保留契约和最小治理文件 |
| PIPELINE-MENTION-CLARITY-041 | completed | exact/describe/null、exact×describe M2 和 N3 describe 消费循环已写入契约与 Schema |
| MENTION-SUFFIX-RULE-042 | completed | 用户确认使用 *女子 等泛称后缀规则归一 describe |
| UPSTREAM-NOVEL-CHARACTERS-043 | completed | 固定保存 novel-characters Skill 上游参考副本、许可证和精确 commit，不接入运行时 |
| PIPELINE-V3-REVIEW-HARDENING-044 | completed | 审查与调研边界已进入契约，Schema 升级到 3.2.0-draft1 |
| MODEL-BOUNDARY-BATCHED-M2-045 | completed | M1/M2 已统一四层模型边界；M2 改为每个 exact 一次携带全部 describe；Schema 升级到 3.3.0-draft1 |
| REMAINING-DESCRIBE-PROMOTION-046 | completed | 未被 exact 消费的 describe 单独进入 M2，一个池可建立多个 promoted 本地人物；Schema 升级到 3.4.0-draft1 |
| M1-RUNTIME-FOUNDATION-047 | completed | Python 0.1.0.dev1 骨架、重叠 Manifest、M1 DTO/提示词/Provider 边界、grounding 与 23 项测试已建立 |
| M1-DEEPSEEK-PROVIDER-048 | completed | DeepSeek Responses API/json_schema、脱敏 trace、有界重试、探测 CLI 与 43 项总测试已建立；未运行真实 API |
| M1-DOULUO-LIVE-RUN-049 | completed | DeepSeek smoke 成功；斗罗大陆前20章按 17 块完成 M1，交付模型输出、grounding、Manifest 与 summary；45 项测试通过 |
| M1-OUTPUT-DIAGNOSIS-050 | completed | 对真实 M1 输出完成错误分类：确认缺章输入、quote whitespace false negative、occurrence 锚点缺失、语义噪声、类型冲突和续跑审计失真；形成分级修复路线 |
| M1-GROUNDING-SCOPE-051 | completed | 按用户决策取消 mention occurrence 位置，增加 type/scope、纯空白等价 Grounding、raw quote 回填与 collective quarantine；51 项测试通过 |
| M1-DOUPO-LIVE-RUN-052 | completed | 斗破苍穹前5章按新契约完成 7/7 Chunk；分别交付模型输出与 grounded packet；37 mentions、94 evidence bindings、0 rejected |
| N2-EXACT-PRECEDENCE-053 | completed | exact raw evidence 优先过滤全部 describe；空块删除、hash 重算、独立 trace/summary；斗破离线重放删 37 bindings/13 blocks，57 项测试通过 |
| M2-MINIMAL-FACT-SCHEMA-054 | completed | M2 模型边界精简为肯定事实；60 项测试和 Schema/治理验证通过，运行时待实现 |
| M2-RUNTIME-FOUNDATION-055 | completed | M2 exact attribution 与 remaining-describe promotion 双模式运行时完成；Schema 3.8/runtime dev7，77 项测试通过，真实 Provider 调用 0 |
| M2-DOUPO-LIVE-RUN-056 | completed | 斗破前5章最新 N2 重放后完成 M2 exact attribution 18/18；50 模型事实全部 grounded，0 issue/0 failure；runtime dev8，81 项测试通过 |
| N3-PROMOTION-DOUPO-RUN-057 | completed | N3 7 Chunk/18 target/50 facts；5/5 promotion 成功，接受 4 人物/11 facts，`青衫` 重复 quote 进入 review；runtime dev9，90 项测试通过 |
| DOCUMENT-EVIDENCE-QUOTEHASH-058 | completed | N2 packet v6 删除逐 quote hash；文档绝对 span、回放和重叠安全去重完成；斗破 61→60 facts，96 项测试通过 |
| PROMOTION-PARTIAL-ACCEPTANCE-059 | completed | Promotion 事实级部分接受与离线重放完成；青衫老者安全事实恢复，歧义青衫仍 review；98 项测试通过 |
| CROSS-CHUNK-IDENTITY-060 | completed | 完整 local/promoted 节点、有界候选、M3 最小关系判断、严格 Grounding、cannot-link/N4 注册表、可恢复批处理与离线斗破准备完成；109 项测试通过，真实 Provider/身份质量 Gate 未运行 |
| M3-DOUPO-LIVE-EVAL-061 | completed | DeepSeek M3 19/19 完成；17 same/2 uncertain，11 个全局人物、5 linked、2 review；36 条身份引用全部回放，发现同名证据语义充分性和失败历史覆盖缺口 |
| DOCUMENT-CHARACTER-PROFILES-062 | in_progress | 确定性 registry/evidence join、统一人物档案、Schema/CLI/测试和斗破离线实跑进行中；Provider calls 必须为 0 |

## 阻塞项

- 真实 API 链路已验证，但 M1 模型质量尚未通过人工标注集评测。
- 身份层当前无阻塞；同名不同人、`different`/`cannot-link` 和证据充分性属于已知覆盖缺口，按用户决定等真实失败案例出现后重开，而非阻塞下一阶段。

## 下一步

1. 设计并实现 `document-character-profiles.json`：以 `document-character-registry.json` 的全局人物为主表，回填 `document-character-evidence.json` 的完整人物事实。
2. 对每个人物保留标签、成员局部人物、事实原文、绝对 span、来源 Chunk、多来源 occurrence、冲突和 review；所有拼装与校验均由确定性代码完成。
3. 加入事实引用完整性、span 原文回放、孤儿 fact、重复 fact 和零外貌事实人物测试，并用斗破既有产物离线实跑，不调用 DeepSeek。
4. 档案结构稳定后，再决定是否实现时间/场景外貌状态，以及可选的自然语言人物总结或图像提示词。

## 进度历史

- 2026-08-31：用户确认斗破当前身份结果可接受；同名不同人、`different`/`cannot-link` 不再作为当前阻塞，未来以真实失败案例触发重开和回归。F-NEW-IDENTITY-006 按当前范围完成，下一阶段转向确定性人物档案组装。
- 2026-08-31：斗破前 5 章真实 M3 运行完成。沙箱内预尝试因网络限制 19 项失败且未获得 HTTP 成功；允许联网后首轮 18/19 成功，1 项因 4096 max output 截断；提高到 8192 后恢复 18 项、仅重试 1 项并完成。最终 17 same/2 uncertain/0 different，11 global characters、5 linked、6 singleton、2 review、0 unresolved/cannot-link。36 条身份证据绝对 span 全部回放；成功 trace 汇总 60,610 tokens。人工检查未见明显错组，但确认 same 引用常只是两个上下文分别出现同名，不能替代同名不同人评测。
- 2026-08-31：完成跨 Chunk 身份纵向切片。新增完整 local/promoted 节点目录、有界候选、最小 M3 三态模型边界、严格/纯空白等价身份证据 Grounding、cannot-link、冲突保留、全局注册表和可恢复批处理。斗破现有 N2/N3/文档事实零 Provider 准备得到 23 nodes（含 1 个零事实 exact）、1 deterministic edge、19 tasks，每节点最多 2 个；模型输入系统字段扫描为 0，109 项测试与 Draft 2020-12 实例验证通过。Stage 5 保持 in_progress，真实身份模型质量未评测。
- 2026-08-31：根据明确评测失败实现 promotion 事实级部分接受。唯一事实不再被同人物的歧义事实连带删除；歧义项显式记录 character/fact index、fact quote 与候选 occurrence 数，并保留全部未分配片段。新增无 Provider 的保存模型输出重放 CLI。斗破 5 个旧模型输出离线重放后 promoted characters 4→5、facts 11→12；`青衫老者/浑浊的老眼` 进入文档事实 `[7366,7371)`，两处 `青衫` 仍 review。统一文档事实 60→61；98 项测试、62/62 span 回放和 Schema 校验通过。
- 2026-08-31：实现 `document-character-evidence-v1` 确定性汇总和 CLI。所有事实/evidence 以 `chunk_start + local_span` 换算并逐字回放；只对同来源、同人物标签、同文档位置、同原文和同结构的重叠副本去重，保留全部 source occurrences。斗破 61 条输入事实得到 60 条文档事实（49 exact、11 promoted），`萧熏儿/微笑的小脸` 的两个重叠 Chunk 来源合并为一条；96 项测试、实例 Schema、治理和 Lifecycle 校验通过。N2 packet 升到 v6，取消逐 quote hash；Stage 5 仍因人工质量 Gate 未完成而保持 `in_progress`。
- 2026-08-31：实现 N3 span 仲裁、冲突隔离、剩余池重建及可恢复 promotion 批处理/CLI。斗破 7 Chunk 汇总 18 target/50 exact facts、5 describe pools、0 consumption/0 conflict；5/5 promotion 成功，接受 4 人物/11 facts，`青衫` 因两个 occurrence 进入 review 并保留原片段；90 项测试和 Schema 实例校验通过，实跑不代表人工质量 Gate。
- 2026-08-31：斗破前5章从旧 M1 model output 重放最新 N2（18 exact、5 individual describe、1 collective、57 bindings），完成 DeepSeek M2 exact attribution 18/18；50 条模型事实全部严格逐字 Grounding，45 条 unique quote，0 歧义/越界。首次执行 5 个任务后遭遇 `IncompleteRead`，补齐瞬态重试并恢复完成剩余 13 个；未运行 N3/promotion，实跑不代表人工质量 Gate。
- 2026-08-30：完成 M2 双模式运行时：E 个 exact 各生成一次携带全部 D 个 individual describe 的结构化任务；代码以统一严格/纯空白等价规则回填事实来源，describe 歧义失败关闭；每个 remaining describe 可稳定 promotion 一到多个人物并拦截跨人物重叠。Schema 3.8、runtime dev7，77 项测试通过，未调用真实 Provider；N3 未实现。
- 2026-08-30：按用户决定将 M2 模型输入输出精简为无 ref/span/状态的肯定事实；模型只返回 `belongs_to_target` 下的 `fact_quote/category/attribute/value`，代码负责唯一绑定、归并、冲突和 describe 消费；Schema 目标 3.7，运行时尚未实现。
- 2026-08-30：实现 N2 `exact-evidence-precedence-v1`；Grounding 后 exact 对同文 describe evidence 优先，空 describe block 删除，独立 trace 与 summary 计数落盘；Schema 3.6/runtime dev6，斗破离线重放 94→57 bindings，57 项测试通过。
- 2026-08-30：斗破苍穹前5章完成新契约真实回归；修复 CLI CRLF 归一化并升至 dev5，8192 预算断点续跑后 7/7 Chunk 成功，37 mentions、94 evidence bindings、1 collective、0 rejected；52 项测试通过。
- 2026-08-30：按用户确认的简化边界移除 mention occurrence 数量/位置，M1 增加 `mention_scope`；Grounding 只容忍 Unicode 空白差异并回填 raw source quote，collective 进入 quarantine；契约 3.5、运行时 dev4，51 项测试通过，未调用真实 Provider。
- 2026-08-30：复核真实 M1 输出并对照 `develop-ai-agents` 与上游 `novel-characters`；确认文件实际仅 1–19 章、149 为 evidence bindings 而非独立引文、49/60 mention 块缺 occurrence-specific 锚点、reasoning 占 output 92.4%，并冻结先修确定性层再建回归集的路线。
- 2026-08-30：DeepSeek 真实 smoke 成功；`斗罗大陆前20章` 以 2,500/250 分块策略完成 17/17 M1 Chunk，得到 63 个候选、60 个 grounded mentions 和 149 条已定位证据；新增可恢复批处理器，总计 45 项测试通过。
- 2026-08-30：建立 DeepSeek Responses API Provider，默认 `deepseek-v4-flash` + `json_schema`；实现 HTTPS/环境配置、脱敏 trace、429/5xx/网络错误有界重试、非瞬态失败关闭和显式探测 CLI，总计 43 项测试通过，真实 API 调用为 0。
- 2026-08-30：建立 Python `0.1.0.dev1` M1 运行时基础；Provider 只接收 `chunk_text`，输出经严格字段校验、Chunk 信封回绑和 N2 grounding，23 项确定性测试通过。
- 2026-08-30：用户纠正剩余 describe 的语义：N3 后不再回给 exact，而是每个剩余 describe 单独进入 M2，并允许按剩余证据拆成多个正式本地人物。
- 2026-08-30：用户确认所有模型阶段都应隔离系统字段；M1/M2 改为代码信封、最小模型输入、最小模型输出和代码回填四层，M2 调用粒度改为每个 exact 一次携带全部 describe。
- 2026-08-30：结合技术审查与开源调研补齐 exact 称号边界、evidence relation、四层 span、非重叠仲裁、pair 缓存、原始 hash、重叠分块和显式截断；Schema 升级到 3.2.0-draft1。
- 2026-08-30：按用户要求将 `eternityspring/shuohao-skills` 的 `novel-characters` 固定在 commit `4322897e6d2bdaf66365534fd40194360c75a85f`，作为只读对照资料；当前 M1 优先级和 V3 契约不变。
- 2026-08-30：确认 `红衣女子` 可通过 `*女子` 后缀规则归一为 describe；实现约定使用 `endswith`，明确名称优先拆成最小 exact 提及。
- 2026-08-30：用户新增 exact/describe/null 规则；所有 describe 与所有 exact 组合进入 M2，N3 唯一认领后消费 describe 片段，剩余片段继续细分。
- 2026-08-30：用户确认当前分支不保留旧代码和旧文档，项目按新流程完全重新开始。
