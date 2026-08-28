# 项目验收

> 执行测试、交付或声明完成前必须读取本文件。没有新鲜证据时不得写成通过。
> 不粘贴密钥、完整个人信息、原始顾客对话或未脱敏工具输出。

## 当前验收结论

- 结论：M1 shadow/offline 工程 Gate 通过，模型效果 Gate 等待用户审核测试集；既有 R2/R3 与最终画像语义质量 Gate 仍不通过，不能进入批量生图
- 验收范围：V2 第一阶段 M1 strict contract/shadow/evaluator；既有《斗罗大陆》19 Chunk R1/R2/R3 真实运行与 R6 生图候选保持原结论
- 最后检查：2026-08-28
- 遗留问题：M1 15-case 数据集尚未获用户批准、没有真实 M1 Provider 结果；M2-M5、端到端 P0、promotion coverage 与人工 review capacity 阈值均未完成；R2/R3 与最终画像真实质量仍未重新通过；首图尚无用户审批、漂移审计和 baseline 锁定。

## 验收标准

| 标准 ID | 标准 | 状态 | 验证方法 | 证据 ID |
|---|---|---|---|---|
| A-PIPELINE-V2-M1-001 | M1 输入输出严格版本化，只表达局部实体、raw fact、epistemic、temporal 与 unresolved，不含 canonical 字段、最终身份/阶段/激活权 | 工程通过；模型效果待审 | Pydantic Schema 正反例、Prompt/request 契约、局部引用测试 | E-20260828-PIPELINE-V2-M1-013 |
| A-PIPELINE-V2-M1-002 | 引文必须来自当前 Chunk，family 白名单、unused entity、悬空/跨 owner 引用、重复与 fact/unresolved 双写失败关闭 | 通过 | contract/service 单元正反例与 shadow 集成测试 | E-20260828-PIPELINE-V2-M1-013 |
| A-PIPELINE-V2-M1-003 | M1 有独立用户审核测试集和评分器；draft 状态强制阻止模型质量结论和 M2 启动 | 待用户审核（工程机制通过） | 15-case dataset 自校验、gold self-test、hard fail/review 分流 | E-20260828-PIPELINE-V2-M1-013 |
| A-PIPELINE-V2-M1-004 | R1/R2/M1 复用公共结构化 Provider 底层，重复 Prompt/调用循环已删除且 V1 生产/回滚行为无回退 | 通过 | 引用审计、30 Provider/恢复测试、251 full Pytest、Ruff、125 source Mypy | E-20260828-PIPELINE-V2-M1-013 |
| A-PIPELINE-V2-DESIGN-001 | N0-N11 每个节点具备单一职责、明确输入输出、触发/失败路由、状态与指标 | v1.1 静态通过；待实现验证 | 主契约结构、Prompt/Schema 链接与职责审阅 | E-20260828-PIPELINE-V2-DESIGN-012-R1 |
| A-PIPELINE-V2-DESIGN-002 | M1-M5 系统提示词独立版本化，字段/身份/时间开放语义由模型负责，代码不冒充语义主解析器 | v1.1 静态通过；待模型验证 | 五份 Prompt、职责矩阵与能力边界审阅 | E-20260828-PIPELINE-V2-DESIGN-012-R1 |
| A-PIPELINE-V2-DESIGN-003 | M1-M5 输入与输出有机器可读条件 Schema；模型不能直接激活 Observation，M5 只可降级，N8b 保留唯一激活权 | v1.1 Schema 通过；待服务端实现 | Draft 2020-12 meta-schema、条件正反例与 Promotion 契约 | E-20260828-PIPELINE-V2-DESIGN-012-R1 |
| A-PIPELINE-V2-DESIGN-004 | 质量优先 Gate 同时约束 precision、safe-fact recall、promotion coverage、Profile 完整率与人工容量；成本护栏、P0/A-B/shadow/灰度/V1 回滚明确 | 条件通过；数值阈值待 P0 冻结 | Gate、评测、实施与兼容章节审阅 | E-20260828-PIPELINE-V2-DESIGN-012-R1 |
| A-PIPELINE-V2-DESIGN-005 | M1 默认覆盖全部有效 Chunk，任何 prefilter 只有独立召回 Gate 后才能跳过 | 设计通过；待质量实测 | M1 触发、空结果审计和模型矩阵检查 | E-20260828-PIPELINE-V2-DESIGN-012-R1 |
| A-PIPELINE-V2-DESIGN-006 | M2 载体绑定、M3 组件召回/旧绑定 supersede、M4 scene/event 起止、M5 分组互斥复核均可表达且失败关闭 | 设计/Schema 通过；待实现与金标 | v1.1 主契约、5 Prompt、Schema 条件正反例 | E-20260828-PIPELINE-V2-DESIGN-012-R1 |
| A-PIPELINE-V2-DESIGN-007 | 模型配置、上下文版本、数据保留、显式语义重评、取消/恢复/晚到响应和 Provider 漂移有具名边界 | 设计通过；待失败注入 | 公共信封、模型/数据 Gate 与最小运维表 | E-20260828-PIPELINE-V2-DESIGN-012-R1 |
| A-PIPELINE-V2-DESIGN-008 | 核心架构重设计先回退 Stage 4 复审，完成 Gate 后 Stage 5 仅恢复为 ready | 通过 | Lifecycle revision 3–5 与验证 | E-20260828-PIPELINE-V2-DESIGN-012-R1 |
| A-R6-ALIYUN-001 | qwen-image-plus 按官方异步契约单图提交、查询并只从阿里云 HTTPS 结果域下载，API Key 不进入结果下载请求 | 通过（离线契约） | MockTransport 请求/响应与凭据边界单元测试 | E-20260827-R6-ALIYUN-009 |
| A-R6-ALIYUN-002 | 明确拒绝与提交未知分流；PENDING/RUNNING 不消耗失败重试且不重复提交 | 通过（离线恢复） | Provider 异常单元测试与 Image Pipeline defer 集成测试 | E-20260827-R6-ALIYUN-009 |
| A-R6-ALIYUN-002A | Worker 通过注册表构造/关闭 Provider；未知、重复和身份不匹配失败关闭；同步/异步结果可恢复且记录模型版本 | 通过（离线架构） | Registry 单元测试、Pipeline 同步引用/版本持久化断言、Alembic 往返、211 项完整回归 | E-20260827-R6-ALIYUN-009 |
| A-R6-ALIYUN-002B | PromptRenderer 独立版本化/可插拔，内部字段转为自然视觉语言，每个语义短句保留 provenance，缺来源失败关闭 | 通过 | golden/provenance/registry 正反例与图片评测元数据断言 | E-20260828-R6-ALIYUN-009 |
| A-R6-TIMICC-001 | timicc 复用通用 OpenAI-compatible 同步 Provider；gpt-image-2 请求、base64 PNG 暂存恢复、受限 host 和错误脱敏通过且 Worker 无供应商分支 | 条件通过：真实模型可用；请求/实际尺寸漂移，baseline Gate 不通过 | MockTransport 契约/安全正反例、registry/settings、完整回归与单图 smoke | E-20260828-R6-ALIYUN-009 |
| A-R6-ALIYUN-003 | 首张真实效果图成功下载并经人工查看 | 部分通过：真实 PNG 与视觉初检完成，用户审批待定 | 单图 smoke、PNG/Prompt 产物与视觉检查 | E-20260828-R6-ALIYUN-009 |
| A-R6-ALIYUN-004 | 可信审批、漂移审计、质量 Gate 与可接受 baseline 阻止未批准批量生成 | 进行中 | 审批/审计/基线正反例与真实图像评测 | 首图已完成；待用户审批与 Gate 实现 |
| A-R1-PROMPT-AB-001 | v2.5 被源码冻结，A/B 可在同 Provider/模型/参数/Schema 链路注入 Prompt/version，默认指针可验证回滚到 v2.5 | 通过 | Provider 请求/版本契约单元测试与源码断言 | E-20260827-R1-PROMPT-AB-007 |
| A-R1-PROMPT-AB-002 | 真实样例与 25 seed 的逐样例报告可复现，记录质量、grounding、warning/reject、token 与延迟且不保存密钥/完整输入 | 通过 | 三轮 130 次 DeepSeek A/B 报告与哈希审核 | E-20260827-R1-PROMPT-AB-007 |
| A-R1-PROMPT-AB-003 | v2.6 关键安全项不回退，整体质量不低于 A，实体重复与服务端拒绝/warning 不增加，成本可接受 | 不通过 | 最终轮 seed/真实样例统计与人工差异审核 | E-20260827-R1-PROMPT-AB-007 |
| A-R1-PROMPT-AB-004 | v3.4 新 deferred 分类和字段语义门禁向后兼容，定向/完整 Pytest、Ruff、Mypy 通过 | 通过 | 49 targeted、203 full Pytest、Ruff、Mypy | E-20260827-R1-PROMPT-AB-007 |
| A-R1-GOLD-001 | v0 原样保留；v1 使用 required/allowed/forbidden 且纠正服装、礼服、白衣、鞋靴和清俊旧答案冲突 | 通过 | 数据集 Schema/计数/哈希与字段边界单元测试 | E-20260828-R1-GOLD-008 |
| A-R1-GOLD-002 | mention、deferred、temporal、禁用事实、重复与 asserted/deferred 双写进入可审计评分 | 通过 | 评分器正反例和 A/B contract metrics 测试 | E-20260828-R1-GOLD-008 |
| A-R1-GOLD-003 | 6 个真实 Chunk 从固定 source/ordinal 重建并验证黄金引文；部分标注明示且未标注输出只计数 | 通过 | source-backed loader 与 15 required/11 forbidden 断言 | E-20260828-R1-GOLD-008 |
| A-R1-GOLD-004 | v0 旧报告可重放；v1 工具默认切换；完整回归、Ruff、Mypy src 通过且真实调用为 0 | 通过 | v0 offline rescore、v1 Mock smoke、21 targeted/225 full | E-20260828-R1-GOLD-008 |
| A-R1-GOLD-RUN-001 | v1 在同 Provider/模型/参数/Schema 下完成 v2.5/v2.6 的 31 seed + 6 real 全量运行 | 通过 | 74 次真实调用报告、逐版本 metadata 与输入哈希 | E-20260828-R1-GOLD-RUN-010 |
| A-R1-GOLD-RUN-002 | 失败可区分黄金/评分、Prompt、grounding/adapter 与字段政策，不以总分替代逐层归因 | 通过 | 原始 candidate、grounded packet、score reason 与人工分类 | E-20260828-R1-GOLD-RUN-010 |
| A-R1-GOLD-RUN-003 | 修正后的 v1 可作为发布硬 Gate，且当前生产 Prompt 满足预设阈值 | 不通过 | 真实结果与测量缺陷审计 | E-20260828-R1-GOLD-RUN-010 |
| A-R1-GOLD-FIX-001 | v1.1 修正阶段键、合法字段、受控异体、安全 deferred 与 identity-dependent gold，且数据契约自校验 | 通过 | 27 项评分器单元与 dataset/manifest 加载 | E-20260828-R1-GOLD-FIX-011 |
| A-R1-GOLD-FIX-002 | raw mention、owner/surface alias、temporal 包含/去重、无关同字段配对和 asserted/deferred 排他进入评分 | 通过 | 评分器正反例与 74 份 candidates 离线重评 | E-20260828-R1-GOLD-FIX-011 |
| A-R1-GOLD-FIX-003 | 完整静态/类型/回归通过且不调用 Provider、不切换生产 Prompt | 通过 | 236 Pytest、Ruff、121 source Mypy、调用计数 0 | E-20260828-R1-GOLD-FIX-011 |
| A-R6-001 | 目标字段可带 block/source refs 适配并确定性编译为 Provider 中立 ImageRenderSpec，目标目录与显式阶段字段有正例 | 通过 | image rendering 单元测试与 context 集成断言 | E-20260827-R6-IMAGE-SPEC-008 |
| A-R6-002 | 普通请求不能自批 consistent scene；legacy provenance 只能 concept；非法字段/形状失败关闭 | 通过 | approval、mode、provenance、extra/shape 反例 | E-20260827-R6-IMAGE-SPEC-008 |
| A-R6-003 | Mock Provider 只消费 spec，context/spec hash 稳定，submit unknown 重启不重复 submit | 通过 | Mock Pipeline、ExternalOperation 与恢复集成测试 | E-20260827-R6-IMAGE-SPEC-008 |
| A-R6-004 | 定向与完整回归、Ruff、Mypy 通过；无真实调用和迁移 | 通过 | 6 targeted、202 full Pytest、Ruff、Mypy | E-20260827-R6-IMAGE-SPEC-008 |
| A-R1-DATA-001 | R1 Schema 只暴露四类 mention，旧标签兼容且非 explicit_name 不进入 explicit_names | 通过 | Provider Schema、兼容和 R2 memory 单元反例 | E-20260827-R1-DATA-006 |
| A-R1-DATA-002 | age 只允许规范路径；clothing 拒绝书籍、武器、药物及无衣物语义字段 | 通过 | Adapter 与字段门禁单元测试 | E-20260827-R1-DATA-006 |
| A-R1-DATA-003 | 证据按精确/软规范/唯一窄漏字定位；歧义、语义替换、跨句硬标点拒绝，并保存原文与修复审计 | 通过 | locator、Adapter 与 GroundedFact 审计测试 | E-20260827-R1-DATA-006 |
| A-R1-DATA-004 | 静态、类型、单元与完整回归通过，不增加调用或迁移 | 通过 | Ruff、Mypy、154 unit、193 full Pytest | E-20260827-R1-DATA-006 |
| A-R1-BASE-001 | R1 回归 fixture 与 R2 身份解析基线分离，且不包含作品特例身份规则 | 通过 | fixture 范围/内容静态审核 | E-20260827-R1-BASELINE-005 |
| A-R1-BASE-002 | 5 项缺失行为以 strict xfail 冻结，2 项既有证据安全边界通过；生产实现保持不变 | 通过 | R1 定向/完整 Pytest 与 Ruff | E-20260827-R1-BASELINE-005 |
| A-R2-SHARD-001 | Dirty frontier 按完整 record 在 record、mention、完整请求预计输入和预计输出预算内确定性分片；原子记录超预算失败关闭 | 通过 | 四重预算/超预算单元测试与多 shard 集成测试 | E-20260827-R2-SHARD-004-CAL1 |
| A-R2-SHARD-002 | Provider 未安全覆盖记录最多两轮 repair；次数或调用预算耗尽后 100% 保守补全并显式 warning | 通过 | repair 成功、次数耗尽和调用预算耗尽集成反例 | E-20260827-R2-SHARD-004-CAL1 |
| A-R2-SHARD-003 | RunEvent/Inspector/UI 显示四重 shard 预算、估算策略、调用、repair、fallback 且 completed_with_warnings 可恢复不重跑 | 通过 | R2 pipeline、Inspector API/UI 契约和恢复测试 | E-20260827-R2-SHARD-004-CAL1 |
| A-R2-FRONTIER-001 | 十章收敛只处理当前批次 dirty non-stable，未变化历史 unresolved 保留但不重复提交 | 通过 | frontier 服务单元测试与两批次集成测试 | E-20260827-R2-FRONTIER-003 |
| A-R2-FRONTIER-002 | 收敛 RunEvent/Inspector 显示 frontier/deferred、Provider 原始覆盖、omission 与收敛后状态且不含原文 | 通过 | 事件与 Inspector API/UI 契约测试 | E-20260827-R2-FRONTIER-003 |
| A-R2-MEM-001 | 逐 Chunk 人物解析只携带有界相关 memory，且未入选历史 memory 在应用结果后不丢失 | 通过 | 服务单元测试与 R2 流水线集成测试 | E-20260827-R2-MEMORY-002 |
| A-R2-MEM-002 | RunEvent 与 Run Inspector 可查看 memory 裁剪前后数量、入选原因和状态构成，且不含正文或证据原文 | 通过 | 事件 payload 与 Inspector API/UI 契约测试 | E-20260827-R2-MEMORY-002 |
| A-001 | v3 候选与证据定位在跨题材样本上可运行 | 通过 | 有界真实 Provider 诊断 | E-20260826-R1-EVAL-002 |
| A-002 | 新 case 不包含作品专名或世界观特例规则 | 通过 | 数据集和 Prompt 静态扫描 + 人工审核 | E-20260826-R1-EVAL-002、E-20260826-R1-PROMPT-003 |
| A-003 | 项目约定的测试全部通过 | 通过 | Ruff、Mypy、Pytest | E-20260826-R1-EVAL-004 |
| A-004 | 成本、失败和未覆盖项被如实记录 | 通过 | 检查诊断 metadata 与任务证据 | E-20260826-R1-EVAL-002、E-20260826-R1-PROMPT-003 |
| A-005 | 字段混淆规则使用跨作品语义边界且逐 case 独立验证 | 通过 | Prompt 静态检查、真实 v3 独立调用、字段集合人工复核 | E-20260826-R1-PROMPT-003 |
| A-006 | 评测器对结构错误、未知措辞和已确认等价值给出确定性三态结果 | 通过 | 单元测试、保存结果离线重评分、全量回归 | E-20260826-R1-EVAL-004 |
| A-R2-001 | 第 3 Chunk 输入包含前两 Chunk 累计记忆；同泛称不会由代码自动绑定 | 通过 | 单元与端到端反例测试 | E-20260827-R2-ENTITY-001 |
| A-R2-002 | 每 10 Chunk 固定收敛，文末余数执行尾批 | 通过 | 11 章集成测试检查 0–9 与 10–10 批次 | E-20260827-R2-ENTITY-001 |
| A-R2-003 | 只有 final 绑定生成 Observation，失败和 unresolved 均失败关闭 | 通过 | 失败替换与“另一男孩”隔离集成测试 | E-20260827-R2-ENTITY-001 |
| A-R2-004 | 迁移、幂等、静态检查和项目回归通过 | 通过 | Alembic/Ruff/Mypy/Pytest | E-20260827-R2-ENTITY-001 |
| A-R3-001 | 显式时间信号完整定位持久化，事实级信号不扩散到同 mention 的其他事实 | 通过 | Adapter 单元测试与 R3 集成反例 | E-20260827-R3-PHASE-001 |
| A-R3-002 | R2 观察保持 pending；R3 final 才激活，needs_review 不进入聚合 | 通过 | 阶段流水线集成测试 | E-20260827-R3-PHASE-001 |
| A-R3-003 | 阶段/呈现/现实/形态解析及审核、查询、revision 修订接口可运行 | 通过 | 纯服务单元测试与 API 集成测试 | E-20260827-R3-PHASE-001 |
| A-R3-004 | 唯一迁移 head、静态检查和全量回归通过 | 通过 | Alembic/Ruff/Mypy/Pytest | E-20260827-R3-PHASE-001 |
| A-REAL-001 | 真实长文本可从 checkpoint 完成 R1/R2/R3/聚合并保存可复核证据 | 通过 | 19 Chunk 隔离 DeepSeek run + summary/DB 审核 | E-20260827-R123-REAL-001 |
| A-REAL-002 | R2 最终记忆不跨显式姓名污染且 stable 覆盖正式人物 | 不通过 | final convergence memory 人工/SQL 审核 | E-20260827-R123-REAL-001 |
| A-REAL-003 | R3 分离转生前后人生阶段和暂态 transformation | 不通过 | life phases、scope bindings、appearance states 审核 | E-20260827-R123-REAL-001 |
| A-REAL-004 | 聚合画像的默认锚点可直接用于人物定妆 | 不通过 | render profile/identity anchor/conflict 审核 | E-20260827-R123-REAL-001 |
| A-REAL-005 | 本轮工程修复的静态与完整回归通过 | 通过 | Ruff/Mypy/Pytest 144 tests | E-20260827-R123-REAL-001 |
| A-OBS-001 | R1/R2/R3 独立阶段摘要可查询且不复制正文 payload | 通过 | API 集成测试与响应边界断言 | E-20260827-OBS-RUN-001 |
| A-OBS-002 | 四类结构化产出详情受 Run 归属和 kind/id 校验保护 | 通过 | R1/R2/R3 详情与 404 反例测试 | E-20260827-OBS-RUN-001 |
| A-OBS-003 | 工作台可查看阶段卡片并下钻，桌面与窄屏可读 | 通过 | UI 静态契约、JS 语法和浏览器视觉检查 | E-20260827-OBS-RUN-001 |
| A-OBS-004 | Inspector 增量静态检查和全量回归通过 | 通过 | Ruff/Mypy/Pytest | E-20260827-OBS-RUN-001 |
| A-RAW-001 | R1/R2 成功 Provider 调用保存消息、完整响应与哈希，普通 Inspector 不复制 raw | 通过 | Provider 单元、R1/R2 API 集成与边界断言 | E-20260827-DEV-RAW-001 |
| A-RAW-002 | 原始响应接口仅 development + 显式开关 + 管理员可读，生产失败关闭 | 通过 | Settings 与 403/200 API 反例 | E-20260827-DEV-RAW-001 |
| A-RAW-003 | 工作台页签、旧 Run 提示与 R3 隐藏行为可读且无控制台错误 | 通过 | Node 与本地浏览器检查 | E-20260827-DEV-RAW-001 |
| A-RAW-004 | 唯一迁移 head、静态检查和完整回归通过 | 通过 | Alembic/Ruff/Mypy/Node/159 Pytest | E-20260827-DEV-RAW-001 |

