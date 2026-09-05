# 源码问题修复清单与 Web 接口规划

日期：2026-09-05。源码基线：0.1.0.dev26 / Schema 3.26.0-draft1，包含工作区已有的 073/074 未提交实现。

本文是修复与接口设计计划，正在逐步实施；优先级不是完成状态。任务状态以 .project-to-act/PROJECT\_PROGRESS.md 为准，功能状态以 PROJECT\_FEATURES.md 为准。

077/dev27 进展：R01 当前范围已修复；R02 已完成否定包含保护，完整冲突闭环待有效期层；R05 已完成 M1/M2 请求指纹、缓存 Grounding 重验及 M2 独立离线重放，其他阶段与统一迁移待补；R12 测试依赖/入口已更新，独立净环境/CI 待验收；R06 已提供 [标注协议候选](38-quality-annotation-protocol.md)，人工 gold/evaluator/Gate 待完成。其他 R 项仍待实施。斗罗 32 个 M2 输出零调用重放得到 83 安全事实和 1 条位置歧义，未覆盖写旧 run。

078/dev28 进展：promotion、M3 identity、cluster rescue、appearance transition 补齐请求指纹预检；promotion 恢复时不再信任缓存 Grounding。211 tests/19 subtests 通过。R05 统一迁移/尝试历史仍待补，详见 [缓存续跑兼容说明](39-cache-resume-compatibility.md)。

079/dev29 进展：R04 基础 Snapshot API/CLI/Schema、共享有效期及旧人物卡适配已验收；R03 已支持衣着独立持续、具体事实关闭和证据连续性，自动场景/换装语义发现仍待补。237 tests/19 subtests，4 张真实快照通过，详见 [Snapshot 与有效期契约](40-character-snapshot-and-applicability.md)。

084/dev33 进展：Web 里程碑 C 已交付（R11 人工决策闭环 + R08 subject 指定 run 解析最小版）。ReviewDecisionStore 按 run 维护追加式决策日志：乐观锁 revision、Idempotency-Key 幂等重放（同键同指纹返回已有决策、异请求 409）、决策指纹与原子写入；决策服务在提交前校验 run/review/conflict 存在性与 action/basis（correct 必须携带 new_value、reopen 需已有决策可补偿），reviews 视图融合 pending/decided/open 状态与 pending_review_count，不改写原始 review 产物。端点：`POST/GET /v1/runs/{run_id}/reviews/{review_id}/decisions`（201/200 幂等）、`GET /v1/documents/{id}/subjects/{subject_id}?run_id=`（resolved/unmapped_in_run）。前端复核页支持接受/拒绝/纠正/重开、决策历史时间线、状态徽章与版本冲突自动刷新。验收：311 tests/19 subtests、前端构建（56 modules，gzip 104.43 kB）、`scripts/c_milestone_smoke.py` 全流程（校验失败关闭、幂等重放与键冲突、乐观锁冲突、conflict 目标决策、reopen 补偿回 pending、历史 append-only、决策后 curated run 不可变）通过。待办：真实 provider 全流程实跑（含 managed registry 发布后的 subject 映射消费）、R07 召回评测、R08 完整合并/拆分迁移、决策对下游产物的补偿性重建策略。

082/083/dev32 进展：Web 里程碑 A+B 已交付。A（082）：FastAPI `/v1` 只读服务 + React/TypeScript/Vite 三栏页面（原文高亮/快照卡/StateSegment 时间线/证据轨迹树），R10 坐标契约按 unicode_codepoint 半开 span 绑定版本落地。B（083）：R09 异步任务管理核心完成——DocumentStore 不可变版本、JobStore 原子写入与事件日志、12 阶段流水线执行器（协作式取消、产物发布到 managed registry）、线程任务服务（幂等键/取消/恢复/事件游标/重启恢复）、R08 subject 映射基础；curated 与 managed 双注册表运行时 reload 合并。验收：275 tests/19 subtests、前端构建、`scripts/b_milestone_smoke.py` 全流程（导入幂等、文本窗口逐字回放、无 key 失败路径、resume 同断点重试、curated 共存）通过。待办：真实 provider 全流程实跑、R11 人工决策提交闭环（已于 084 完成）、R07/R08 召回评测与合并迁移。

