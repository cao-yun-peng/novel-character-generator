# Novel Character Generator

这是一个从零重新开始的中文小说人物外貌证据项目。

当前分支不复用旧版源码、测试、评测数据、提示词或运行结果；新的 M1 运行时从冻结契约重新实现。

## 当前流程

1. M1：从 Chunk 中识别人物提及，标记 `mention_type`（`exact` / `describe` / JSON `null`）和 `mention_scope`（`individual` / `collective` / JSON `null`），并把相关原文证据放进该提及块。
2. N2：验证人物称呼和证据是否确实存在于 Chunk；证据严格匹配失败时只允许忽略 Unicode 空白后完全一致的安全恢复。Grounding 后汇总当前 Chunk 的 exact evidence，并从所有 describe 中删除逐字相同的 evidence；describe 被删空时删除整个 grounded block。
3. M2 第一模式：每个 `exact` 只调用一次，并在该次输入中携带本轮全部 `describe` 块，先尝试把描述归给已有 exact。
4. N3：验证证据并汇总归属。唯一归属的 describe 原文片段被已有 exact 消费；未被任何 exact 消费的 describe 单独进入 M2 第二模式，可拆成一个或多个新的 Chunk 内正式人物；冲突片段进入复核。
5. M3 身份层：将 exact/promoted 局部人物跨 Chunk 建立有界候选；模型只判断一对人物并返回身份原文，代码严格 Grounding 后生成全局人物档案、cannot-link、未决绑定与冲突记录。

“张三”“林黛玉”等明确名称属于 `exact`；“老者”“女孩”“红衣女子”“月袍老人”等单人泛称属于 `describe + individual`；“十七道白色的身影”“众人”等群体称呼属于 `describe + collective`。collective 证据会保留审计，但被隔离在单人物解析与 promotion 之外。同一句证据可暂时出现在 M1 多个提及块中；进入 N2 后 exact 对相同原文 quote 优先，describe 中的副本被删除。

`describe` 使用版本化泛称后缀表复核，例如 `红衣女子.endsWith("女子")` 后归一为 `describe`。明确名字优先抽取为最小 exact 提及。

人物称谓只校验能否在正文中逐字匹配，不再输出出现次数或位置。证据仍使用半开字符 span，以便确认 `evidence_quote` 的确来自原文；M2 模型不读取或输出 span，代码根据模型返回的最小 `fact_quote` 安全且唯一匹配后回填来源位置。长文本通过版本化重叠 Chunk 和显式 `complete/truncated` 清单证明覆盖范围。技术审查调整见 [docs/35-v3-contract-review-adjustments.md](docs/35-v3-contract-review-adjustments.md)。

所有模型调用都分成“代码编排信封 → 最小模型输入 → 最小模型输出 → 代码回填验证”。来源版本、Chunk ID、ref、span、状态、hash、cache key 和 trace 留在代码层；M1 模型只看 `chunk_text`。M2 归属模式只读取一个 individual exact、它的证据、全部 individual describe 原文和 `chunk_text`，只输出 `belongs_to_target` 外貌事实；独立建人模式同样只返回人物标签与事实原文，不处理编排字段。N2 grounded packet v6 已取消逐条 `quote_hash` / `mention_quote_hash`，仍保留 document/chunk/packet/fact 和运行审计 hash。

## 当前产物

- `src/novel_character_generator/`：重叠分块 Manifest、M1/N2、M2 双模式编排、N3 span 仲裁、文档事实聚合、可恢复 M3 身份解析和严格 quote grounding
- `tests/`：分块、模型字段隔离、M2/N3/promotion、文档去重、身份候选上限、same/different/uncertain、cannot-link、冲突保留与断点续跑测试
- [流程契约](docs/33-simplified-character-evidence-pipeline-v3.md)
- [机器 Schema](docs/contracts/simplified-character-evidence-v3-model-schemas.json)
- [开源项目与 Skill 调研](docs/34-open-source-novel-character-visualization-research.md)
- [契约审查后的技术调整](docs/35-v3-contract-review-adjustments.md)
- [novel-characters 上游参考副本](references/upstream/shuohao-skills/UPSTREAM.md)
- [文档入口](docs/README.md)

