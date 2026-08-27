# Novel Character Generator

从中文小说中提取带原文证据的角色视觉事实，整理角色在不同时间线和阶段的外观状态，并为后续可追溯的角色图像生成提供稳定输入。

当前版本已经跑通 TXT 上传、源文档版本、分块、角色与视觉事实提取、任务恢复、人物合并/拆分、时间绑定修正、档案编辑审批和目标时点快照，并实现上传后的细粒度 passage、SQLite FTS5/BM25、远程 Embedding、Qdrant Local、RRF、邻居扩展，以及面向角色的 QueryPlan、检索审计、视觉精提取和 Observation/Suggestion 分流。图像侧已提供默认关闭的 `GenerationContextBuilder + Mock Image Provider`，可验证 context hash、候选图落库与 Worker 恢复；真实收费 Provider、视觉防漂移、完整结构化业务日志和 `log-check` 仍待实现。

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

浏览器打开 `http://127.0.0.1:8000/ui` 进入“角色造像台”。页面可以上传 TXT、创建分析 Run、查看 Worker 进度和角色证据；角色详情页还会显示当前检索索引状态，按人生阶段自动规划视觉字段缺口，并可创建精提取任务、查看证据和审核 Suggestion。2D 图像区域根据 `/api/v1/capabilities` 自动启用；默认 `IMAGE_PROVIDER=disabled`，开发验证时可改为 `mock`，Mock 产物只证明链路正确，不代表角色画面质量。

默认开发配置使用 Mock LLM；普通和管理员 API Key 均为空时，本地请求无需认证。生产环境禁止该降级方式。完整上传和分析示例见 [API 调用手册](docs/20-api-cookbook-and-error-catalog.md)。

### 上传一本小说并查看角色

1. 首次运行先执行 `Copy-Item .env.example .env` 和 `uv run alembic upgrade head`。当前默认按每块 5,000 个估算 Token、相邻块重叠 300 Token 处理文本。
2. 在终端 A 启动 API，看到 Uvicorn 监听 `127.0.0.1:8000` 后保持终端运行。
3. 在终端 B 启动 Worker，保持该终端运行；API 只创建任务，实际分块、提取和聚合由 Worker 完成。
4. 打开 `http://127.0.0.1:8000/ui`。如果 `.env` 配置了 `USER_API_KEY`，先在左侧输入相同 Key 并连接。
   页面刷新后，可在“历史项目”中重新打开数据库里已有的小说和最近一次任务；失败或取消的任务也会显示已经持久化的部分角色。旧项目若没有细粒度索引，可在项目摘要中点击“构建精细索引”，该任务复用原始文本，不会重跑或覆盖角色抽取。
5. 在“上传小说”区域选择大小限制内的 `.txt` 文件，点击“上传小说”。页面显示“上传完成”后点击“开始分析角色”。
6. 等待任务依次完成 `normalize_and_chunk → extract_characters → aggregate_appearance`。页面显示“任务成功”后会自动加载角色列表。
   `extract_characters` 运行期间页面会显示“已完成块数/总块数”，并逐步加载已经落库的部分角色与证据；停止 Worker 不会删除这些结果，重启后仍可从游标继续。
7. 点击角色卡片查看外观事实、原文证据、置信度和阶段状态；索引就绪后，可在“视觉精提取”面板选择阶段和仍缺失的字段组，创建任务并查看新增事实、证据与待审核建议。在“人工审核中心”填写审核人 ID 后，可处理 Suggestion、审批队列、冲突值和 Render Profile。只有 approved/locked Profile 且无开放冲突时，Mock Image Run 才可创建。

默认 Mock Provider 只适合验证流程，只识别有限的测试句式。分析任意真实小说前，应在 `.env` 配置 `LLM_PROVIDER=deepseek` 或 `openai_compatible`，并填写对应 `LLM_API_KEY`、`LLM_MODEL`、必要时的 `LLM_BASE_URL`，以及远程响应较慢时的 `LLM_TIMEOUT_SECONDS`，然后重启 API 与 Worker。

调试模型字段时，可在**开发环境**设置 `LLM_RAW_RESPONSE_CAPTURE_ENABLED=true`，执行 `uv run alembic upgrade head` 后重启 API 和 Worker。使用 `ADMIN_API_KEY` 连接工作台，在 Run Inspector 的 R1 Chunk、R2 Chunk 或 R2 收敛详情中打开“模型原始响应（开发）”页签，即可查看模型消息正文和 Provider 完整响应；R3 当前是代码策略阶段，没有模型响应。它在每次请求完成并通过结构校验后更新，不是逐 token 流；旧 Run 不会补录，生产环境会拒绝启用。

## 常用检查

```powershell
uv run pytest
uv run ruff check .
uv run mypy src
```

数据库 Schema 只通过 Alembic 迁移管理，不使用运行时 `create_all()` 代替迁移。API 和 Worker 是两个独立进程；一期 SQLite 模式只运行一个写 Worker。