080/dev30 进展：R03 自动事件模型任务与 R02 语义不兼容→时点冲突链路已实施；259 tests/19 subtests 通过。081/dev31 已完成斗罗 52 任务真实调用及离线重放，4 个 Snapshot 校验通过；质量仍待 R06，详见 [自动事件与冲突闭环](41-automatic-events-and-conflicts.md)。

## 1. 当前能力与本轮范围

- 已实现从原文到人物身份、事实、transition、StateSegment、语义关系、Label/Review 和 render-ready profile 的纵向链路。现有 compiler 已按 character/state/document\_position 选择状态，并区分 active/provisional。

- CharacterSnapshot 的缺口是统一查询契约、可解释的有效期/覆盖规则和供 Web 消费的稳定视图；不能把现状写成“完全没有时点快照”，也不应新建第二套可编辑状态。

- M3 候选默认上限 2，但 CLI 已允许配置；“长篇漏召回”是待通过标注集验证的风险，尚未测得漏召回率。

- scene 的现行策略确实以行尾或章尾过期；衣着事实又受同章节条件限制。这是当前保守基线，需要按用户要求演进。

- 前一轮复验为 191 tests / 13 subtests 通过；已另外复现 exact 重复 quote 仍选最早位置、否定子串被判 compatible 两个问题。单测通过不能替代人工质量 Gate。

- 本轮把 Web 服务层、接口、必要任务存储和调试页面纳入后续范围；不实现运行时代码、部署、图像生成或跨文档记忆。首轮按本机单用户 Web 设计，远程多人使用另有发布门槛。

## 2. 优先级清单

P0：阻断可信快照或可信评测。P1：后续 Web 最小可用版本及长篇可靠性所需。P2：完整诊断体验与基准驱动的规模优化。优先级在各自交付门槛内生效，依赖项仍须先完成。

