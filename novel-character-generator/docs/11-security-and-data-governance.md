# 配置、安全与数据治理

> [← 上一篇](10-provider-and-workflow-versioning.md) · [文档索引](README.md) · [下一篇 →](12-evaluation-and-acceptance.md)
>
> 文档版本：3.1 · 源章节：14. 配置、安全与数据治理 · 修订日期：2026-08-24
>
> 本页先列当前源码真正接受的配置，再单独列目标配置。运行时字段以 [`settings.py`](../src/novel_character_generator/settings.py) 和 [`.env.example`](../.env.example) 为准。

## 14. 配置、安全与数据治理

### 14.1 当前可用配置

```ini
APP_ENV=development
LOG_LEVEL=INFO
LOG_FORMAT=json

OTEL_ENABLED=true
OTEL_SERVICE_NAME=novel-character-generator-api
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
METRICS_ENABLED=true
METRICS_PATH=/metrics

DATABASE_URL=sqlite+aiosqlite:///./data/app.db
ARTIFACT_STORE=local
ARTIFACT_LOCAL_ROOT=./data/artifacts
MAX_UPLOAD_BYTES=20000000

LLM_PROVIDER=mock
LLM_API_KEY=
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=
LLM_TIMEOUT_SECONDS=180

MAX_CHUNK_INPUT_TOKENS=5000
CHUNK_OVERLAP_TOKENS=300
MAX_TASK_ATTEMPTS=3
WORKER_LEASE_SECONDS=240

AGENT_RUNTIME_ENABLED=false
AGENT_MAX_TURNS_DEFAULT=3
AGENT_MAX_TOOL_CALLS_DEFAULT=12
AGENT_MAX_REFLECTION_ROUNDS=1
AGENT_MAX_COST_DEFAULT=1.0
AGENT_DEADLINE_SECONDS_DEFAULT=180
AGENT_TOOL_WRITE_POLICY=approval_required

AUTH_MODE=api_key
USER_API_KEY=
ADMIN_API_KEY=
```

开发环境未配置两个 API Key 时允许以 `development` 身份调用；生产环境必须配置不同的普通和管理员 Key。`LLM_PROVIDER=mock` 只用于本地开发和测试，生产启动会拒绝；启用 `deepseek` 或 `openai_compatible` 时必须同时提供 `LLM_API_KEY` 和 `LLM_MODEL`。

当前 `OTEL_*` 字段只是配置入口，完整 API→Worker→Provider instrumentation 尚未实现；`AGENT_RUNTIME_ENABLED` 默认关闭。敏感值只通过环境变量或 secret manager 注入，不写入日志、数据库快照或 `.env.example`。缺少生产必需配置时启动失败，不以匿名管理权限或无限预算降级。

### 14.2 目标配置：实现对应能力后再加入

以下名称表达目标设计，当前 `Settings` 尚不接受或使用，不能放入当前部署模板冒充可用功能：

```ini
# 完整 OpenTelemetry instrumentation 实现后
OTEL_TRACES_SAMPLER=parentbased_traceidratio
OTEL_TRACES_SAMPLER_ARG=0.10

# 图像 Provider 和 WorkflowProfile 实现后
IMAGE_PROVIDER=fal
FAL_KEY=
IMAGE_WORKFLOW_PROFILE=sdxl_instantid_v1
MAX_CONCURRENT_IMAGE_CALLS=1

# 局部 LangGraph PoC 通过后
LANGGRAPH_AGENT_RUNTIME_ENABLED=false

# LLM 并发调度器实现后
MAX_CONCURRENT_LLM_CALLS=3

# 检索增强视觉精提取实现后；PoC 先接远程 Embedding API
RETRIEVAL_LEXICAL_PROVIDER=sqlite_fts5
RETRIEVAL_LEXICAL_PROFILE_VERSION=zh-jieba-visual-v1
RETRIEVAL_VECTOR_STORE=qdrant_local
QDRANT_LOCAL_PATH=./data/qdrant
EMBEDDING_PROVIDER=openai_compatible
EMBEDDING_BASE_URL=
EMBEDDING_API_KEY=
EMBEDDING_MODEL=
EMBEDDING_DIMENSION=
EMBEDDING_PROFILE_VERSION=
EMBEDDING_BATCH_SIZE=16
EMBEDDING_TIMEOUT_SECONDS=60
```

新增配置字段时必须同时修改 `Settings`、`.env.example`、配置测试和本页；未接入代码的候选配置只能留在“目标配置”段落。

### 14.3 文件与路径安全

- 上传限制大小和文件类型；文件名不参与真实存储路径；
- 产物使用 UUID/哈希路径，防止目录穿越；
- 下载远程文件时限制协议、域名、大小、超时和 MIME；
- 校验图像解码，拒绝解压炸弹；
- 本地存储接口与 S3 兼容对象存储接口保持一致。

### 14.4 数据治理

小说正文可能受版权保护，且可能包含个人或敏感信息。产品必须明确：

- 用户确认拥有处理权限；
- 哪些内容会发送到哪个云端 Provider；
- 远程 Embedding API 同样会接收小说 passage，不能因为其输出只是向量就把它视为纯本地处理；
- Provider 的数据保留和训练使用政策；
- 本地与云端产物保留周期；
- 删除小说时如何级联删除或匿名化观察、调用日志和产物；
- 日志只保存必要摘要，不记录完整正文和密钥。
- 删除小说时须同时删除 FTS 派生索引、Qdrant point/collection 中属于该源版本的向量，以及失败批次缓存；备份中的延迟删除策略必须明确。
- Agent 轨迹不保存隐藏思维链，只保存输入上下文清单、可见输出、工具调用、决策依据和使用量。

### 14.5 认证与权限

一期至少使用 API Key 区分普通调用与管理操作。二期增加用户、项目、RBAC、审计事件和配额。Prompt、原型、Provider、删除和批量生成均属于管理权限。

Agent 工具权限按 `read/propose/execute/admin` 分级。模型永远不能通过 Prompt 自行获得更高权限；运行时只绑定 AgentSpec 白名单和当前用户权限的交集。外部 MCP/A2A 返回内容视为不可信数据，不能把其中的指令提升为系统指令。

---

[← 上一篇](10-provider-and-workflow-versioning.md) · [文档索引](README.md) · [下一篇 →](12-evaluation-and-acceptance.md)
