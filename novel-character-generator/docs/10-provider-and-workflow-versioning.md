# Provider 与工作流版本

> [← 上一篇](09-api-specification.md) · [文档索引](README.md) · [下一篇 →](11-security-and-data-governance.md)
>
> 文档版本：2.8 · 源章节：13. Provider 与工作流版本管理 · 修订日期：2026-08-22

## 13. Provider 与工作流版本管理

### 13.1 LLM Provider 接口

```python
class LLMProvider(Protocol):
    async def generate_structured(
        self,
        *,
        messages: Sequence[Message],
        output_schema: type[BaseModel],
        request_options: LLMRequestOptions,
    ) -> StructuredLLMResult: ...

    async def count_tokens(self, messages: Sequence[Message]) -> int: ...
    async def get_capabilities(self) -> LLMCapabilities: ...
    async def get_pricing(self) -> PricingSnapshot | None: ...

    async def generate_tool_turn(
        self,
        *,
        messages: Sequence[Message],
        tools: Sequence[BoundTool],
        request_options: LLMRequestOptions,
    ) -> LLMToolTurnResult: ...
```

返回值必须包含 usage、model revision、request ID、finish reason、工具调用关联信息和原始响应哈希。业务层不直接接触厂商 SDK 对象。Provider 只适配一次模型响应及工具调用格式；多轮循环、工具执行、权限、预算、审批、停止和轨迹记录统一由项目 `AgentRuntime` 负责，避免 Provider 与 Runtime 双重编排。

### 13.2 图像 Provider 接口

```python
class ImageGenerator(Protocol):
    async def submit(self, request: ImageGenerationRequest) -> ExternalJob: ...
    async def get_status(self, external_job_id: str) -> ExternalJobStatus: ...
    async def cancel(self, external_job_id: str) -> bool: ...
    async def fetch_result(self, external_job_id: str) -> ImageGenerationResult: ...
    async def estimate_cost(self, request: ImageGenerationRequest) -> CostEstimate | None: ...
    async def get_capabilities(self) -> ImageProviderCapabilities: ...
    async def reconcile(self, operation: ExternalOperation) -> ReconciliationResult: ...
```

提交与查询分开，才能在 Worker 重启后恢复远程任务。`ImageProviderCapabilities` 至少声明幂等键、取消、Webhook、按 request fingerprint 查询、状态保留期和费用返回能力；不支持的能力不能由适配器伪造。PoC 同时测量冷启动、模型/节点下载、首图与热启动 P95、回调重复/乱序和远程状态过期。无法自动识别的 `submission_unknown` 必须进入人工对账，而不是盲目重提。

### 13.3 Prompt 与 Agent 规格管理

一期：

- Prompt 存放在 `prompts/v1/`；
- `registry.yaml` 保存名称、版本、输入变量和内容哈希；
- 启动时校验占位符与 Schema；
- 每次调用保存实际 Prompt 版本和内容哈希。
- AgentSpec 存放在 `agent_specs/v1/`，工具白名单引用 ToolSpec 版本；
- AgentSpec 必须通过静态校验：输出 Schema 存在、工具权限闭合、预算和轮次上限有效。

二期：

- 文件作为种子，数据库保存草稿/已发布版本；
- 发布操作是事务性的，不只依赖 `is_active` 布尔值；
- 支持草稿、审核、发布、回滚和灰度；
- 缓存使用版本号失效，支持多进程同步；
- `max(version)+1` 由数据库锁或序列保障；
- 管理操作写入审计日志。
- Agent、Prompt 和工具权限作为一个可发布配置包灰度和回滚，避免只回滚 Prompt 却保留不兼容工具集合。

### 13.4 Prompt 缓存与高级调用能力

静态系统指令、输出 Schema 和稳定工具定义适合作为可缓存前缀。`model_calls` 记录 `cache_read_tokens`、`cache_write_tokens`、缓存键和 TTL 快照，用实际命中率判断收益。

`LLMCapabilities.agent` 使用以下结构，并随 Provider/模型 revision 保存能力快照：

```python
class AgentCapabilities(BaseModel):
    direct_tool_calling: bool
    parallel_tool_calling: bool
    programmatic_tool_calling: bool
    tool_search: bool
    prompt_caching: bool
    explicit_prompt_caching: bool
    persisted_reasoning: bool
    multimodal_input: bool
    remote_mcp: bool
```

一期只要求 Direct Tool Calling 或单次 Structured Output。Programmatic Tool Calling 只允许调用只读、低风险、返回结构稳定的工具，用于过滤、连接、排序、去重和聚合；需要人工批准、保留原始引用或每个结果都会改变下一步判断时，继续使用普通工具调用。不得把特定 Provider 的 beta 能力写成业务正确性的前提。

---

[← 上一篇](09-api-specification.md) · [文档索引](README.md) · [下一篇 →](11-security-and-data-governance.md)
