# Image Provider 插件契约

## 目标

生图编排只依赖 `ImageProvider`，不依赖供应商请求体。阿里云、其他云模型和本地模型都消费同一份 `ImageRenderSpec`，复用提交恢复、轮询、Artifact 持久化、审批、漂移审计与评测链。Provider 在提交前调用独立的 `ImagePromptRenderer`，因此更换自然语言模板不需要修改领域规格或 Worker 状态机。

## PromptRenderer

- `renderer` 与 `version` 是稳定标识，必须随生成图片进入评测元数据；切换版本后不能静默复用旧 baseline。
- `render(ImageRenderSpec)` 返回正向 Prompt、负向 Prompt 和逐短句 provenance；每个语义短句必须绑定原始 `field_path` 与 `source_refs`。
- Renderer 只能翻译字段表达、组织顺序和增加不含人物事实的工作流指令，不能补写脸型、性格、服装、道具或剧情事实。
- Registry 对未知、重复和身份不一致的 Renderer 失败关闭。当前内置版本为 `canonical-zh:canonical-zh-character-v1`。
- Golden fixture 固定字段路径到最终自然语言及 provenance 顺序，防止重构时重新泄漏 `hair.color: black` 一类内部路径。

## 必须实现

- `provider`：稳定、唯一、全小写的适配器 ID，例如 `dashscope`。
- `version`：不可含糊的模型或适配器版本；每张结果都会持久化该值，baseline 按版本隔离。
- `submit(ImageSubmitRequest)`：只读取 Provider 中立 `render_spec`；异步 Provider 返回 `submitted + provider_request_id`，同步 Provider 返回 `succeeded + artifact_refs`，两者都会持久化后再进入下一步。确定拒绝抛出 `ImageProviderSubmissionRejected`，传输结果不确定则原样抛出，使主链进入 `submission_unknown`。
- `query(provider_request_id)`：映射为 submitted/running/succeeded/failed，不把等待伪装成错误。
- `download(artifact_ref)`：验证协议与可信结果域，禁止把 API Key 转发给结果存储域。
- `capabilities()`：如实声明幂等、取消、指纹查询和成本报告能力。
- `close()`：释放连接；无资源的 Provider 提供 no-op 实现。

## 注册

适配器通过 `ImageProviderRegistry.register(name, factory)` 注册。Worker 只调用 `create_image_provider(settings)`，新增供应商不得修改生图状态机。

注册表失败关闭：未知名称、重复名称、`disabled` 名称或工厂返回的 `provider` 身份不一致都会拒绝启动，不回退到 Mock。

## 实验记录

市场模型对比至少固定并记录：Provider ID、模型/版本、ImageRenderSpec hash、workflow 版本、seed、输出尺寸、候选序号、延迟、成功/失败、成本和人工评分。不同模型版本不得合并为同一 baseline。

单次效果图只属于 smoke；进入批量前仍需通过可信审批、漂移审计和质量 Gate。

2026-08-28 已用北京共享原生地址完成一张 `qwen-image-plus` 真实候选图。共享地址允许 `https://dashscope.aliyuncs.com/api/v1`，业务空间专属地址允许 `https://<WorkspaceId>.<region>.maas.aliyuncs.com/api/v1`；适配器会规范化 `/api/v1`，避免重复拼接。该结果只是待人工审批的 `Baseline Candidate v1`，不表示 baseline 已锁定。

## OpenAI-compatible 同步生图

- 通用适配器 `OpenAICompatibleImageProvider` 实现官方 `POST /v1/images/generations` 形状；`timicc` 只是注册表中的一个受限配置实例，后续同协议市场模型可复用适配器而不改 Worker。
- `gpt-image-2` 固定返回 base64。适配器在 `submit` 返回前先将 PNG 原子写入可恢复暂存区，再把 `staged-image://<provider>/<sha256>.png` 写入 ExternalOperation；不把大段 base64 存进数据库。
- Base URL 只允许 HTTPS、显式 host allowlist 和空路径或 `/v1`；请求密钥只发往 API host，本地暂存下载不携带 Authorization。
- GPT Image Prompt 由同一版本化 Renderer 生成；负向约束以自然语言合入单一 `prompt`。请求记录 `provider/model/renderer/spec_hash/size/quality`；官方接口没有 seed 参数，因此实验记录明确标记 seed 不受 Provider 支持。
- TIMI CC 公开文档给出的客户端 Base URL 是 `https://timicc.com`，适配器负责拼接 `/v1/images/generations`。公开页面不列各密钥分组模型清单，`gpt-image-2` 是否开放必须用所属分组实调确认。