## 证据索引

| 证据 ID | 时间 | 方法或命令 | 退出状态 | 版本或文件哈希 | 结果摘要 | 证据位置 | 有效期 |
|---|---|---|---|---|---|---|---|
| E-20260828-PIPELINE-V2-M1-013 | 2026-08-28 | M1 contract/provider/evaluator/shadow 正反例 + R1/R2 Provider 恢复 + 完整 Pytest/Ruff/Mypy + 引用/治理检查 | 0 | Prompt `DE2D528E...56BFA`；dataset `F52F1324...5618E` | 15-case draft；251 tests；125 source files；0 Provider/迁移/路由；工程通过，用户数据/模型质量 Gate blocked | `.project-to-act/tasks/PIPELINE-V2-M1-013/evidence/E-20260828-PIPELINE-V2-M1-013.md` | M1 contract/prompt/dataset/evaluator/model config/Provider 底层或生产路由变化前 |
| E-20260828-PIPELINE-V2-DESIGN-012-R1 | 2026-08-28 | Draft 2020-12 Schema/meta-schema 与条件正反例、Prompt/Markdown/链接/空白、Project-to-Act/Lifecycle validate | 0 | doc `8DDD5454...1F6A5C`；schema `ED78F002...E436C`；Lifecycle rev 5 | v1.1；5 输入+5 输出；Stage 4 conditional、Stage 5 ready；0 Provider、0 生产代码 | `.project-to-act/tasks/PIPELINE-V2-DESIGN-012/evidence/E-20260828-PIPELINE-V2-DESIGN-012-R1.md` | V2 节点、Prompt/Schema、Gate、模型/数据/恢复策略或实现路线变化前 |
| E-20260828-PIPELINE-V2-DESIGN-012 | 2026-08-28 | JSON/meta-schema、Prompt/Markdown/链接、治理验证与 git diff check | 0 | doc `671F5A54...4FA0`；schema `3DECBA73...53AB` | 5 Prompt；Schema/meta-schema/6 links/治理通过；0 Provider、0 生产代码；不代表实现或质量 Gate | `.project-to-act/tasks/PIPELINE-V2-DESIGN-012/evidence/E-20260828-PIPELINE-V2-DESIGN-012.md` | V2 节点职责、Prompt、Schema、Gate 或实现路线变化前 |
| E-20260828-R6-ALIYUN-009 | 2026-08-28 | Renderer golden/provenance/registry + URL 回归 + Ruff/Mypy/完整 Pytest + 百炼单图/视觉初检 | 0（全仓 Mypy 的 3 个既有非本任务错误单列） | renderer `eb798625...cdc63`；PNG `ecd6bfc2...f5d4` | 225 tests；24 Prompt clauses；1 张 1328×1328 qwen-image-plus 候选；baseline 未批准 | `.project-to-act/tasks/R6-ALIYUN-009/evidence/E-20260828-R6-ALIYUN-009.md` | Renderer、golden、Provider/model/spec、工作流默认值或图片 Gate 变化前 |
| E-20260828-R1-GOLD-RUN-010 | 2026-08-28 | 31 seed + 6 real 的 DeepSeek v2.5/v2.6 同链路 A/B + candidate/grounding/scorer 归因 | 正式运行 0；首次沙箱网络预检失败 | report `6F8560A9...0BAB9`；analysis `DFE3706B...60C44` | 74/74 calls；242,288 tokens；v2.6 不切换；确认测量与系统双重问题 | `.project-to-act/tasks/R1-GOLD-RUN-010/evidence/E-20260828-R1-GOLD-RUN-010.md` | Prompt、模型、Schema、rubric、adapter 或样例变化前 |
| E-20260828-R1-GOLD-008 | 2026-08-28 | v1/真实 manifest 加载 + 评分正反例 + v0 重放 + v1 Mock + 定向/完整 Pytest + Ruff/Mypy | 0 | v1 `E5986D4A...CC2284`；real `220DAE89...9796A` | 31 hard case、6 real audit slices；21 targeted/225 full；120 source files；0 真实调用 | `.project-to-act/tasks/R1-GOLD-008/evidence/E-20260828-R1-GOLD-008.md` | Prompt、Schema、rubric、字段政策或真实样例变化前 |
| E-20260827-R1-PROMPT-AB-007 | 2026-08-27 | 同链路 v2.5/v2.6 三轮 DeepSeek A/B + 真实/seed 审核 + 定向/完整 Pytest + Ruff/Mypy | 工程 0；v2.6 切换 Gate 失败 | 见任务 evidence | 130 calls；426,190 tokens；0 Schema failure；49 targeted/203 full；默认 v2.5，保留 v3.4 门禁 | `.project-to-act/tasks/R1-PROMPT-AB-007/evidence/E-20260827-R1-PROMPT-AB-007.md` | Prompt、模型、Schema、样例或 rubric 变化前 |
| E-20260827-R6-IMAGE-SPEC-008 | 2026-08-27 | expected-field/spec/readiness/submit-unknown 反例 + 定向/完整 Pytest + Ruff/Mypy | 0 | 见任务 evidence | 6 targeted、202 full；117 source files；0 真实调用/迁移 | `.project-to-act/tasks/R6-IMAGE-SPEC-008/evidence/E-20260827-R6-IMAGE-SPEC-008.md` | 字段/provenance/readiness/compiler/provider port/submit 语义变化前 |
| E-20260827-R1-DATA-006 | 2026-08-27 | mention/field/locator/R2 边界反例 + Ruff/Mypy/单元/完整 Pytest | 0 | 见任务 evidence | 154 unit、193 full；7/7 基线转绿；0 API calls；无迁移 | `.project-to-act/tasks/R1-DATA-006/evidence/E-20260827-R1-DATA-006.md` | R1/R2 Schema、Prompt、字段或 locator 变化前 |
| E-20260827-R1-BASELINE-005 | 2026-08-27 | R1 fixture/strict-xfail + 定向/完整 Pytest + Ruff | 定向/重跑 0；默认 temp 首次 1 | fixture `16855126...E7F39C`；test `BD1FED06...4929D` | 定向 28 passed / 5 xfailed；完整 175 passed / 5 xfailed；0 生产代码与 0 真实 API calls | `.project-to-act/tasks/R1-BASELINE-005/evidence/E-20260827-R1-BASELINE-005.md` | R1 mention、字段门禁或 evidence locator 变化前 |
| E-20260827-R2-SHARD-004-CAL1 | 2026-08-27 | 历史覆盖计数校准 + 四重预算/Provider/Inspector 回归 + Ruff/Mypy/Node/完整 Pytest | 0 | 见任务 evidence | 172 tests；默认值 16 records/32 mentions/12k input/4.5k output；0 新真实 API calls | `.project-to-act/tasks/R2-SHARD-004/evidence/E-20260827-R2-SHARD-004-CAL1.md` | 分片策略、Prompt/Schema、Provider、估算器或配置变化前 |
| E-20260827-R2-SHARD-004 | 2026-08-27 | shard/repair/警告/恢复/Inspector 反例 + Ruff/Mypy/Node/完整 Pytest | 0 | 见任务 evidence | 171 tests；三重预算分片、有限 repair、耗尽 warning 与恢复通过；0 真实 API calls | `.project-to-act/tasks/R2-SHARD-004/evidence/E-20260827-R2-SHARD-004.md` | 分片/repair、R2 Schema、事件/Inspector 或配置变化前 |
| E-20260827-R2-FRONTIER-003 | 2026-08-27 | frontier/跨批 unresolved/trace 反例 + Ruff/Mypy/Node/定向与全量 Pytest | 0 | 见任务 evidence | 18 项定向测试与全量回归通过；旧 unresolved 不重复提交且完整 memory 保留 | `.project-to-act/tasks/R2-FRONTIER-003/evidence/E-20260827-R2-FRONTIER-003.md` | frontier、R2 收敛事件或 Inspector 变化前 |
| E-20260827-R2-MEMORY-002 | 2026-08-27 | memory 选择/保留/trace 反例 + Ruff/Mypy/Node/定向与全量 Pytest | 0 | 见任务 evidence | 26 项定向测试与全量回归通过；逐 Chunk 模型视图有界且完整 memory 不丢失 | `.project-to-act/tasks/R2-MEMORY-002/evidence/E-20260827-R2-MEMORY-002.md` | memory 选择、R2 事件或 Inspector 变化前 |
| E-20260826-R1-PROMPT-003 | 2026-08-26 | 17 次独立 v3 调用 + 字段/原子结构审核 + Ruff/Mypy/Pytest | 0 | 见任务 evidence | v2.1 字段结构 7/7；v2.2 定向 3/3；121 tests；32,280 tokens | `.project-to-act/tasks/R1-PROMPT-003/evidence/E-20260826-R1-PROMPT-003.md` | Prompt、模型或评测变化前 |
| E-20260826-R1-EVAL-004 | 2026-08-26 | rubric v2 边界测试 + 保存结果离线重评分 + Ruff/Mypy/Pytest | 0 | 见任务 evidence | v2.2：2 pass / 1 review / 0 fail；126 tests；0 API calls | `.project-to-act/tasks/R1-EVAL-004/evidence/E-20260826-R1-EVAL-004.md` | 评测器、rubric 或种子数据变化前 |
| E-20260826-R1-EVAL-002 | 2026-08-26 | 两次真实 v3 诊断 + 人工差异审核 + Ruff/Mypy/Pytest | 0 | 见任务 evidence | 25 case；119 tests；7,535 tokens | `.project-to-act/tasks/R1-EVAL-002/evidence/E-20260826-R1-EVAL-002.md` | 配置变化前 |
| E-20260827-R2-ENTITY-001 | 2026-08-27 | R2 单元/集成反例 + Ruff/Mypy/Alembic/Pytest | 0 | 见任务 evidence | 129 tests；实体定向 2 tests；0 真实 API calls | `.project-to-act/tasks/R2-ENTITY-001/evidence/E-20260827-R2-ENTITY-001.md` | R2 Schema/Prompt/收敛/迁移变化前 |
| E-20260827-R3-PHASE-001 | 2026-08-27 | R3 单元/流水线/API 反例 + Ruff/Mypy/Alembic/Pytest | 0 | 见任务 evidence | 135 tests；114 source files；唯一 head a3e8c1d4f620；0 真实 API calls | `.project-to-act/tasks/R3-PHASE-001/evidence/E-20260827-R3-PHASE-001.md` | R3 Schema/解析/门禁/迁移变化前 |
| E-20260827-R123-REAL-001 | 2026-08-27 | 19 Chunk 隔离 DeepSeek 全链路 + DB/summary 人工审核 + Ruff/Mypy/Pytest | 工程 0；质量 Gate 失败 | source SHA256 `8bcb7305...9741`，其余见任务 evidence | 工程 succeeded；R2 人物污染、R3 零阶段、聚合默认锚点污染；144 tests 通过；246,633 recorded tokens | `.project-to-act/tasks/R123-REAL-001/evidence/E-20260827-R123-REAL-001.md` | R1/R2/R3/模型配置变化前 |
| E-20260827-OBS-RUN-001 | 2026-08-27 | Inspector API/UI 反例 + Ruff/Mypy/Pytest + Node + 浏览器桌面/720px | 0 | 见任务 evidence | 三阶段摘要与四类下钻通过；115 source files；146 tests；0 真实 API calls | `.project-to-act/tasks/OBS-RUN-001/evidence/E-20260827-OBS-RUN-001.md` | Inspector Schema、业务表、RunEvent usage 或 UI 变化前 |
| E-20260827-DEV-RAW-001 | 2026-08-27 | raw Provider/Settings/API/迁移反例 + Ruff/Mypy/Node/159 Pytest + 浏览器 | 0 | 见任务 evidence | R1/R2 raw、管理员门禁、生产失败关闭、UI 页签通过；0 真实 API calls | `.project-to-act/tasks/DEV-RAW-001/evidence/E-20260827-DEV-RAW-001.md` | raw Schema、Provider、表、权限或 UI 变化前 |

