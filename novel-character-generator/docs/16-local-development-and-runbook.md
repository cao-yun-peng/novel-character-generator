# 本地开发、部署与运维手册

> [← 上一篇](15-risks-decisions-and-references.md) · [文档索引](README.md) · [下一篇 →](17-appearance-aggregation-contract.md)
>
> 文档版本：2.9 · 修订日期：2026-08-24
>
> 当前适用范围：`0.1.0`、Python 3.12、SQLite、本地产物目录、单写 Worker。二期 PostgreSQL/Redis/对象存储部署不适用本手册。

## 1. 运行拓扑

```text
客户端
  → FastAPI API 进程
      → SQLite
      → data/artifacts
  → Worker 进程
      → SQLite 领取 PipelineStep
      → Mock 或 OpenAI-compatible LLM
```

API 只接收请求和查询状态，Worker 推进长任务。即使开发时运行在同一台机器，也必须作为两个进程启动。一期 SQLite 只允许一个写 Worker；同时启动多个 Worker 可能放大锁竞争，不属于支持配置。

## 2. 首次安装

前置要求：

- Python `>=3.12,<3.13`；
- `uv`；
- PowerShell 7 或能够执行等价命令的终端。

在项目根目录执行：

```powershell
uv sync --dev
Copy-Item .env.example .env
uv run alembic upgrade head
uv run alembic current
```

默认 `.env.example` 使用 `LLM_PROVIDER=mock`，不调用远程模型，适合烟雾测试。若使用远程 OpenAI-compatible Provider，至少设置：

```ini
LLM_PROVIDER=deepseek
LLM_API_KEY=<secret>
LLM_MODEL=<model-name>
```

不要把真实密钥提交到 Git。所有当前有效字段见[配置、安全与数据治理](11-security-and-data-governance.md)。

## 3. 启动与停止

终端 A 启动 API：

```powershell
uv run uvicorn novel_character_generator.api.app:app --reload
```

终端 B 启动持续 Worker：

```powershell
uv run python -m novel_character_generator.workers.main
```

浏览器入口：

```text
http://127.0.0.1:8000/ui      轻量角色造像工作台
http://127.0.0.1:8000/docs    FastAPI OpenAPI
```

工作台本身不需要单独构建或启动前端服务。它使用同源 API，配置 API Key 后只保存在当前页面内存中，刷新页面即清除。

仅领取并处理一次可运行 Step：

```powershell
uv run python -m novel_character_generator.workers.main --once
```

只推进指定 Run 的下一个可运行 Step：

```powershell
uv run python -m novel_character_generator.workers.main <run-uuid>
```

使用 `Ctrl+C` 先停止 API 和 Worker，再进行数据库复制、恢复或破坏性本地清理。Worker 在单步内退出后，租约到期的任务可以由后续 Worker 重新领取；不要直接编辑 Step 终态。

## 4. 最小烟雾测试

先检查进程：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health/live
Invoke-RestMethod http://127.0.0.1:8000/health/ready
Invoke-RestMethod http://127.0.0.1:8000/api/v1/capabilities
```

上传仓库自带样例并创建分析 Run：

```powershell
$novel = Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/novels `
  -Form @{ file = Get-Item data/fixtures/upload-smoke-novel.txt }

$run = Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/novels/$($novel.id)/runs" `
  -Headers @{ "Idempotency-Key" = "local-smoke-001" }

