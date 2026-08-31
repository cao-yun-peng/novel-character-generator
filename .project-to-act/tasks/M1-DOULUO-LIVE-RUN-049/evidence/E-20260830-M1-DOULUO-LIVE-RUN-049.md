# E-20260830-M1-DOULUO-LIVE-RUN-049

## 结论

- DeepSeek Responses API 真实 smoke 成功：`deepseek-v4-flash`、HTTP 200、结构化输出经 M1 Schema 和 grounding 接受。
- 输入 `tests/小说/斗罗大陆前20章.txt`：110,951 bytes，37,655 Unicode code points，SHA-256 `4dd3d57c99f4b2548c45c69a391918a391782e64a4526971b2e6e34a81e2ed0e`。
- 最终策略：`fixed-codepoint-window-2500-overlap-250-v1`，17 个 Chunk，完整覆盖到文档末尾。
- 首轮完成 16/17；第 3 块明确返回 `incomplete_details.reason=max_output_tokens`，用同一 Manifest 断点续跑，仅重试该块并完成。最终 17/17 成功、失败清单为空。
- 最终输出：63 个 schema-valid candidate mentions（31 exact、32 describe、0 null），60 个 grounded mentions，149 条 approved evidence quotes，4 条 rejected evidence quotes。
- 成功结果保存的 usage 合计：input 39,724、cached input 17,792、output 59,321、reasoning 54,803、total 99,045 tokens。该合计不含 Provider 未返回 usage 的截断尝试。
- 45 项离线单元测试通过。Lifecycle 保持阶段 5、revision 2、L1；本任务完成不等于阶段 Gate 完成。

## 产物

- `runs/m1-douluo-20ch-20260830-v3/manifest.json` — SHA-256 `a22e05c2b15438fcf7c42fb4b7d434466c853d31bdb52ff67215d9b589b4a188`
- `runs/m1-douluo-20ch-20260830-v3/m1-model-outputs.json` — SHA-256 `382bbe53305d2248374d1fb0a680fbd857e582f41b31e8945901d63e9b94b625`
- `runs/m1-douluo-20ch-20260830-v3/m1-grounded-packets.json` — SHA-256 `d4665833729a58818973c54ebc698ef8bb40e34c2f4a971602464eafcb02ae6f`
- `runs/m1-douluo-20ch-20260830-v3/summary.json` — SHA-256 `b1a148a1729201b676108684df8b5c30b48d8c46c27d5e68bafdf6136f95efee`
- `runs/m1-douluo-20ch-20260830-v3/chunks/` — 17 个逐块 validated output + grounded packet + credential-free trace。

## 边界

- 这些统计反映模型结构化输出和确定性逐字定位，不是人工标注的 precision/recall。
- 250 字符重叠可能产生跨 Chunk 重复；跨 Chunk 绝对 span 换算与去重尚未实现。
- 本任务只运行 M1/N2 Chunk 局部 grounding，没有运行 M2/N3 或人物合并。
- `.env` 仅用于当前进程注入；证据和运行产物不包含 API Key、Prompt、完整请求正文或 reasoning 内容。
