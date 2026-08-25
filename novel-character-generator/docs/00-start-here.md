# 从这里开始：这个项目到底做什么

> [文档索引](README.md) · [当前实现状态](00-current-status.md) · [代码导航](00-code-navigation.md)
>
> 文档版本：3.0 · 修订日期：2026-08-24

## 一句话说明

这个项目把一部长篇小说转换成“有原文证据、有时间阶段、可人工确认”的角色视觉档案，并最终用这些档案生成同一角色在不同历史阶段的一致形象。

它不是普通的“输入角色名就画图”，重点解决三个更难的问题：

1. 小说里关于角色的描述散落在不同章节，甚至互相矛盾。
2. 同一个角色会变老、受伤、换装、伪装，不能压缩成唯一外观。
3. 图像模型容易把其他阶段、其他时间线或自己编造的特征混进结果。

## 用户最终会得到什么

以角色“林岚”为例，系统最终希望提供：

- 她在原文中出现过的名字、别名和称谓；
- “黑发”“左眉有疤”“成年后右臂受伤”等带原文位置的观察事实；
- 少年期、成年期、受伤后等互不覆盖的阶段外观；
- 经过人工批准的稳定身份锚点和配色；
- 每个关键阶段的一组候选图和一张锁定基准图；
- 任何生成图都能追溯到小说版本、证据、时间线、档案版本、Prompt、模型、seed 和费用。

## 完整业务流程

```text
上传 TXT 小说
  → 识别章节并切成可处理文本块
  → 从每个文本块批量提取角色、称谓、外貌和证据
  → 处理同名、别名、误合并和误拆分
  → 区分叙事顺序与故事时间，识别回忆、梦境和分支时间线
  → 聚合稳定身份、阶段外观与场景临时状态
  → 人工解决冲突并批准角色渲染档案
  → 在指定时间点解析不可变外观快照
  → 生成候选角色图
  → 检查身份、年龄、伤势、服装和时间线漂移
  → 人工选择并锁定阶段基准图
```

这条流程目前不是全部完成状态。文本导入、角色提取、任务恢复、人物合并/拆分、时间绑定修正以及档案快照等基础已经落地；图像生成、视觉防漂移和完整日志检查仍待实现。准确边界见[当前实现状态](00-current-status.md)。

## 现在实际能跑通什么

当前可从公开 API 和 Worker 跑通的主链是：

```text
POST /api/v1/novels
  → 创建小说与不可变源文档版本

POST /api/v1/novels/{novel_id}/runs
  → 创建文本分析 Run

Worker
  → normalize_and_chunk
  → extract_characters
  → aggregate_appearance

GET /api/v1/runs/{run_id}
GET /api/v1/runs/{run_id}/events
  → 查询状态或通过 SSE 查看进度

GET /api/v1/novels/{novel_id}/characters
GET /api/v1/characters/{character_id}/observations
GET /api/v1/characters/{character_id}/appearance-states
GET /api/v1/characters/{character_id}/conflicts
  → 查看角色、原文证据、人生阶段、外观状态与冲突
```

随后可以通过 API：

- 查询时间线、事件和场景，并修正场景时间绑定；
- 合并被重复识别的角色，或拆分被错误合并的角色；
- 查询人物外观状态、冲突、渲染档案与目标时点快照；
- 处理需要管理员批准的 Agent 或业务动作；
- 取消、重试和恢复失败任务。

需要注意：真实 Observation 已能自动聚合为阶段状态、冲突和待审核档案，人工确认值也不会被后续自动运行静默覆盖。当前提取会把综合外观规范成原子视觉字段，并区分“前世”“转生幼年”等人生阶段；图像生成端点仍不存在。

## 五个最重要的概念

### 1. Observation：原文观察

Observation 表示“小说明确写了什么”，例如“她剪短了头发”。它必须关联原文版本、文本块、引用位置、时间范围和抽取运行，不能因为新结果出现就覆盖旧结果。

### 2. CharacterAppearanceState：阶段或场景状态

它表示角色在某段故事时间内是什么样子，例如少年期、长期伤势、伪装、当前服装或临时污渍。不同阶段可以同时保留。

### 3. CharacterRenderProfile：人工确认的生成档案

它不是原文事实集合，而是“哪些稳定属性和阶段可以用于出图”的人工决策。已批准或锁定的版本不会被后续抽取静默改写。

### 4. Resolved Snapshot：本次生成快照

生成时不能只传 `character_id`。系统必须先确定时间线、事件、场景或章节，再把有效状态合并成不可变快照，并计算哈希。

### 5. PipelineRun / PipelineStep：可恢复任务

上传、抽取和未来的图像生成都是长任务。Run 表示整次任务，Step 表示其中一步；租约、attempt 和 fencing 用来防止多个 Worker 重复写入或重复收费。

## 谁会使用系统

| 角色 | 主要操作 |
|---|---|
| 普通用户 | 上传小说、启动分析、查看角色与证据、选择生成阶段和候选图 |
| 审核人员 | 解决角色与外观冲突、批准渲染档案、选择阶段基准图 |
| 管理员 | 处理高风险审批、查看成本与任务异常、管理 Provider 和工作流版本 |
| 开发者 | 扩展抽取、时间解析、图像 Provider、评测器、日志检查和任务步骤 |

## 接下来读什么

- 想知道“已经实现到哪”：读[当前实现状态](00-current-status.md)。
- 想开始改代码：读[代码导航](00-code-navigation.md)。
- 想理解整体架构：读[架构蓝图与技术栈](02-architecture-and-tech-stack.md)。
- 想理解角色数据：读[领域模型与数据库设计](03-domain-data-model.md)和[角色渲染档案](05-character-render-profile.md)。
- 想实现出图：读[图像生成与视觉防漂移](06-image-generation-and-drift-control.md)。
- 想排查任务和日志：读[任务系统与断点恢复](08-task-recovery.md)和[可观测性、日志检查与成本](13-observability-logging-and-cost.md)。
- 想把项目实际跑起来：读[本地开发、部署与运维手册](16-local-development-and-runbook.md)和[API 调用手册](20-api-cookbook-and-error-catalog.md)。
- API 启动后想直接操作：打开 `http://127.0.0.1:8000/ui`；页面会根据 capability 隐藏尚未实现的图像能力。
- 想实现尚未闭合的主链：先看[外观聚合契约](17-appearance-aggregation-contract.md)、[图像生成实现契约](18-image-generation-implementation-contract.md)和[功能追踪矩阵](19-feature-traceability-matrix.md)。

---

[文档索引](README.md) · [当前实现状态 →](00-current-status.md)