Invoke-RestMethod "http://127.0.0.1:8000/api/v1/runs/$($run.id)"
```

持续 Worker 会依次处理 `normalize_and_chunk` 和 `extract_characters`。重复创建请求时使用相同 `Idempotency-Key`，验证不会创建重复任务。完整调用方式见 [API 调用手册与错误目录](20-api-cookbook-and-error-catalog.md)。

## 5. 数据库迁移

```powershell
uv run alembic current
uv run alembic heads
uv run alembic upgrade head
```

修改 ORM 时必须新增迁移并运行迁移测试。不得用 `Base.metadata.create_all()`、手写 `init.sql` 或删除本地数据库掩盖迁移缺陷。发布前至少验证：

```powershell
uv run pytest tests/integration/test_migrations.py
```

如果仓库中实际迁移测试文件名发生变化，以 `rg --files tests | rg migration` 的结果为准，并同步更新本手册。

## 6. 验证顺序

```powershell
uv run ruff check .
uv run mypy src
uv run pytest
```

按变更范围增加专项验证：

| 修改范围 | 必跑检查 |
|---|---|
| ORM/Migration | 迁移升级、Repository 集成测试 |
| Worker/任务状态 | 恢复、租约、fencing、幂等测试 |
| API/权限 | OpenAPI、401/403、错误信封测试 |
| Agent 工具 | 权限、预算、审批与轨迹测试 |
| Provider | 超时、429、5xx、未知提交和重复回调契约测试 |
| 日志事件 | 正常/失败夹具和 `log-check` 规则；当前检查器尚未实现 |

## 7. 备份与恢复

当前需要一起保护的数据是：

- `data/app.db` 及可能存在的 SQLite WAL/SHM 辅助文件；
- `data/artifacts/`；
- 实际部署使用的非密钥配置版本；
- Alembic revision 和应用 Git commit。

一致性备份步骤：

1. 停止 API 和 Worker，确认没有写事务；
2. 将数据库文件和整个 Artifact 目录复制到同一个带时间戳的备份目录；
3. 记录当前 Git commit、`uv.lock` 哈希和 `uv run alembic current` 输出；
4. 在隔离目录恢复副本，启动前执行 `alembic upgrade head`；
5. 检查 `/health/ready`、Run/Artifact 引用和文件 SHA-256。

不要只备份数据库而遗漏 Artifact，也不要在进程仍写入时只复制一个 SQLite 主文件。生产化前必须根据部署环境冻结 RPO/RTO、保留周期、加密和异地恢复演练；当前项目尚未声明生产 SLO。

## 8. 故障排查

| 现象 | 首要检查 | 处理 |
|---|---|---|
| API 启动时报 `mock_llm_provider_forbidden_in_production` | `APP_ENV`、`LLM_PROVIDER` | 生产配置真实 Provider、Key 和 Model；不要绕过校验 |
| 生产启动时报 Key 错误 | `USER_API_KEY`、`ADMIN_API_KEY` | 两者必须存在且不同 |
| 请求返回 `401 invalid_api_key` | `X-API-Key` | 使用普通或管理员 Key；开发无 Key 模式仅在两个 Key 都未配置时生效 |
| 管理接口返回 `403 admin_api_key_required` | 当前 Key 类型 | 改用管理员 Key，不提升普通用户权限 |
| Run 一直 queued | Worker 是否运行、Step 状态 | 启动单写 Worker，查询 Run；不要手工改终态 |
| Worker 报 `database is locked` | Worker 数量、长事务 | 保证单写 Worker，停止额外实例；持续出现时检查事务边界 |
| Step claimed 后长期不动 | Worker 是否崩溃、租约是否过期 | 等待租约过期后由 Worker 重领；核对 `lease_generation`，禁止旧 Worker 回写 |
| 远程 LLM 调用失败 | Provider 配置、网络、429/5xx | 查看 Step `error_code`，按重试策略处理；不要无限重试 |
| 上传返回 413/415/422 | 文件大小、扩展名、编码 | 仅上传限制内的 TXT，检查 `MAX_UPLOAD_BYTES` |
| SSE 断开 | 最后事件序号 | 以 `after=<last-sequence>` 重连，不从头重复消费 |
| 数据库与文件不一致 | Artifact 记录、URI、SHA-256 | 停止写入并保留现场；当前 `log-check` 尚未实现，按业务记录和文件哈希人工核对 |

## 9. 发布前检查

- `git status` 中没有密钥、数据库、产物或临时知识图谱中间文件；
- `uv.lock` 与代码依赖一致；
- Alembic 只有一个预期 head；
- 全量测试、Lint、类型检查通过；
- `/capabilities` 与[当前实现状态](00-current-status.md)一致；
- 新接口已更新 API 规范、调用手册和追踪矩阵；
- 新关键状态转换已增加结构化日志设计与测试；
- 数据库和 Artifact 备份能够在隔离目录恢复。

---

[← 上一篇](15-risks-decisions-and-references.md) · [文档索引](README.md) · [下一篇 →](17-appearance-aggregation-contract.md)
