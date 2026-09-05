# R03/R02 真实 API 测试与 Snapshot 验证

2026-09-05，任务 SEMANTICS-LIVE-081，运行时 0.1.0.dev31，Schema 3.30.0-draft1。用户明确授权向配置的 DeepSeek 发送小说片段及派生事实并承担调用费用；此前审批阻塞已解除。

## 实测结果

输入为 `tests/小说/斗罗大陆前20章.txt`，实际含 19 章、38,251 字符；复用斗罗 dev18 post-link facts、dev29 states、dev25 labels 和既有 M1 manifest。本次不是从 M1/M2 重新解析全文，也未重新验证历史事实准确率。

使用 deepseek-v4-flash / responses-v1，17 个原文块事件任务与 35 个关系任务全部完成。累计 53 次 HTTP 请求：52 次成功、1 次因 max_output_tokens 截断失败；保持原配置重试失败任务，复用其余 51 个缓存，成功补齐。失败尝试仍保留在脱敏 trace 中，最终 failures.json 仅表示当前未完成任务。

| 指标 | 结果 |
|---|---:|
| 模型事件 | 8：6 scene_boundary、1 remove、1 wear |
| 接受事件 | 7：6 scene_boundary、1 remove |
| 事件复核 | 1：wear 的目标事实缺失或歧义 |
| 关系 | 35：21 compatible、6 equivalent、5 incompatible、3 uncertain |
| 离线重放新增调用 | 0 |
| Schema / 重新 Grounding / Snapshot | 通过，4 个查询 |
| 4 个查询的真实冲突 | 0；不兼容候选不等于当前双方 active |

成功请求已知用量：输入 78,499、输出 22,921、合计 101,420 tokens，其中 reasoning 21,288、cached input 25,728。失败请求用量缺失，因此不是完整计费量；本报告不推算费用。

## 实测推动的修复

部分关系响应重复提供同一 evidence_quote。旧代码保存重复绑定，而消费阶段先去重再重新定位，造成同一结果无法通过一致性校验。dev31 在关系 Grounding 时按首次出现顺序去重；原模型响应、请求指纹、输入和 Schema 不变。新增重复引文→保存→Snapshot 回归；260 tests、19 subtests 通过。首次测试因默认临时目录权限出现 setup errors，改用工作区内独立临时目录后通过全量测试。

原始结果保留于 `runs/semantic-dev30/douluo-live/`，不得将其当作已修复的派生产物。修复后从全部 52 份原始响应零调用重放，交付目录为 `runs/semantic-dev30/douluo-live-replay-dev31/`：

- `automatic-semantics.json`：供 Snapshot 与旧人物卡编译消费的有效产物。
- `verification-report.json`：统计、用量和验证结果。
- `verified-snapshots.json`：唐三、素云涛各两个既有选择器的快照。
- `model-event-audit.json`、`model-relation-audit.json`：原模型判断供人工审阅。
- `rejected-output-audit.json`：老杰克穿新衣事件未能唯一绑定既有事实，保留复核。

## 质量边界与下一步

代码校验只证明证据和引用可回放，不证明模型语义正确。模型将“该是回去的时候了”等计划性描述判断为 scene_boundary，需人工核查是否误把意图当作实际转场；换装仅有一个 remove 被接受，不能据此宣称换装召回达标。5 条 incompatible 仍需核查同部位、同层次和上下文；本次 4 个真实快照没有覆盖双方 active 的真实冲突。该路径已有可控响应工程回归，尚缺人工标注真实样本验证。

R06 冻结标注、事件召回、关系精度及总体质量门槛仍待完成。Stage 6 保持 in_progress、revision 4；本次完成 API 实测和工程修复，不通过人工质量 Gate。
