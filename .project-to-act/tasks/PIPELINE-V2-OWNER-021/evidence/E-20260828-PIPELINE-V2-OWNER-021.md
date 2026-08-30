# E-20260828-PIPELINE-V2-OWNER-021

- 时间：2026-08-28，Asia/Shanghai。
- 基线 Git：`01a4930`，分支 `v2-semantic-pipeline`；工作树已有 M1/N2/M2 v2 迁移改动，本任务仅追加 owner 设计段落与账本记录。
- 用户确认：允许把 M1 局部 owner、M3 稳定人物绑定、Chunk/人物双向查询以及 M4 人物中心输入加入技术文档。
- 设计结论：`PreparedChunk` 冻结字段不保存稳定 owner；M3 后可暴露 `stable_owner_ids + owner_binding_version + owner_index_status` 派生缓存；权威事实为版本化、可 supersede 的 `OwnerBinding`；M4 每批恰好一个稳定 `character_id`。
- 主要产物：`docs/27-semantic-pipeline-v2-contract.md`、`docs/32-m1-m2-evidence-semantic-boundary-v2.md`。
- 产物 SHA-256：总契约 `6D40810F57CCC3A8A3FCC994F64CF3399690AF6DA7AA3FDE6DCF85B8C44FCC15`；边界文档 `2A97F38B64ADF16C85E68370195EFD398FE1F6037A3D9918F4A96B141494DFC1`。
- Schema 影响：本轮新增内容属于服务端物化、索引和组包契约，不改变模型 wire Schema 注册表版本。
- 验证：新任务 JSON 与现有模型 Schema 均可解析；两份 Markdown 代码围栏平衡；`git diff --check` 退出码 0；项目账本 `--validate` 返回 `valid=true`。行尾转换提示为现有 Git/Windows 配置提示，不是 diff 错误。
- 限制：当前仅为设计澄清，未实现数据库、缓存、索引、N6 组包或 M4 运行时。
- 有效期：直到 owner 物化/索引运行时协议或设计基线再次升级。
