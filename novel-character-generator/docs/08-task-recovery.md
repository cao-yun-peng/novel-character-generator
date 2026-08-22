# 任务系统与断点恢复

> [← 上一篇](07-agent-architecture.md) · [文档索引](README.md) · [下一篇 →](09-api-specification.md)
>
> 文档版本：2.7 · 源章节：11. 任务系统与断点恢复 · 修订日期：2026-08-22

## 11. 任务系统与断点恢复

### 11.1 一期数据库任务队列

一期使用 `pipeline_runs` 和 `pipeline_steps` 作为 durable queue，由单 Worker 原子领取任务：

1. API 在事务内创建 Run 和初始 Step，返回 run ID；
2. Worker 使用条件更新领取 `queued/retry_scheduled` 任务；
3. 设置 `lease_owner`、`lease_expires_at` 和心跳；
4. 每个步骤开始前检查是否已有成功结果；
5. 外部请求提交前创建 `external_operations(prepared)`，以 request fingerprint 和幂等键唯一约束；
6. 提交窗口开始时写入 `submitting`，提交后立即保存 external job ID 并转为 `submitted`；
7. 若进程在提交窗口崩溃且无法证明是否已提交，转为 `submission_unknown` 并进入对账，不直接重提；
8. Worker 崩溃后，租约过期任务可被重新领取，所有写入使用 `lease_generation` fencing；
9. 已提交的外部任务优先查询状态，不盲目再次提交。

### 11.2 重试策略

| 错误 | 策略 |
|---|---|
| 网络超时且未知是否提交 | 先按幂等键或 request ID 查询 |
| 429/限流 | 指数退避 + jitter，尊重 Retry-After |
| Provider 5xx | 有上限重试，记录每次尝试 |
| JSON 校验失败 | 一次本地提取/修复，再一次受限模型修复 |
| 内容安全拒绝 | 不自动重试，进入人工处理 |
| 参数/工作流错误 | 立即失败，不消耗重复费用 |
| 取消请求 | 在安全检查点停止；已提交远程任务尽量取消或等待回收 |

### 11.3 并发和 Session

- 每个 Worker 任务拥有独立 `AsyncSession`；
- `asyncio.gather()` 中每个并发分支创建自己的 Session；
- 不在网络等待期间保持数据库事务；
- SQLite 一期只允许单写 Worker，并设置 WAL 和 busy timeout；
- 图像候选可以由 Provider 端并发，但本地状态更新串行提交。

### 11.4 二期升级

当需要多 Worker、优先级、定时任务或高吞吐时，迁移至 PostgreSQL + Redis 队列，并选用 Dramatiq/Celery 等成熟执行器。应用层只依赖 `TaskDispatcher` 端口，不改领域逻辑。

---

[← 上一篇](07-agent-architecture.md) · [文档索引](README.md) · [下一篇 →](09-api-specification.md)
