# PIPELINE-V2-M1-013 Handoff

## 当前目标

只完成 M1 局部观察发现的 shadow/offline 纵向切片和独立效果测量闭环；不切换 V1，不开始 M2。

## 用户 Gate

实现和自动测试完成后，必须把 `tests/evaluation/m1_local_observation_discovery_v1.json` 交给用户逐项审核。测试集未批准时，只能声明工程 Gate 通过，不能声明 M1 模型效果通过。

当前进度：工程 Gate 已通过；用户已授权 v1 完成一次 15-case 真实开发基线。测量修正后的 `v1.1-draft2` 为 11 pass / 0 review / 4 fail，模型质量 Gate 不通过，且修正版数据集重新等待用户审核。下一步只能审核 draft2、修 M1，或建立新的 held-out 验收集；不得直接开始 M2。

## 删除边界

本阶段保留仍被 Worker、历史回放或 V1 回滚使用的旧抽取代码与测试。允许删除的内容仅限本任务产生后被证明重复、未引用且已有等价覆盖的实现或测试，并在证据中记录引用审计。

已完成的整理：

- 删除 docs 下重复的 M1 Prompt，运行时 package Prompt 成为唯一来源；
- R1、R2、M1 共用 `OpenAICompatibleStructuredClient`，删除 R1/R2 重复 HTTP/超时/重试/usage 循环和无用连接字段；
- 引用审计确认 V1 DTO、Prompt、adapter、Worker 与历史数据集仍承担生产/回滚职责，因此保留。

## 禁止扩张

- 不写 active Observation 或迁移数据库。
- 不改变 Worker 默认 Provider、Prompt 或路由。
- 不实现 M2–M5。
- 不读取或泄露 `.env` 凭据，不发起真实 Provider 调用。

## 验证

- 首次真实联网基线：15/15 一次成功，31,697 tokens，0 Schema/契约失败；
- `v1.1-draft2` 离线重评：11 pass / 0 review / 4 fail，事实召回 86.7%，信号召回/精度均 25%；
- 工程完整回归与治理的最新结果见 `E-20260828-PIPELINE-V2-M1-013-REAL1`；
- 真实 Provider 调用：15；数据库迁移与默认路由切换：0。
