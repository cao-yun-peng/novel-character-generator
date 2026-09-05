# dev28 缓存续跑兼容说明

2026-09-05，任务 CACHE-CONTINUATION-078。运行时 0.1.0.dev28；模型和领域 Schema 保持 3.27.0-draft1。本切片继续 R05，不代表 R05 全部完成。

## 已实现

M1、M2 attribution、promotion、M3 identity、cluster rescue、appearance transition 六条模型执行路径均绑定完整请求指纹：Provider 的 cache_identity、system instruction、user payload、response schema 和 schema name。DeepSeek 的 cache_identity 包含实际模型与生成配置；凭据不参与普通日志或指纹元数据展示。自定义 Provider 未提供稳定 cache_identity 时可首次执行，但不能静默恢复缓存。

本版本新增后四条路径的预检。promotion、identity 和 transition 在批次新增调用前检查已规划任务的缓存；rescue 在每轮开始时检查该轮动态生成的任务。后续轮依赖前轮结果，尚不提供全运行的离线调用计划，不能宣称所有未来轮次已预检。

所有路径恢复时均重新解析保存的模型输出并执行当前 Grounding；promotion 同时重建 grounded_result 和 grounding_issues，旧派生数据不作为结果依据。无人物的 transition Chunk 不调用模型，也不要求模型请求指纹。

## 使用与兼容

- **resume**：相同来源、代码信封和完整请求指纹才能复用。缺失或不一致时抛出 ContractValidationError，不自动调用新模型补齐该缓存。
- **regenerate**：更换模型、Prompt、响应 Schema 或生成配置时使用独立输出目录。它会产生新模型调用，不能称为离线重放。
- **offline replay**：既有 M2 `replay-m2-grounding` 和 promotion 重放工具保持原用途。M3/rescue/transition 的统一旧缓存迁移入口尚未交付，不能把它们的普通 resume 当作迁移工具。

历史 run 不在本切片中重写。旧无指纹记录仍可查看，但普通 resume 会拒绝；不要手工补上当前指纹来伪造旧请求一致性。代码侧任务 JSON 添加 request_fingerprint，原模型输入/输出和领域产物结构未变，所以本切片仅提升 runtime 版本。

## 验收与剩余工作

211 项测试、19 项子测试通过，真实 Provider 调用 0。回归覆盖四阶段恢复、损坏 Grounding 重建、缺失/变化指纹拒绝，以及前面任务文件缺失、后面缓存不兼容时在调用前拒绝。测试使用明确 cache_identity 的可控 Provider。

R05 仍需统一离线迁移、完整调用计划、尝试历史及失败结果未知时的审计；R03/R04 有效期与 Snapshot、R02 真冲突及 R06 人工质量 Gate 继续按清单实施。
