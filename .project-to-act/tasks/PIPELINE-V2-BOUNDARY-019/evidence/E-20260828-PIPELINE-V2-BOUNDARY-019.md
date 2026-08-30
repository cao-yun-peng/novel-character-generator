# E-20260828-PIPELINE-V2-BOUNDARY-019

- 时间：2026-08-28，Asia/Shanghai。
- 基线 Git：`01a4930`，分支 `v2-semantic-pipeline`。
- 用户确认：M1 只寻找人物视觉相关原文；face/body 等分类、语义原子化、认知状态和显式信号转交 M2。
- 设计版本：`semantic-pipeline-v2-design-v1.3`。
- 机器 Schema：`semantic-pipeline-v2-model-schemas-v1.4`。
- 主要产物：`docs/27-semantic-pipeline-v2-contract.md`、`docs/32-m1-m2-evidence-semantic-boundary-v2.md`、`docs/contracts/semantic-pipeline-v2-model-schemas.json`。
- 产物 SHA-256：总契约 `07F395A1674BD4463AB21207B3F1BC82397F34E819FBCDC0626B5532D3EC719D`；边界文档 `41C437F5239D7F60C2D191457AD23F1F7105FBD9D3D245CF7ABAF72DCD7754C5`；Schema `AE3CD60A82D19F915961F5782F386580B84C5E68138020B45F2E8AF4AB55A34D`。
- 历史兼容：M1/N2/M2 v1 文档、Prompt、数据集和 5/6 结果保留，但不作为 v2 Gate。
- 验证：JSON 解析与 target/legacy 定义结构断言通过；10 份技术 Markdown 的本地相对链接检查通过；`git diff --check` 通过；项目账本 `--validate` 返回 valid；现有测试 59/59 通过；旧状态关键字一致性检索无命中。
- 限制：环境未安装 `jsonschema` 包，因此没有执行 Draft 2020-12 meta-schema 库校验；本轮完成了 JSON 语法、关键 required/enum/definition 结构断言，后续实现任务仍需用运行时 Pydantic Schema 做双向一致性测试。
- 有效期：直到 M1/N2/M2 v2 运行时协议或本设计基线再次升级。
