# M1 v2.5 approved 真实 Chunk 测试交接

## 已完成

- 用户已批准并冻结 `m1-visual-evidence-real-v2.3`。
- Prompt v2.5 / `deepseek-v4-flash` attempt 2 完成 10 条调用：8 succeeded、2 deterministic validation failed。
- Rubric：0 pass / 1 review / 9 fail；完整 M1 evidence Gate 未通过。
- 运行器已修正为单条确定性失败落盘并继续批次；80 项测试、Ruff、Mypy、diff check 和 Project-to-Act validate 通过。

## 安全边界

- API key 只从本地环境加载，不写入输出、报告、manifest 或项目账本。
- 所有模型响应必须经过 deterministic validation 后才进入评分。

## 测量限制

- 001、002、003 的有效明确人名或完整人物短语未被 owner accepted mentions 覆盖。
- 007 需要复核可接受逐字跨度。
- 因此原始 0 pass 不能全部归因于 Prompt；需先升级并重新审核数据集。

## 下一步

1. 建立真实集 v2.4-draft，修复 owner alias 与可接受跨度覆盖。
2. 重新人工审核后先对同一 outputs 重评分。
3. 再针对明确的逐字唯一定位、漏召回、人物锚点和服饰/持物边界问题优化 Prompt。