## 当前状态

M1 已接入 DeepSeek Responses API Provider：默认模型为 `deepseek-v4-flash`，使用 `json_schema` 约束输出；模型只接收 `chunk_text`、M1 system instruction 和 response schema。返回结果仍须经过本地严格结构校验、Chunk 信封绑定、确定性 grounding 和 `exact-evidence-precedence-v1` 去重，才能生成 N2 packet。人物称谓本身不生成位置统计。

M2 与 N3 运行时已经接线：`build_m2_attribution_envelopes` 为每个 individual exact 生成一次携带全部 individual describe 的任务；`resolve_n3_chunk` 将 exact 自有事实直接归并，对 describe fact span 执行跨 exact 仲裁，隔离冲突并重建剩余池；`run_n3_promotion_from_m2_run` 再把每个非空剩余池作为独立、可恢复的 promotion 任务。模型看不到 ref/span/hash，collective 不进入这些入口。promotion 使用 `promotion-partial-fact-acceptance-v1`：每条事实独立严格 Grounding，唯一事实保留，重复/歧义事实进入 review 并留在未分配池，不猜 occurrence，也不因一条失败事实删除整个人物。

使用既有 M1 run 重新物化最新 N2 并可恢复地运行 M2 exact attribution：

```powershell
$env:PYTHONPATH='src'
python -m novel_character_generator run-deepseek-m2-from-m1-run `
  --input-file 'tests/小说/斗破苍穹前5章.txt' `
  --source-run-dir 'runs/doupo-first5-m1-scope-v4' `
  --output-dir 'runs/doupo-first5-m2-dev7-20260831' `
  --env-file '.env' `
  --show-progress
```

命令先验证原文/Manifest hash，再从保存的 M1 model output 重放当前 N2。每个 M2 task 独立落盘，网络中断后会按 `task_cache_key` 恢复；模型输出、代码 grounded 输出、N2 重放 packet、失败、脱敏 trace、摘要和追加式运行历史分别保存。该命令会产生真实 API 调用和费用。

基于完整 M2 run 运行确定性 N3 和可恢复 promotion：

```powershell
$env:PYTHONPATH='src'
python -m novel_character_generator run-deepseek-n3-promotion-from-m2-run `
  --input-file 'tests/小说/斗破苍穹前5章.txt' `
  --source-m1-run-dir 'runs/doupo-first5-m1-scope-v4' `
  --source-m2-run-dir 'runs/doupo-first5-m2-dev7-20260831' `
  --output-dir 'runs/doupo-first5-n3-promotion-dev9-20260831' `
  --env-file '.env' `
  --show-progress
```

N3 本身不调用模型；只有 `next_action=promote_remaining_describe` 的 individual describe 池会产生 API 调用。N3 target packet、describe pool、promotion 模型原始输出、grounded 输出、失败、脱敏 trace、摘要和追加式运行历史分别保存。

已有模型输出可在不调用 Provider 的情况下按当前策略重新 Grounding：

```powershell
$env:PYTHONPATH='src'
python -m novel_character_generator replay-promotion-grounding `
  --source-run-dir 'runs/doupo-first5-n3-promotion-dev9-20260831' `
  --output-dir 'runs/doupo-first5-n3-promotion-dev11-partial-20260831'
