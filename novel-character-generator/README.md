# Novel Character Generator

从中文小说中提取带原文证据的角色视觉事实，整理角色在不同时间线和阶段的外观状态，并为后续可追溯的角色图像生成提供稳定输入。

当前版本已经跑通 TXT 上传、源文档版本、分块、角色与视觉事实提取、任务恢复、人物合并/拆分、时间绑定修正、档案编辑审批和目标时点快照。图像生成、视觉防漂移、完整结构化业务日志和 `log-check` 仍在设计或待实现阶段。

## 从这里开始

- 想先知道产品做什么：读[开始这里](docs/00-start-here.md)。
- 想知道哪些能力真正可用：读[当前实现状态](docs/00-current-status.md)，或启动后查询 `GET /api/v1/capabilities`。
- 想找到功能对应代码：读[代码导航](docs/00-code-navigation.md)。
- 想在本地跑起来：读[本地开发与运维手册](docs/16-local-development-and-runbook.md)。
- 想查看全部设计：读[技术文档索引](docs/README.md)。

## 最短启动路径

要求 Python 3.12 和 `uv`。在本目录执行：

```powershell
uv sync --dev
Copy-Item .env.example .env
uv run alembic upgrade head
uv run uvicorn novel_character_generator.api.app:app --reload
```

另开一个终端启动 Worker：

```powershell
uv run python -m novel_character_generator.workers.main
```

浏览器打开 `http://127.0.0.1:8000/ui` 进入“角色造像台”。页面可以上传 TXT、创建分析 Run、查看 Worker 进度和角色证据；2D 图像区域根据 `/api/v1/capabilities` 自动启用，当前图像后端未实现时会保持禁用并明确提示。

默认开发配置使用 Mock LLM；普通和管理员 API Key 均为空时，本地请求无需认证。生产环境禁止该降级方式。完整上传和分析示例见 [API 调用手册](docs/20-api-cookbook-and-error-catalog.md)。

## 常用检查

```powershell
uv run pytest
uv run ruff check .
uv run mypy src
```

数据库 Schema 只通过 Alembic 迁移管理，不使用运行时 `create_all()` 代替迁移。API 和 Worker 是两个独立进程；一期 SQLite 模式只运行一个写 Worker。
