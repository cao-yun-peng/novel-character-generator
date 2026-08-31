# E-20260831-M3-DOUPO-LIVE-EVAL-061

- 时间：2026-08-31（Asia/Shanghai）
- 任务：`M3-DOUPO-LIVE-EVAL-061`
- 阶段：Stage 5 `in_progress`，revision 2；本证据不推进阶段
- 风险：L1，主要风险为身份假合并
- 运行时：`0.1.0.dev12`
- Schema：`3.12.0-draft1`
- 模型：`deepseek-v4-flash`
- 有效期：Prompt、Schema、Provider、Grounding/聚类策略、输入小说或来源产物变化前有效

## 执行与恢复

1. 输入预检：19 tasks；每节点最多 2；模型 payload 系统字段命中 0；`.env` 存在 `DEEPSEEK_API_KEY` 变量名，未输出值。
2. 受限网络预尝试：19/19 为 `ProviderTransientError`，无 HTTP 成功响应；用于确认需联网权限，不作为模型质量数据。
3. 允许联网后的真实首轮：18/19 成功；1 项得到 HTTP 200，但 `status=incomplete/reason=max_output_tokens`，4096 输出预算不足。
4. 将该次进程 `DEEPSEEK_MAX_OUTPUT_TOKENS` 提高到 8192 后恢复：18 项从 task cache 读取，只新增 1 次调用并完成失败项。
5. 最终状态：19/19 成功，0 failures，registry built。

## 模型与注册表结果

- Grounded relations：17 same、0 different、2 uncertain。
- Grounded identity quotes：36；绝对 span 原文回放错误 0。
- Global characters：11。
- Linked：5（萧炎、萧薰儿/萧熏儿/熏儿、萧战、葛叶、纳兰嫣然）。
- Singleton：6（萧媚及五个 promoted 泛称人物）。
- Review items：2；unresolved bindings：0；cannot-link：0。
- Possible conflicts：4，均表现为事实值粒度差异，原事实保留。

成功任务 trace 汇总：input 41,423、cached input 10,112、output 19,187、reasoning 17,854、total 60,610 tokens；截断响应 usage 不可得，未包含。最终产物包含 19 条成功脱敏 trace；API Key 内容扫描命中 0，trace 敏感字段扫描命中 0。

## 验证

- `python -m unittest discover -s tests`：退出 0，109 tests passed。
- Draft 2020-12 Schema：19 model outputs 经运行时严格解析；19 grounded decisions 和 document registry 实例通过。
- Grounding replay：36/36 identity quotes 与小说原始 CRLF 文本绝对 span 一致。
- Project-to-Act validate：通过。
- Agent Lifecycle validate：通过；Stage 5/revision 2 保持不变。

## 质量判断

本样本最终五个 linked 组未发现明显错人，promoted 泛称也没有互相误合并。但多个 same 结果引用的是“两处上下文分别出现同名”，没有直接身份桥接句。Grounding 只证明引用真实，不能证明引用语义上足以支持同一人物；本样本没有覆盖同名不同人、different 或 cannot-link。因此真实执行 Gate 通过，身份模型质量 Gate 未通过。

另外发现两个工程审计缺口：review 汇总存在重复 evidence 展示；成功恢复后最终 `failures.json` 为空，失败详情没有追加保存，只有 `run-history.json` 保留失败计数。这两项不影响本次最终注册表，但应在下个修复任务处理。

## 文件哈希

- `identity-preparation-manifest.json`：`235aa32dd802f341dc7140cbc2ae36fda5f261978bf2f7497ace521bbaef9b5c`
- `identity-model-outputs.json`：`a7073a6a09b662ff57d9663e515c4f044ae066f7527dcc61755192cd757296d7`
- `grounded-identity-decisions.json`：`551a6f6d297f91eae83c16133e2934a5f8b26311b628071014c1a1f478e830ba`
- `document-character-registry.json`：`2ff08312ca47c03765a2808f675e4232cea353bbd4d8b90883755c3647fcac29`
- `provider-traces.json`：`f907b4728098d68b35e7b7d2a48dfabe765a7b4a0c33889b4f695ad030e1ccc9`
- `summary.json`：`d6c57e63440611ab41cbc8c8cb7e2740c0969c6f92ee0a97009d9b2658c28ea1`
- `run-history.json`：`24c9c34b308e02b7e193ee6ac892e576cd28641e602ae5f07a7bdd4048fc9746`
- `identity-run-diagnosis.md`：`b7f6d7a7deda967d735236d8aedfb0ef41e99a2a044cef64a46e6db604bd24a9`

## Gate

- 任务状态：completed。
- 真实 M3 系统执行与 Grounding Gate：通过。
- 身份模型质量 Gate：未通过，等待人工 gold 与对抗回归。
- Stage 5：继续 `in_progress`。