```

重放会校验 envelope 与模型输出的一一对应关系，记录来源文件 hash，并生成新的 grounded、review 与 summary；旧 run 保持只读。

把 N3 与 promotion 的 Chunk 局部事实换算成文档绝对 span，并安全消除重叠 Chunk 副本（纯确定性代码，不调用模型）：

```powershell
$env:PYTHONPATH='src'
python -m novel_character_generator build-document-character-evidence `
  --input-file 'tests/小说/斗破苍穹前5章.txt' `
  --source-m1-run-dir 'runs/doupo-first5-m1-scope-v4' `
  --source-m2-run-dir 'runs/doupo-first5-m2-dev7-20260831' `
  --source-n3-run-dir 'runs/doupo-first5-n3-promotion-dev11-partial-20260831' `
  --output-file 'runs/doupo-first5-n3-promotion-dev11-partial-20260831/document-character-evidence.json'
```

统一文件保留 document/chunk/artifact/fact hash、原始事实与 evidence quote、文档绝对 span，以及每条合并事实的全部来源 Chunk occurrence。

离线准备跨 Chunk 身份节点与有界候选（不调用模型、不产生费用）：

```powershell
$env:PYTHONPATH='src'
python -m novel_character_generator prepare-document-identity `
  --input-file 'tests/小说/斗破苍穹前5章.txt' `
  --source-n2-packets-file 'runs/doupo-first5-m2-dev7-20260831/source-n2-grounded-packets.json' `
  --source-n3-run-dir 'runs/doupo-first5-n3-promotion-dev11-partial-20260831' `
  --document-evidence-file 'runs/doupo-first5-n3-promotion-dev11-partial-20260831/document-character-evidence.json' `
  --output-dir 'runs/doupo-first5-identity-dev12-20260831'
```

确认 `identity-envelopes.json` 后，可以可恢复地调用 DeepSeek 完成 M3，并在所有任务成功后生成 `document-character-registry.json`：

```powershell
$env:PYTHONPATH='src'
python -m novel_character_generator run-deepseek-document-identity `
  --input-file 'tests/小说/斗破苍穹前5章.txt' `
  --source-n2-packets-file 'runs/doupo-first5-m2-dev7-20260831/source-n2-grounded-packets.json' `
  --source-n3-run-dir 'runs/doupo-first5-n3-promotion-dev11-partial-20260831' `
  --document-evidence-file 'runs/doupo-first5-n3-promotion-dev11-partial-20260831/document-character-evidence.json' `
  --output-dir 'runs/doupo-first5-identity-live-dev12-20260831' `
  --env-file '.env' `
  --show-progress
```

默认每个局部节点最多产生 2 个候选任务。相同姓名或相似外貌不会自动合并；模型必须返回可被代码唯一定位的身份原文。第二条命令会产生真实 API 调用与费用。

### 配置 DeepSeek

API Key 只从进程环境变量读取。不要把真实 Key 写进 `.env.example`、提交到 Git 或发送到聊天中。

PowerShell 当前会话配置：

```powershell
$secret = Read-Host 'DeepSeek API Key' -AsSecureString
$pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
try {
  $env:DEEPSEEK_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
} finally {
  [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
}
$env:DEEPSEEK_MODEL = 'deepseek-v4-flash'
```

其他可选配置见 `.env.example`。当前 Provider 强制 HTTPS，默认请求 `https://api.deepseek.com/responses`；对 429、5xx 和瞬态网络错误执行有界重试，对鉴权失败、余额不足和参数错误立即失败。

对一个短 Chunk 做显式探测：

```powershell
$env:PYTHONPATH='src'
$env:PYTHONDONTWRITEBYTECODE='1'
python -m novel_character_generator probe-deepseek-m1 --text '林黛玉眉目清秀，身形纤细。' --show-trace
```

标准输出是经过 N2 grounding 和 exact precedence 的 packet；批处理另外生成 `n2-grounding-traces.json`，记录后缀归一、describe evidence 删除和空块删除，不包含 API Key、Prompt 或模型推理。`--show-trace` 只在标准错误输出 Provider 调用信息。该命令会产生一次真实 API 调用和相应费用，自动测试不会访问网络。

运行最小测试：

```powershell
$env:PYTHONPATH='src'
$env:PYTHONDONTWRITEBYTECODE='1'
python -m unittest discover -s tests -v
```
