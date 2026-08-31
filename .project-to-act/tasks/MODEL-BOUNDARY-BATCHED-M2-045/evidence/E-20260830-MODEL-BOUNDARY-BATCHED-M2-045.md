# E-20260830-MODEL-BOUNDARY-BATCHED-M2-045

- 时间：2026-08-30，Asia/Shanghai。
- 用户决定：M2 改为 E 个任务，每个 exact 携带 D 个 describe；所有模型阶段统一精简输入输出。
- Schema：`3.3.0-draft1`。
- Provider 调用：0。
- 运行时修改：0。
- Schema 静态验证：Draft 2020-12 通过，版本 `3.3.0-draft1`，共 23 个定义。
- 模型边界验证：M1 输入只接受 `chunk_text`，M1 输出不接受 `chunk_id`；M2 输入不接受来源版本、Chunk ID、hash 或 cache key，M2 输出不接受 `target_character_ref` 等系统字段。
- 批量行为验证：E=2、D=2 时只生成 2 个任务且每个任务包含 2 个 describe；消费后剩余 D=1 时仍生成 2 个逐 exact 批量任务。
- 输出验证：任务内 describe/fragment ref 集合必须与输入一致；claimed/support quote 与 fragment-local span 切片一致；代码回填后的 grounded M2 结果通过 Schema。
- 项目台账：`valid: true`，无 issue。
- Git 检查：工作区和 staged `diff --check` 通过；仅有现有 LF/CRLF 提示，无空白错误。
- 产物 SHA-256：
  - `docs/33-simplified-character-evidence-pipeline-v3.md`：`cf849e2d7e4d7a1891247287f1ffd41559281e51e40cac8d38174860433840c1`
  - `docs/contracts/simplified-character-evidence-v3-model-schemas.json`：`7507eb8bad1246edb2390a71bbd64ec12cd5dad1b763ffc218ccb07c2af8aa88`
  - `README.md`：`ddeb0021faa9364fca8c6a387df87af1516ed9771e41979868ed38c86518be7a`
  - `docs/README.md`：`74b6f00a61de321759463cb4337f5e3dbc3415f714902d7ebf3cd7fd1be16d98`
- 验证结论：静态契约完成；Provider、提示词文件、运行时代码和真实模型质量尚未实现。
- 有效期：直到模型输入输出边界、M2 调用粒度或 Schema 变化。