## Gate 记录

| Gate ID | 日期 | Gate | 对象 | 结果 | 证据 ID | 豁免与确认人 |
|---|---|---|---|---|---|---|
| G-PIPELINE-V2-DESIGN-012-R1 | 2026-08-28 | 语义流水线 V2 v1.1 架构与契约完整性 | PIPELINE-V2-DESIGN-012 | Stage 4 条件通过、Stage 5 ready；条件为 P0 冻结 promotion coverage 与人工 review capacity 数值阈值；不代表实现或质量通过 | E-20260828-PIPELINE-V2-DESIGN-012-R1 | 用户确认总体方向并要求修补；P0 阈值仍待用户确认 |
| G-PIPELINE-V2-DESIGN-012 | 2026-08-28 | 质量优先语义流水线 V2 设计完整性 | PIPELINE-V2-DESIGN-012 | 设计工件完成、待用户评审；不代表 P0、实现、真实质量或阶段 5 通过 | E-20260828-PIPELINE-V2-DESIGN-012 | 用户待确认设计与初始 Gate |
| G-R6-ALIYUN-009 | 2026-08-28 | PromptRenderer 与真实阿里云单图纵向切片 | R6-ALIYUN-009 | 条件通过：Renderer/Provider/真实 PNG 通过；数据库无 approved/locked Profile，用户审批、漂移 Gate、baseline 锁定和批量生成不通过 | E-20260828-R6-ALIYUN-009 | 待用户审批候选图 |
| G-R1-GOLD-RUN-010 | 2026-08-28 | R1 v1 首轮真实 A/B 与测量有效性 | R1-GOLD-RUN-010 | 运行/归因通过；v1 发布硬 Gate 暂不通过，v2.6 不切换，先修测量层并离线重评分 | E-20260828-R1-GOLD-RUN-010 | 无 |
| G-R1-GOLD-008 | 2026-08-28 | R1 黄金集与确定性评分契约 | R1-GOLD-008 | 通过（仅数据、评分器与工具；未重跑真实 Provider，不改变 v2.5/v2.6 或 R2/R3 质量结论） | E-20260828-R1-GOLD-008 | 无 |
| G-R1-PROMPT-AB-007 | 2026-08-27 | R1 Prompt v2.5/v2.6 真实 A/B 与 v3.4 安全门禁 | R1-PROMPT-AB-007 | 部分通过：实验链、v3.4 门禁和完整回归通过；v2.6 默认切换不通过，继续使用 v2.5 | E-20260827-R1-PROMPT-AB-007 | 无 |
| G-R6-IMAGE-SPEC-008 | 2026-08-27 | 期望字段到 Mock 生图规格纵向切片 | R6-IMAGE-SPEC-008 | 通过（仅契约、Mock 编排与失败关闭；真实字段、视觉质量、收费 Provider、审计/gate/baseline 未通过，禁止批量生图） | E-20260827-R6-IMAGE-SPEC-008 | 无 |
| G-R1-DATA-006 | 2026-08-27 | R1 基础数据与证据门禁增量 | R1-DATA-006 | 通过（自动化与兼容边界；真实新 Run 的 Prompt 质量和跨作品召回仍待复核） | E-20260827-R1-DATA-006 | 无 |
| G-R1-BASELINE-005 | 2026-08-27 | R1 数据质量测试基线冻结 | R1-BASELINE-005 | 通过（仅表示红灯/绿灯边界已冻结；5 项生产行为仍未实现，不代表 R1 质量 Gate 通过） | E-20260827-R1-BASELINE-005 | 无 |
| G-R2-SHARD-004-CAL1 | 2026-08-27 | R2 收敛预算失败数据校准 | R2-SHARD-004 | 通过（历史样本与自动化；真实新 Run 的覆盖率、成本、延迟及 stable context 检索仍待后续） | E-20260827-R2-SHARD-004-CAL1 | 无 |
| G-R2-SHARD-004 | 2026-08-27 | R2 收敛预算分片与 omission repair 增量 | R2-SHARD-004 | 通过（自动化与 Inspector 契约；真实 token 降幅、repair 成功率、stable context 检索和 final sweep 仍待后续） | E-20260827-R2-SHARD-004 | 无 |
| G-R2-FRONTIER-003 | 2026-08-27 | R2 十章收敛 dirty frontier 增量 | R2-FRONTIER-003 | 通过（自动化与 Inspector 契约；单 frontier 分片、repair 和真实 token 降幅仍待后续） | E-20260827-R2-FRONTIER-003 | 无 |
| G-R2-MEMORY-002 | 2026-08-27 | R2 逐 Chunk memory 容量治理增量 | R2-MEMORY-002 | 通过（自动化与 Inspector 契约；真实 token 降幅和十章收敛容量仍待后续） | E-20260827-R2-MEMORY-002 | 无 |
| G-R1-PROMPT-003 | 2026-08-26 | R1 通用语义 Prompt 增量 | R1-PROMPT-003 | 通过（保留严格字符串与 v2.2 全量复测缺口；不代表 R1 阶段通过） | E-20260826-R1-PROMPT-003 | 无 |
| G-R1-EVAL-004 | 2026-08-26 | R1 评测器三态边界增量 | R1-EVAL-004 | 通过（review 写回仍为人工流程；不代表 R1 阶段通过） | E-20260826-R1-EVAL-004 | 无 |
| G-R1-EVAL-002 | 2026-08-26 | R1 跨题材差异回灌 | R1-EVAL-002 | 通过（不代表 R1 阶段通过） | E-20260826-R1-EVAL-002 | 无 |
| G-R2-ENTITY-001 | 2026-08-27 | R2 实体解析基础主链增量 | R2-ENTITY-001 | 通过（仅实现与自动回归；不代表 R2 质量 Gate、阶段 5 或生产发布通过） | E-20260827-R2-ENTITY-001 | 无 |
| G-R3-PHASE-001 | 2026-08-27 | R3 阶段与时间作用域基础主链增量 | R3-PHASE-001 | 通过（仅实现与自动回归；不代表 R3 跨作品质量 Gate、阶段 5 或生产发布通过） | E-20260827-R3-PHASE-001 | 无 |
| G-R123-REAL-001 | 2026-08-27 | R1/R2/R3 真实语义质量 | R123-REAL-001 | 不通过（工程链路通过；禁止据此进入批量生图） | E-20260827-R123-REAL-001 | 无 |
| G-OBS-RUN-001 | 2026-08-27 | R1–R3 Run Inspector 纵向切片 | OBS-RUN-001 | 通过（仅可观测性入口；不代表真实语义质量、阶段 5 或生产发布通过） | E-20260827-OBS-RUN-001 | 无 |
| G-DEV-RAW-001 | 2026-08-27 | 开发模型原始响应查看器 | DEV-RAW-001 | 通过（成功且 Schema 有效的调用；不含失败 raw、清理策略或 token streaming） | E-20260827-DEV-RAW-001 | 无 |