| ID  | 优先级 | 问题与依据                                          | 修复交付物                                                                                 | 核心验收                                                                                           | 依赖                       |
| --- | --- | ---------------------------------------------- | ------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- | ------------------------ |
| R01 | P0  | M2 exact 多 occurrence 仍取最早位置，与唯一定位契约不一致        | 统一事实 Grounding 歧义策略；保留候选 occurrence 与 review；不猜位置                                     | 同 quote 两处、跨阶段两处、重叠 evidence 同一绝对位置分别处理；歧义事实不进入确定归属/状态                                         | 无                        |
| R02 | P0  | 包含规则把“高大/不高大”“黑色/不是黑色”判兼容；true\_conflict 缺生成闭环 | 否定/修饰反例保护；分开生成语义关系与有效期冲突判定；属性/部位不明时保留 unclassified                                    | 两个已复现反例不再 compatible；真实不可兼容且同时有效才冲突；跨时期、换装替换、左右部位均不误报                                          | R01；最终冲突 Gate 依赖 R03/R04 |
| R03 | P0  | scene 按行/章关闭，衣着与瞬时状态混在同一持续规则中                  | 分离叙事场景边界、装束/部位状态、瞬时状态；版本化有效区间与变化事件                                                    | 跨段/连续跨章不无故脱衣；明确脱下/替换及时关闭；无证据时间跳跃只暂定；形态退出不随意丢失基础装束                                              | R01；与 R04 契约共同冻结         |
| R04 | P0  | 已有按位置编译能力，但缺独立、稳定、可解释的 Snapshot 查询             | 从现有 compiler 抽取共享 applicability 引擎；增加 CharacterSnapshot 派生视图；旧 render profile 成为其适配输出 | 儿童/前世、普通/附体、换装前后独立快照；active/provisional/排除原因可追踪；旧 API/CLI 输出有兼容演练                              | R01/R03；冲突消费接 R02        |
| R05 | P0  | 缓存未完整绑定模型请求；M1/M2 缓存命中可直接使用旧 grounded 输出       | 请求指纹与 Grounding 版本分离；resume/replay/regenerate 三种显式模式；保留每次尝试历史                         | 换模型/Prompt/Schema 不误用缓存；纯策略重放零模型调用；未更改请求只续跑缺失任务；中断可恢复                                          | 无                        |
| R06 | P0  | 075 缺正式人工标注与 evaluator                         | 冻结标注协议、开发/保留测试集、裁决规则、逐层指标和失败样例库；基于 baseline 确认阈值                                      | mention/evidence、attribution、promotion、identity、state/snapshot 各自出报告；包含否定、重复 quote、跨章换装、候选遗漏反例 | 立即准备；最终 Gate 依赖对应修复      |
| R07 | P1  | 候选默认 2，二次扫描 O(n²)，缺 retrieval recall 度量        | 多路高召回 Top-K 候选检索、可配置截断、独立裁决预算、候选 provenance                                           | 对 K=2/5/10/20 的召回-成本曲线；报告未召回/被截断/未裁决/误裁决；不得靠同名直接合并                                             | R05/R06 标注协议             |
| R08 | P1  | character\_id 随来源版本/策略/anchor 变化，Web 收藏与审阅会失联  | 稳定 subject\_id 与 run-scoped character\_id 映射；合并/拆分迁移、历史别名和映射歧义状态                      | 重跑链接可解释；合并可重定向；拆分必须显示候选；不按姓名静默迁移                                                               | R04/R07 契约               |
| R09 | P1  | 当前以多条 CLI 和文件拼接，缺 Web 服务与长任务管理                 | 应用服务接口、后台 Job、不可变结果集合、HTTP 查询与命令接口、进度/取消/恢复                                           | 请求迅速返回任务句柄；刷新页面能恢复进度；多个 run 不串结果；中断/重复提交有测试；费用/重试可见                                            | R05/R08；查询接 R04          |
| R10 | P1  | Python code point 与浏览器 UTF-16 不同，文本归一可能破坏 span | 明确 offset\_unit/source\_version；服务端原文分段接口与前端索引映射                                      | 中文、emoji、扩展汉字、组合字符、CRLF、重复 quote 的高亮与后端逐字回放一致                                                  | R09 契约；Web 阅文入口前必需       |
| R11 | P1  | trace 分散，历史/当前 review 不同；页面尚无统一错误证据接口          | Evidence Trace 投影与 ReviewDecision 追加式记录；统一 stage/code/reason 与重建依赖                    | 可由卡片事实追到每层输入/输出/接受或拒绝原因；人工改动不覆盖 raw/model output；旧版修改返回版本冲突                                    | R05/R08/R09；坐标接 R10      |
| R12 | P1  | README/test 入口和部分验收行滞后；测试依赖未声明                 | 统一 pytest 开发依赖、可复现测试命令、CI/本地临时目录；同步现状文档                                               | 干净环境完整收集当前全部测试；明确单测与人工 Gate；清除已完成项的旧待办表述                                                       | 无                        |
| R13 | P2  | 人工难以在大量 JSON 中确定错误层                            | Evidence Debug Viewer：原文高亮、层级轨迹、状态时间线、前后 run 对比、人工复核入口                                | 一条错误可定位首次有证据支持的异常层；区分上游漏检与后续拒绝/传播；可分享固定 run 的深链                                                | R04/R09/R10/R11          |
| R14 | P2  | 小样本通过尚无长篇性能、并发和调用预算基准                          | 长篇分层基准、候选索引/分页/增量重建、受限并发和预算优化                                                         | 记录字符量/节点量、p50/p95、内存、provider calls/tokens、恢复耗时；优化后质量与确定性不退化                                   | R06/R07/R09；先测再选优化       |

## 3. CharacterSnapshot 的实现边界

### 3.1 复用路径

现有 render\_profile\_compiler.py 已有选择器、有效性判断、traits 与 provenance。先把选择状态和 applicability 提取为共享纯函数，然后由 Snapshot 组织查询结果，旧 render compiler 复用 Snapshot 投影为原有卡片结构。禁止 Snapshot 和 render compiler 各维护一套不同的持续规则。

数据依赖保持单向：

```
raw evidence + Registry
  -> canonical facts + grounded transition/boundary events
  -> StateSegments + fact observation bindings
  -> applicability intervals + semantic relations
  -> CharacterSnapshot(at position)
  -> render profile / Web character card
```

