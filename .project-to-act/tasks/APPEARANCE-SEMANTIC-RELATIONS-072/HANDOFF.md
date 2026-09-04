# APPEARANCE-SEMANTIC-RELATIONS-072

任务已完成。Stage 5 保持 `in_progress`，lifecycle revision 仍为 2。

首版候选面经过斗罗 dev23 审计：109 个 observed facts 中有 16 个“同人物 + 同 StateSegment + 同 exact attribute”的多事实组，共 37 个 pair。dev24 已实现确定性 baseline：相等值为 equivalent，长度至少 2 的安全子串为 compatible，其余为 unclassified；不在没有 active applicability 的情况下猜 true conflict。

关系图已集成进 `document-character-appearance-states-v5`，并且只从 equivalent 连通分量派生 normalized propositions。真实输出为 37 relations（7 equivalent、5 compatible、25 unclassified）和 103 propositions；raw 值与事实引用未被覆盖，新增语义 Provider 调用为 0。

全量回归为 `171 passed, 13 subtests passed`；compileall、Draft 2020-12 真实实例、diff check 与两套治理校验通过。17/17 保存的 transition 输出再次离线恢复，new Provider calls 为 0，artifact SHA-256 稳定为 `83D1A87EDFE83A8591122AEC5754861AFEE26D5531D0506C2639B74577071CDB`。

下一任务为 073 Label/Review 投影。active applicability、不可兼容事实的有效期重叠判断及完整 true-conflict Gate 继续留在 render compiler 前的后续切片；当前 25 条 unclassified 不得静默降级或强制归类。