## 验收记录

按时间倒序追加：日期、检查范围、证据 ID、结果、遗留问题和结论。失败、跳过与过期证据也必须如实记录。

- 2026-08-28：PIPELINE-V2-DESIGN-012 根据用户复核升级为 `semantic-pipeline-v2-design-v1.1`。Draft 2020-12 Schema 含 5 个输入、5 个输出和 BoundaryRef，M2/M3/M4/M5 条件正反例通过；5 Prompt、6 链接、代码围栏和目标文件空白检查通过。生命周期 Stage 5 返回 Stage 4 完成条件架构 Gate后，Stage 5 为 ready/revision 5。0 Provider、0 生产代码/迁移；P0、真实质量、promotion coverage 与人工容量数值阈值仍未通过或冻结。证据 `E-20260828-PIPELINE-V2-DESIGN-012-R1`。
- 2026-08-28：PIPELINE-V2-DESIGN-012 形成 `semantic-pipeline-v2-design-v1` 评审稿：N0-N11 节点、M1-M5 单职责 Prompt/Schema、downgrade-only 复核、确定性 Promotion、效果漏斗、质量优先 Gate、成本护栏与离线/shadow/灰度/回滚路径已定义。当前未修改生产代码、未调用 Provider、未运行 P0 或真实质量评测，因此 Gate 仅为设计待用户评审。
- 2026-08-28：R1-GOLD-RUN-010 正式真实 A/B 74/74 调用成功。v2.5 seed 为 13 pass/7 review/11 fail，v2.6 为 12/7/12；B tokens +27.9%、deferred 与 asserted/deferred 双写增加，因此不切换。逐层审计同时确认测量问题与真实系统问题：当前 v1 工程契约可运行，但在阶段键、temporal、owner alias、safe deferred、raw mention 和部分真实标注修正前，不得作为发布硬 Gate；现有报告应先离线重评分。
- 2026-08-28：R6-ALIYUN-009 在既有版本化 Renderer 与 DashScope 首图基础上增加 `openai-compatible-image-v1` 和 `timicc/gpt-image-2`。23 项定向、230 项完整 Pytest、Ruff、修改范围 Mypy 通过；同步 base64 图片具备进程重启可恢复暂存与完整性验证。一次真实调用成功并保存 1024×1536 PNG；请求为 1328×1328，尺寸漂移已留证，故只判 Provider/model 可用，不判 baseline Gate 通过；数据库没有 approved/locked Profile，仍不开放批量。
- 2026-08-28：R6-ALIYUN-009 完成版本化/可插拔 PromptRenderer、逐短句 provenance、golden test、官方共享 URL 修复及一张 `qwen-image-plus` 真实候选。225 项完整 Pytest、Ruff、修改范围 Mypy 通过；图片 1328×1328，主要字段命中，脸部细节和偏动画/3D 风格待用户判断。数据库没有 approved/locked Profile，故 Gate 仅条件通过，产物保持 `Baseline Candidate v1`，不锁定 baseline、不开放批量。
- 2026-08-28：R1-GOLD-008 黄金数据与评分契约 Gate 通过；v0 未变，v1 的 31 个硬黄金 case 与 6 个真实审计切片均能从原文严格加载，required/allowed/forbidden、mention/deferred/temporal 及重复/双写指标有自动正反例。21 项定向、225 项完整 Pytest、Ruff、Mypy src 通过，旧 v0 报告重放成功，0 真实调用。该结论不代表生产 Prompt 已在 v1 上通过；历史 v0 A/B 仍只作历史证据。
- 2026-08-27：R1-PROMPT-AB-007 完成三轮真实 DeepSeek A/B。最终轮 A/B 的 TP/FP/FN 同为 16/4/1，B 的 pass/review/fail 从 3/5/3 改善为 5/3/3、年龄信号改善到 3/3；但总 token 增加约 28%，deferred/warning/reject 分别从 4/32/27 增至 22/54/31，并在真实多人样例产生重复和 asserted/deferred 双写。故 v2.6 切换 Gate 不通过，默认保留 v2.5；向后兼容 v3.4 安全门禁、49 项定向、203 项完整 Pytest、Ruff、Mypy 通过。本结论不改变 R2/R3 与批量生图总体 Gate。
- 2026-08-27：R6-IMAGE-SPEC-008 Mock 纵向切片通过；期望字段适配、逐字段来源、draft 简报、三档失败关闭、稳定 spec/context hash、Provider 最小边界和 submit unknown 防重提均有自动正反例。6 项定向、202 项完整 Pytest、Ruff、Mypy 通过；未运行真实图像 Provider或视觉评测，不改变 `R123-REAL-001` 的批量生图禁令。
- 2026-08-27：R1-DATA-006 自动化增量通过；历史 5 项红灯全部转绿，四类 mention、旧标签兼容、age/clothing 失败关闭和分级引文修复/审计均有正反例。154 项单元、193 项完整 Pytest、Ruff、Mypy 通过；未运行真实 Provider，不改变整体 R2/R3 真实语义质量 Gate 未通过的结论。
- 2026-08-27：R1-BASELINE-005 基线冻结通过；独立 v1 fixture 和 strict-xfail 机制可执行，相关 R1 回归 28 passed / 5 xfailed、完整回归 175 passed / 5 xfailed、Ruff 通过。完整回归首次因系统默认临时目录权限退出 1，切换至项目内全新 basetemp 后通过。该 Gate 仅确认失败边界已留痕；descriptor、`age.age`、非衣物服装门禁和窄引文修复仍未实现，R2 身份质量不在本 Gate 内。
- 2026-08-27：R2-SHARD-004 失败数据校准自动化增量通过；四重预算、Provider Prompt/Schema 输入开销、Trace/Inspector/UI、39 项定向、172 项完整 Pytest、Ruff、Mypy 和 Node 均通过。没有运行新真实 Provider，32/16/12k/4.5k 仍是保守起点，不构成最终 p95/p99 容量结论。
- 2026-08-27：R2-FRONTIER-003 自动化增量通过；frontier 选择、旧 unresolved 保留不重跑、新 mention 重新激活、Provider 原始覆盖/omission trace、全量 Pytest、Ruff、Mypy 和 Node 均通过。未运行真实付费 Provider；分片、repair、stable context 检索及有界 final sweep 不在本 Gate 内。
- 2026-08-27：R2-MEMORY-002 自动化增量通过；相关 memory 选择、隐藏历史保留、事件/Inspector 数据边界、全量 Pytest、Ruff、Mypy 和 Node 均通过。未运行真实付费 Provider，新 Run 的实际 token 降幅及十章收敛输入/输出膨胀不在本 Gate 内。
- 2026-08-27：DEV-RAW-001 开发增量通过；R1/R2 raw 持久化、管理员页签、生产失败关闭、迁移、159 项完整测试和浏览器检查通过。旧 Run 不补录；失败 Schema raw、保留期限和 token streaming 明确未覆盖。
- 2026-08-27：OBS-RUN-001 纵向切片通过；R1/R2/R3 摘要、结构化下钻、404/正文边界、全量静态/测试和响应式视觉检查均通过。保留 OTel、生产采样/留存、Langfuse 与黄金集质量指标缺口；不改变 R123-REAL-001 的真实语义质量 Gate 失败结论。
- 2026-08-27：R123-REAL-001 完成 19 Chunk 真实 DeepSeek 全链路；checkpoint 与工程回归通过，但唐三/唐昊实体污染、0 life phases、变身外观污染默认锚点，故真实语义质量 Gate 明确判定不通过，不进入批量生图。
- 2026-08-27：R3-PHASE-001 基础主链增量通过；135 项全量测试、114 个源码文件类型检查、唯一 Alembic head 和迁移测试通过；“前世黑发”不会把阶段扩散到“三年后白衣”，后者保持审核态。保留真实 Provider phase/scope 质量、复杂 timeline/event 和审核后自动重聚合缺口。
- 2026-08-27：R2-ENTITY-001 基础主链增量通过；129 项全量测试、110 个源码文件类型检查和迁移升降级通过，“另一男孩”特征不进入唐三。保留真实模型跨作品质量、成本和延迟评测，不宣称 R2 完整 Gate。
- 2026-08-26：R1-EVAL-004 增量验证通过；未知 value 保守进入 review，已接受等价值自动通过，结构与无证据错误保持 fail；126 项测试通过。保留“review 写回为人工流程”和“种子集 25/30–40”两个缺口。
- 2026-08-26：R1-PROMPT-003 增量验证通过；七类语义字段错配未复现，Prompt 无作品特例，121 项本地测试通过。保留“最终 v2.2 未全量付费复测”和“严格值/证据评分过于表面化”两个缺口。
- 2026-08-26：R1-EVAL-002 增量验收通过；两次真实调用和本地回归均成功。保留“新 Prompt 未付费复测”和“尚未达到 30–40 case”两个非阻断缺口。