语义等价、包含、不兼容判断读取原始事实及限定词；true conflict 再结合实际有效期与选择器计算。不得让 Snapshot 冲突结果回写关系输入，避免循环。原来的 observed\_fact\_ids 仍表示观察位置唯一绑定；跨段有效性用派生区间表达。

### 3.2 查询与响应草案

查询至少绑定 document\_version\_id、run\_id、character\_id 和 at.document\_position；Web 长期入口用 subject\_id，再由指定 run 的映射解析 character\_id。life/form/scene 可作为附加筛选条件。首版 at 指原文叙事位置，不宣称已解决倒叙/插叙下的真实故事时间。

CharacterSnapshot 建议包含：

| 字段                                              | 消费方与用途                                                           |
| ----------------------------------------------- | ---------------------------------------------------------------- |
| snapshot\_id、schema\_version、policy\_version    | API 缓存、前后版本对比；snapshot\_id 绑定精确输入结果集合与查询                         |
| document\_version\_id、run\_id、artifact\_set\_id | 禁止跨文档、跨 run、跨发布批次拼卡                                              |
| subject\_id、character\_id、identity\_status      | 页面稳定入口与当前 run 身份解释；映射不明确时返回候选                                    |
| at、selected\_state\_segment\_id、life/form/scene | 阅文位置、状态导航与筛选                                                     |
| active\_traits、provisional\_traits              | 页面分别呈现确定和暂定外貌；暂定项不能被默认当作确定绘图条件                                   |
| applicability                                   | canonical fact 引用、观察位置、有效区间、依据事件与 status；未知终点明确表达                |
| conflicts、warnings、review\_refs                 | 当前位置的矛盾、不确定性与人工操作入口                                              |
| provenance\_refs                                | trait -> proposition/canonical fact -> raw occurrence -> 原文 span |

排除事实及 reason 通过 explain 查询按需展开，不在每张卡复制整本原文和所有历史事实。必要 reason 包括 future\_observation、different\_life/form、replaced、removed、expired\_momentary、uncertain\_continuity、identity\_unresolved。

未来 observation 不进入当前卡；未知持续性保持 provisional；不根据“后文出现新值”自动把任意多值当作覆盖。缺位置、选择器歧义、覆盖范围外或身份映射不明确应有明确响应，不返回混合 traits。具体坐标边界沿用半开区间并在 R10 固定测试；“读到章末”由服务端解析为覆盖内的明确位置。

### 3.3 缓存与兼容

- Snapshot 是可丢弃缓存，键绑定 source/run/artifact revisions、character、position/selector 和 applicability/relation policy。

- Raw facts 不变；新增状态事件、关系策略或人工决策后生成新的 artifact\_set，依赖失效沿单向图传播。

- 保留 dev26 reader/输出适配，新增 schema 与策略版本。旧结果可查看；旧模型输出不足以支持新场景判断时标记缺失，不伪造补齐结果。

- 初期从 run-scoped character\_id 查询即可开发纯函数；subject\_id 在 Web 长期链接上线前接入，不阻塞基础 Snapshot 单测。

## 4. 场景、换装与有效期规则

必须拆开叙事场景与角色装束。换段、换章、人物暂时离开叙述，不等于该人物脱下衣物；角色仍在同一场景，也不等于表情和短暂状态一直有效。

| 情况              | 目标规则                                       |
| --------------- | ------------------------------------------ |
| 段落/章节切换但有连续行动依据 | 保留装束；不因排版边界清空。是否确定 active 取决于连续性证据         |
| 地点切换            | 可结束叙事场景；衣着按自身持续规则处理，不能跟随场景 ID 一起删除         |
| 明确穿上/脱下/替换      | 生成有原文支持的变更事件，按部位/层次/物件关闭或叠加对应状态            |
| 外套叠加衬衣、佩饰增减     | 按槽位和叠穿关系处理，不使用全人物最后写入覆盖                    |
| 静态“身穿灰衣”        | 作为 observation，不冒充换装事件；是否向后延续由连续性与持续规则决定   |
| 表情、脸红、瞬时光效      | 使用 momentary 或有证据支持的短区间；不能与衣着共用长期持续规则      |
| 时间跳跃/倒叙/边界未知    | 不推断真实时间连续；降低为 provisional/unknown，等待证据或复核  |
| life 改变         | 隔离旧生命阶段；form 改变按属性作用域建立覆盖，不把基础状态无条件迁入新生命阶段 |
| form 退出         | 仅在基础状态仍有有效来源且期间未被替换时恢复；不通过“退出”凭空补衣着        |

