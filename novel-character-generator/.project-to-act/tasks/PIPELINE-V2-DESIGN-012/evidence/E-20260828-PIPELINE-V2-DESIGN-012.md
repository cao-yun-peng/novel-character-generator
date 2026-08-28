# E-20260828-PIPELINE-V2-DESIGN-012

- 时间：2026-08-28T10:54:46+08:00
- 任务：PIPELINE-V2-DESIGN-012
- Git revision：`faa06d03696c76bbee6451b5c75c27b95ca4fc9a`；工作树已有用户/既有任务未提交改动，本任务只修改 TASK 允许路径。
- 设计版本：`semantic-pipeline-v2-design-v1`
- Provider 调用：0
- 生产代码、数据库、默认 Prompt/Worker 修改：0

## 验证

| 检查 | 退出状态 | 结果 |
|---|---:|---|
| 四份任务/Schema JSON 使用 PowerShell `ConvertFrom-Json` 解析 | 0 | 全部有效 |
| Draft 2020-12 meta-schema `jsonschema.Draft202012Validator.check_schema` | 0 | `json_schema_meta_valid=true` |
| 系统提示词计数 | 0 | M1-M5 共 5 份 |
| 主契约 Markdown code fence | 0 | 8 个，成对 |
| 主契约相对链接检查 | 0 | 6 个链接，0 缺失 |
| 旧“条件模型/规则主语义”措辞扫描 | 0 | 仅任务不变量保留“不得冒充主解析器”，无旧设计残留 |
| `git diff --check`（本任务修改的既有 tracked 文件） | 0 | 无 whitespace error；仅 Windows LF/CRLF 提示 |
| Project-to-Act `--validate` | 0 | managed schema v1，issues 为空 |
| Agent lifecycle `validate` | 0 | revision 2、stage 5、active，有效 |

## 工件哈希

| 工件 | SHA256 |
|---|---|
| `docs/27-semantic-pipeline-v2-contract.md` | `671F5A54856FDDFA283878420DE3E9BB814F57116E3931925C71E07508E64FA0` |
| `docs/contracts/semantic-pipeline-v2-model-schemas.json` | `3DECBA73CADE1795D9AA7EBCEB5742C0C1A36DEB2BAC9DB8661F936C024453AB` |
| M1 system prompt | `A349CDBF3C30C0400F08C3BEEDC91DC7387EE400D8CB2A55028EAF49CD44E8A7` |
| M2 system prompt | `373CB17DE313F576955D4B4261032FB17079E59DDFAA2C35CB3F1AB28104DA36` |
| M3 system prompt | `2D444F9C6F94565B0699C9659D2A029152BA0037C4FE4CA559C0DD645FA73544` |
| M4 system prompt | `494E70F6EF375EBC12C18C1F256F6E0C2C5C4F01B2A98F2C193D247AE66DC829` |
| M5 system prompt | `755D9D3675FB804C84A144E8E02BA6056B92C35898496FFBAD25A771C65E1C9A` |

## 结果与限制

- 节点、Prompt、Schema、状态、指标、质量 Gate、成本护栏和迁移回滚设计已形成，可进入用户评审。
- 本证据只证明设计工件结构与治理一致性，不证明 V2 已实现、模型质量提升、成本可接受或阶段 5 通过。
- 未运行 Pytest/Ruff/Mypy，因为本任务未修改生产代码；后续 P0/P1 实现必须建立独立测试与证据。
- 有效期：V2 节点职责、Prompt、Schema、Gate 或实现路线变化前。
