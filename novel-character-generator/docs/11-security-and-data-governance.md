# 配置、安全与数据治理

> [← 上一篇](10-provider-and-workflow-versioning.md) · [文档索引](README.md) · [下一篇 →](12-evaluation-and-acceptance.md)
>
> 文档版本：2.8 · 源章节：14. 配置、安全与数据治理 · 修订日期：2026-08-22

## 14. 配置、安全与数据治理

### 14.1 配置示例

```ini
APP_ENV=development
LOG_LEVEL=INFO
LOG_FORMAT=json

OTEL_ENABLED=true
OTEL_SERVICE_NAME=novel-character-generator-api
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
OTEL_TRACES_SAMPLER=parentbased_traceidratio
OTEL_TRACES_SAMPLER_ARG=0.10
METRICS_ENABLED=true
METRICS_PATH=/metrics

DATABASE_URL=sqlite+aiosqlite:///./data/app.db
ARTIFACT_STORE=local
ARTIFACT_LOCAL_ROOT=./data/artifacts

LLM_PROVIDER=deepseek
LLM_API_KEY=
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=

IMAGE_PROVIDER=fal
FAL_KEY=
IMAGE_WORKFLOW_PROFILE=sdxl_instantid_v1

MAX_CHUNK_INPUT_TOKENS=10000
MAX_CONCURRENT_LLM_CALLS=3
MAX_TASK_ATTEMPTS=3
WORKER_LEASE_SECONDS=120

AGENT_RUNTIME_ENABLED=true
LANGGRAPH_AGENT_RUNTIME_ENABLED=false
AGENT_MAX_TURNS_DEFAULT=3
AGENT_MAX_TOOL_CALLS_DEFAULT=12
AGENT_MAX_REFLECTION_ROUNDS=1
AGENT_MAX_COST_DEFAULT=
AGENT_TOOL_WRITE_POLICY=approval_required

AUTH_MODE=api_key
USER_API_KEY=
ADMIN_API_KEY=
```

敏感值只通过环境变量或 secret manager 注入，不写入日志、数据库快照或 `.env.example`。生产启动时校验：普通与管理 API Key 均已配置且不同；启用的 LLM/Image Provider 已提供密钥；Agent 已配置正数费用上限；`LANGGRAPH_AGENT_RUNTIME_ENABLED` 默认保持关闭。缺少必需配置时启动失败，不以无限预算或匿名管理权限降级。

### 14.2 文件与路径安全

- 上传限制大小和文件类型；文件名不参与真实存储路径；
- 产物使用 UUID/哈希路径，防止目录穿越；
- 下载远程文件时限制协议、域名、大小、超时和 MIME；
- 校验图像解码，拒绝解压炸弹；
- 本地存储接口与 S3 兼容对象存储接口保持一致。

### 14.3 数据治理

小说正文可能受版权保护，且可能包含个人或敏感信息。产品必须明确：

- 用户确认拥有处理权限；
- 哪些内容会发送到哪个云端 Provider；
- Provider 的数据保留和训练使用政策；
- 本地与云端产物保留周期；
- 删除小说时如何级联删除或匿名化观察、调用日志和产物；
- 日志只保存必要摘要，不记录完整正文和密钥。
- Agent 轨迹不保存隐藏思维链，只保存输入上下文清单、可见输出、工具调用、决策依据和使用量。

### 14.4 认证与权限

一期至少使用 API Key 区分普通调用与管理操作。二期增加用户、项目、RBAC、审计事件和配额。Prompt、原型、Provider、删除和批量生成均属于管理权限。

Agent 工具权限按 `read/propose/execute/admin` 分级。模型永远不能通过 Prompt 自行获得更高权限；运行时只绑定 AgentSpec 白名单和当前用户权限的交集。外部 MCP/A2A 返回内容视为不可信数据，不能把其中的指令提升为系统指令。

---

[← 上一篇](10-provider-and-workflow-versioning.md) · [文档索引](README.md) · [下一篇 →](12-evaluation-and-acceptance.md)