事件输出保持最小模型边界：模型只提供人物标签、必要变化语义和连续原文；ID、span、有效区间与覆盖顺序由代码验证和生成。优先复用保存输出及原文证据；需要增加场景连续性语义时先冻结最小 Schema 与样例，再决定是否增加受约束模型节点。不能仅凭扩大关键词表宣称“真实场景识别”完成。

最少验收组：跨段延续、连续跨章、换地点不换衣、明确脱衣、局部换装、叠穿、暂时离场、时间跳跃、转生、变身进入/退出、同位置事件顺序、缺失结束证据、重叠 Chunk 去重。区间采用半开边界，变更前后两个查询必须可解释。

## 5. 高召回 Top-K 的边界

现有 max\_candidates\_per\_node 可配置，问题不只是默认数字小。先分离 retrieval\_k（候选池容量）与 adjudication\_budget（模型实际裁决预算），允许在预算内分批扩展并保留未裁决候选。

- 候选来源包括名称/已验证别名、局部明确关系原文、相邻叙事上下文及已有事实索引；各路都保留来源与排序理由。

- 称号和相似外貌可帮助召回，不作为自动身份合并证据；cannot-link 继续硬约束。

- 已确认成员可按簇聚合以减少 Top-K 被同一人物的多个节点挤占，仍保留原始节点证据及多样性。

- 保留 K 截断、预算截断和无候选原因；“没有召回”与“模型判 uncertain”在报表中分开。

- 优先建立姓名/别名/事实索引并测量；embedding/reranker 只有在冻结样本证明增益后再选型，不预设新增模型费用。

- 评测只使用当前运行阶段已存在的信息，不能把完整答案/后验标签泄漏到检索输入。

报告 gold candidate recall\@K、候选 MRR、false merge/split、候选/模型调用数和 tokens；按同名、别名、泛称、长距离重现和零事实节点分层。K 值与正式召回阈值须由 baseline 决定；“高召回”在测得指标前只是目标。

## 6. Web 应用服务与接口草案

### 6.1 分层和结果一致性

Python 领域函数 -> 应用服务 -> 存储/后台 Worker -> HTTP API -> Web 页面。CLI 和 HTTP 复用应用服务；不从 HTTP 直接拼接 shell 命令，也不向客户端暴露 runs 文件系统路径。首轮不为规划预定 Web 框架或数据库产品。

原始文本及既有 artifacts 继续作为不可变结果；任务、索引、subject 映射和人工决策通过 Repository 接口持久化。每次成功重建后原子发布 artifact\_set manifest，绑定 registry/facts/states/snapshot 的兼容版本。页面显式选择 run，不自动混用各目录的“最新文件”。

异步任务状态建议 queued/running/succeeded/partial/failed/cancel\_requested/cancelled；阶段状态与整条 run 分开。缺失上游依赖的结果不可假装完整，已验证的局部结果可按 coverage/status 查看。

