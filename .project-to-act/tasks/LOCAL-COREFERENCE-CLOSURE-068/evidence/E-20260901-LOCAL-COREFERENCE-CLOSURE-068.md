# LOCAL-COREFERENCE-CLOSURE-068 验收证据

- 日期：2026-09-01
- 基线 HEAD：`85985e3380a755a1cd2e5d99e9cc401b0c22d335`
- 运行时：`0.1.0.dev17`
- Schema：`3.17.0-draft1`
- 策略：`grounded-local-coreference-v1` / `bounded-local-candidate-retrieval-v3`
- Provider 调用：0

## 纵向切片结果

- 复用基础 M3 grounded decisions 63 条、rescue supplemental grounded decisions 6 条。
- 新增 deterministic local-coreference edge 1 条：`高大的身影 -> 唐昊`。
- 关系链完整位于文档绝对 span `[5591,5814)`，包含“高大的身影”“中年男子”和“这就是唐昊”，并从文档及双方保存的 context 逐字回放。
- deterministic edges 从 1 增至 2；global characters / profiles 从 8 降至 7；singleton 从 4 降至 3。
- 唐昊最终簇包含 11 个成员、28 条 appearance facts，labels 包含 `唐昊`、`高大的身影`、`高大苍老的男人`。
- 129/129 appearance facts、130 source occurrences、0 unassigned facts 保持。
- 1 个 unresolved 仍为“看门的青年”且 reason 为 `insufficient_identity_evidence`；2 条 cannot-link、9 条 review、13 条 possible conflicts 保持。

## 自动验证

执行：

```powershell
$env:PYTHONPATH='src'
python -m unittest discover -s tests
python -m compileall -q src tests
```

结果：140 tests，全部通过；compileall 退出码 0。

执行离线回放：

```powershell
$env:PYTHONPATH='src'
python -m novel_character_generator replay-local-identity-closure `
  --input-file 'tests/小说/斗罗大陆前20章.txt' `
  --source-identity-run-dir 'runs/douluo-20ch-e2e-dev13-20260831/identity' `
  --source-rescue-run-dir 'runs/douluo-20ch-e2e-dev13-20260831/identity-rescue-fixedpoint-dev16' `
  --evidence-file 'runs/douluo-20ch-e2e-dev13-20260831/document-character-evidence.json' `
  --output-dir 'runs/douluo-20ch-e2e-dev13-20260831/identity-local-coreference-dev17'
```

连续两次执行后 6 个 JSON 的 SHA-256 均未变化：

- `document-character-profiles.json`: `9EB5D36A868DEE42F3E414320743CF62ABB664B98C64ACCC5A5ABF037FAEAADE`
- `document-character-registry.json`: `9FF571B51398B734427303BBAAE2803409F6280EA8A2107A15759236543C1EE9`
- `identity-deterministic-edges.json`: `E4281F1DC065FDE39358780ED2B8BCAE96F18DD9DF40FD5167CBD7DDCB161C63`
- `local-coreference-edges.json`: `14E9277DC0C24D5818A2A8AC99C82C6C7ED31FA787FEE9A9FA63F11017863A63`
- `local-identity-closure-manifest.json`: `8DFDF509D9311CC32C7C0713BA876921D33D77D5C26EC25CBD2B4B609EA54D67`
- `summary.json`: `ECC52DE0C4EF8C67E0890CC8C9DFC792940FDECC11701AFE55C6809AC5A3A17C`

Draft 2020-12 meta-schema、`IdentityDeterministicEdges`、`DocumentCharacterRegistry` 和 `DocumentCharacterProfiles` 实例校验全部通过。`git diff --check` 退出码 0。Project-to-Act `--validate` 返回 `valid: true`、`issues: []`。

## 边界结论

本验收只证明局部显式关系的确定性闭合纵向切片成立。跨 Chunk、无关系陈述、问句、篡改证据和纯姓名共现均不建边；不使用当前全局唯一姓名推断身份。本任务不替代 M1/M2/promotion 人工质量 Gate，也不包含 post-link fact groups 或外貌状态层。
