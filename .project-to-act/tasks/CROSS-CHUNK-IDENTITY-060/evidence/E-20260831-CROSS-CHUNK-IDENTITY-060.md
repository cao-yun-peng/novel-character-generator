# E-20260831-CROSS-CHUNK-IDENTITY-060

- 时间：2026-08-31（Asia/Shanghai）
- 任务：`CROSS-CHUNK-IDENTITY-060`
- 阶段：Stage 5 `in_progress`，revision 2；本证据不推进生命周期阶段
- 风险：L1，主要风险是跨 Chunk 假合并
- 代码版本：工作区未形成可引用提交；以下使用文件 SHA-256
- 有效期：相关源码、Schema、Prompt、身份策略或斗破来源产物变化前有效

## 验证结果

1. `PYTHONPATH=src python -m unittest discover -s tests -v`
   - 退出状态：0
   - 结果：109 tests passed
   - 覆盖：模型字段隔离、候选上限、共享事实确定性边、严格/纯空白等价 Grounding、非空白改写拒绝、多 occurrence 歧义、same/alias、different/cannot-link、uncertain/unresolved、事实冲突保留、批处理写档案和断点恢复。
2. Draft 2020-12 Schema 与实例校验
   - 退出状态：0
   - `Draft202012Validator.check_schema` 通过。
   - `DocumentLocalCharacterNodes`、19 个 `M3IdentityEnvelope` 和全 uncertain 假 Provider 生成的 `DocumentCharacterRegistry` 实例通过。
3. 斗破离线身份准备
   - 命令：`python -m novel_character_generator prepare-document-identity ...`
   - 退出状态：0
   - Provider calls：0
   - 结果：23 local character nodes；其中 1 个零外貌事实 exact；1 deterministic same edge；19 pending M3 tasks；每节点最多 2 tasks。
   - 候选原因计数：same exact label 13、possible name variant 4、label contains 2、shared fact quote 2。
4. 产物审计
   - 所有模型 payload 的 `node_key/character_id/span/hash/ref/cache_key/task_cache_key` 字段扫描结果为 0。
   - 23 个节点的所有 context binding 均按绝对 span 对原始 CRLF 文本逐字回放通过。
   - 身份产物中未发现 `quote_hash` 或 `mention_anchor_spans`。
   - Manifest 保存 identity/candidate/context policy version、system instruction hash 与 response schema hash。
5. 端到端失败关闭演练
   - 使用只返回 `uncertain` 的假 Provider 完成 19/19 tasks 并建立注册表。
   - 结果：12 global characters、1 linked character（来自共享文档事实确定性边）、10 unresolved bindings、12 review items；未按同名擅自合并。

## 文件哈希

- `src/novel_character_generator/identity.py`：`27d84329756e3157e232da2da99c128ce41e788129dc1ae8491503986c6ec8ca`
- `src/novel_character_generator/identity_batch.py`：`60b4ce716a0ee47fa54116dbe98f661ee8dfe08bc771c8b099cb6dee4a3d6175`
- `src/novel_character_generator/__main__.py`：`71c10b3eb1446388246e6ced90fad52dfceed9e893073c6378d7b54b39841b97`
- `tests/test_identity.py`：`5230f4bb749c4562b0ae343dce3011785e856e2fd3fb448b5d4696df5fb4557b`
- `docs/contracts/simplified-character-evidence-v3-model-schemas.json`：`d31b7432e29b2ebc797eaf213e7e31eea85c3b4e38ed72cde8c64148a7a2665a`
- `docs/33-simplified-character-evidence-pipeline-v3.md`：`1409e3849e0a9c889f2e60f228faebb0077259d5a563f27bca6ebef20d809f20`
- `runs/doupo-first5-identity-dev12-20260831/identity-preparation-manifest.json`：`235aa32dd802f341dc7140cbc2ae36fda5f261978bf2f7497ace521bbaef9b5c`
- `runs/doupo-first5-identity-dev12-20260831/document-local-character-nodes.json`：`667f6127e8fbe5696d1848031a84875f83aa8b6f32e0faaf2126df284840d818`
- `runs/doupo-first5-identity-dev12-20260831/identity-envelopes.json`：`dc3e1295d0796a77d8cf3fa7e3abaa3bac1d14be73598a4ed75c6fb08b9dc9ca`
- `runs/doupo-first5-identity-dev12-20260831/summary.json`：`68c5a2243ff2324657155f977931dafeca4dfe6f26664318955bc5d84432fe0b`

## Gate 结论

任务级纵向切片通过：代码、契约、离线产物与失败关闭路径均满足任务验收，可以关闭 `CROSS-CHUNK-IDENTITY-060`。

生命周期和功能质量 Gate 不通过：没有调用真实 DeepSeek M3，也没有人工标注的身份 precision/recall/review-rate。`F-NEW-IDENTITY-006` 和 Stage 5 继续保持 `in_progress`。下一 Gate 需要真实 19-task 输出、人工身份标注、同名不同人/泛称/多候选回归集和成本统计。