| 方法与路径（/v1 前缀）                                                   | 用途                           | 关键约束                                                                                   |
| --------------------------------------------------------------- | ---------------------------- | -------------------------------------------------------------------------------------- |
| POST /documents                                                 | 上传或提交原文，建立文档及不可变来源版本         | 编码/大小检查；原文 CRLF 保真；变更文本新建 version                                                      |
| GET /documents/{document\_id}/versions                          | 来源版本列表                       | 后续查询固定 version                                                                         |
| POST /documents/{document\_id}/runs                             | 创建解析/重建任务                    | source\_version、pipeline/model config、mode、预算、Idempotency-Key；返回 202 与 run\_id/job\_id |
| GET /runs/{run\_id}                                             | 阶段进度、coverage、错误摘要、成本        | 区分 resumed/new calls；无可靠 ETA 时不编造                                                      |
| GET /runs/{run\_id}/events                                      | 增量进度事件，支持断线续读                | 有序 cursor；轮询保底，可增加 SSE                                                                 |
| POST /runs/{run\_id}/cancel                                     | 请求取消                         | 幂等；取消阻止新任务，已发出的模型请求可能继续结束                                                              |
| POST /runs/{run\_id}/resume                                     | 继续未完成且请求指纹匹配的工作              | 保留历史；不静默换配置                                                                            |
| POST /runs/{run\_id}/replays                                    | 派生新 run，重放指定策略及下游            | 与 regenerate 分开；明确计划重算哪些层与是否有新模型调用                                                     |
| GET /runs/{run\_id}/characters                                  | 人物列表、未决状态和分页                 | 返回 subject\_id 与 run-scoped character\_id                                              |
| GET /runs/{run\_id}/characters/{character\_id}/states           | 状态区间与可用查询位置                  | source\_version、offset\_unit、coverage                                                  |
| GET /runs/{run\_id}/characters/{character\_id}/snapshot         | 指定 position 与可选 selector 的快照 | GET 不触发付费模型；昂贵重建另建 Job；不可用时明确 missing artifact                                         |
| GET /runs/{run\_id}/characters/{character\_id}/snapshot/explain | 指定位置、fact 的纳入/排除原因           | 与 snapshot 绑定相同 artifact\_set                                                          |
| GET /runs/{run\_id}/evidence/{evidence\_id}/trace               | 原文、逐层来源引用与处理原因               | 分页/按层展开；不整本小说塞进响应                                                                      |
| GET /documents/{document\_id}/versions/{version\_id}/text       | start/end 原文窗口及坐标            | 限制窗口长度；原文渲染转义；严格校验版本与范围                                                                |
| GET /runs/{run\_id}/reviews                                     | 当前待办与历史审计                    | actionable/audit 分开筛选，不删除历史                                                            |
| POST /runs/{run\_id}/reviews/{review\_id}/decisions             | 提交人工纠正/接受/拒绝                 | expected\_revision + 幂等键；追加式决策，触发必要下游重建                                                |
| GET /documents/{document\_id}/subjects/{subject\_id}            | 稳定入口在指定 run 下的映射             | 合并/拆分/不可解析状态显式返回，不能按名称猜                                                                |

接口冻结时补齐请求/响应 Schema、分页、错误码和生成的客户端类型。例：返回 schema\_version、request\_id、run\_id、artifact\_set\_id、data、warnings；错误返回 code/stage/retryable/review\_ref/可读消息。身份歧义、版本冲突、依赖缺失与参数越界不得都映射为普通 500。

### 6.2 并发、重试与预算

- 创建 run 与提交人工决策支持幂等；同键不同请求返回冲突。

- Worker 使用任务租约/互斥及原子结果提交，避免两个执行器并发覆盖相同 .tmp 文件或成功记录。

- 模型网络超时不能保证恰好调用一次；记录 attempt、未知结果和实际可观测用量，恢复时先检查已提交结果。

- resume/replay/regenerate 的调用计划在服务端显式生成，运行中统一执行最大调用数、tokens/可用预算和取消策略。

- 原始请求内容、完整 Prompt、正文和密钥不进入普通日志；模型凭据仅保留服务端。上传文本作为数据处理，不能执行其指令。

- 默认本机访问。若改为远程/多人服务，上线前补认证、资源归属与跨用户隔离测试、持久化备份和服务恢复验收；这些是部署模式门槛，不是本轮额外操作。

### 6.3 坐标契约

API 明确 offset\_unit=unicode\_codepoint、半开 span、source\_document\_version\_id，并说明位置来自未经归一化的原文。前端不可直接用 JavaScript UTF-16 slice 消费后端索引；建立 code point 到 UTF-16 的映射或使用等价可靠转换。

展示层换行折叠、HTML 转义和富文本标记都不能回写来源文本。同 quote 多次出现时必须按版本/span 定位，禁止字符串首次搜索。上传、后端处理、API 原文窗口、浏览器高亮四个环节联测。

## 7. Evidence Debug Viewer 与人工纠正

P1 先提供可用 Trace API 和错误明细，P2 再交付完整 Viewer，避免为了调试页面延迟正确性修复。

建议页面以当前人物/位置为中心，包含原文窗口、快照/状态时间线、证据处理轨迹三部分。点击一条 trait 展开：

```
原文 -> M1 候选 -> N2 接受/删除/拒绝
     -> M2 事实与 Grounding -> N3 认领/冲突/剩余池
     -> promotion -> M3 候选与身份裁决
     -> canonical fact -> transition/StateSegment
     -> applicability -> Snapshot
```

每个节点显示 stage、源任务/版本、接受或拒绝原因、相关 evidence/review；模型判断和确定性检查明确标识。trace 缺失则显示不可追溯段，不能根据结果反编造模型输入。

“错误出在哪层”应显示可证据定位的最早异常或人工标记，不把下游 warning 当作根因；没有 gold 标注时不能自动证明 M1 漏检。提供原文手选 span 发起问题记录，以支持“没有抽出的事实”反馈。

人工纠正单独形成版本化 decision：目标、动作、原/新值、依据、操作者、时间、expected revision。按依赖图重建新结果；撤销用补偿 decision，不改旧 raw facts、模型原始输出或历史 review。subject 拆分时不自动把旧 decision 应用于所有新人物。

## 8. 实施顺序与交付门槛

1. 准备：R06 冻结标注协议与错误分类，同时 R12 整理完整测试入口。保留当前 dev26 baseline。
2. 正确性修复：R01、R02 的否定保护、R05 缓存/重放。每个已复现问题必须有针对性回归和保存输出重放结果。
3. 快照纵向切片：共同冻结 R03/R04 契约，先实现有效期，再接 Snapshot 与 R02 真冲突生成/消费。完成旧 render profile 兼容及边界样例。
4. 长篇身份：R07 测 recall\@K 和裁决预算，R08 建立稳定入口及合并/拆分迁移。可在依赖冻结后与快照开发分别推进。
5. Web 最小可用版：R09/R10/R11，贯通导入 -> 启动/恢复任务 -> 人物列表 -> 状态快照 -> 原文证据 -> 复核决定；R12 提供可复现运行说明。
6. 体验与规模：R13 Viewer、R14 基准驱动优化。R06 对实际交付链路执行最终质量评测，再评审发布。

门槛分别判定：

- 工程门槛：来源回放、引用一致性、版本失效、幂等/恢复、坐标高亮及失败路径通过。

- 模型质量门槛：冻结集上的逐层指标达到实施前确认的阈值，报告未决与分层错误；不以“0 conflict”或单一总分代替。

- Web 门槛：用户能完成最小流程、刷新/失败后继续操作；查询无意外付费，结果不跨 run 拼接。

- 发布门槛：按本机或远程使用模式分别验收访问、恢复、数据保留、预算和回滚；规划完成不构成发布许可。

旧版本与历史 Gate 保留。若新增功能使已验收阶段的入口/出口发生实质变化，在进入实施前通过生命周期工具登记回退或重审，不直接改写旧 Gate。当前 Stage 6 只启动问题梳理与规划，075 最终 Gate 尚未通过。

## 9. 源码依据

- 重复 exact 位置选择：[m2.py](../src/novel_character_generator/m2.py)，ground\_m2\_attribution\_output。

- 否定子串/当前关系枚举：[appearance\_semantic\_relations.py](../src/novel_character_generator/appearance_semantic_relations.py)，\_classify\_pair。

- 行/章过期：[appearance\_state\_segments.py](../src/novel_character_generator/appearance_state_segments.py)，scene\_expiry\_position。

- category 持续性基线：[appearance\_scope.py](../src/novel_character_generator/appearance_scope.py)，\_persistence。

- 已有快照式能力及同章约束：[render\_profile\_compiler.py](../src/novel_character_generator/render_profile_compiler.py)，\_fact\_applicability / \_compile\_profile。

- 缓存与恢复：[m1\_batch.py](../src/novel_character_generator/m1_batch.py)、[m2\_batch.py](../src/novel_character_generator/m2_batch.py) 及 M2OrchestrationEnvelope。

- 默认候选及 O(n²) 扫描：[identity.py](../src/novel_character_generator/identity.py)，build\_identity\_preparation；CLI 已提供 max-candidates-per-node。

- ID 稳定性：[identity.py](../src/novel_character_generator/identity.py)，\_character\_id。

- 既定 075 和后续范围：[36 开发计划](36-appearance-profile-compiler-development-plan.md)。

