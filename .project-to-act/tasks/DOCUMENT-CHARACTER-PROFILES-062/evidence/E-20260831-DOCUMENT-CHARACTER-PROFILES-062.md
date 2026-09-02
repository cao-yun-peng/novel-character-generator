# E-20260831-DOCUMENT-CHARACTER-PROFILES-062

- 时间：2026-08-31（Asia/Shanghai）
- 任务：`DOCUMENT-CHARACTER-PROFILES-062`
- 基线提交：`85985e3380a755a1cd2e5d99e9cc401b0c22d335`
- 运行时：`0.1.0.dev13`
- Schema：`3.13.0-draft1`
- 有效期：对应本任务文件 hash、斗破来源产物和当前工作区；相关代码、Schema 或来源 run 变化后需重验

## 验证

1. `python -m novel_character_generator build-document-character-profiles ...`
   - 退出状态：0
   - Provider calls：0；命令和模块不加载 Provider
   - 结果：11 global characters、5 linked、6 singleton、61 assigned facts、0 unassigned facts、62 source occurrences、4 possible conflicts、2 review、0 unresolved/cannot-link
2. `python -m unittest discover -s tests`
   - 退出状态：0
   - 结果：118 tests passed
3. Draft 2020-12 `DocumentCharacterProfiles` 实例校验
   - 退出状态：0
   - 结果：`schema_valid=true`
4. 独立原文回放
   - 退出状态：0
   - 结果：61 个唯一 `fact_hash`；61/61 fact quote span、62/62 evidence span 和 62/62 Chunk hash 回放通过，失败 0
5. `git diff --check`
   - 退出状态：0
   - 结果：无 whitespace error；仅报告 Windows LF→CRLF 提示

## 核心工件 SHA-256

- `src/novel_character_generator/document_profiles.py`：`22a0249b1b9e00ad003dd5d41d522e9ac5a10809110d2259c8988dfccfa93e92`
- `tests/test_document_profiles.py`：`b979715126ef2037569828b22d17199e62976eff58142ba38df7412167c85909`
- `docs/contracts/simplified-character-evidence-v3-model-schemas.json`：`52c78f8065604d0ea2f6d888620070651b5525d5ecda178d27eb6050391defb3`
- `runs/doupo-first5-character-profiles-dev13-20260831/document-character-profiles.json`：`454a82f586e3cc2304dfe0fd6ea20e7f91f63dd12e4724c75b717a8e20aca0bb`

## 边界

- 本任务只证明确定性 join、完整性检查和斗破现有产物物化正确，不代表上游模型外貌事实质量已完成人工评测。
- 不生成自然语言画像，不解决时间/场景状态，也不扩展尚未真实出现的同名不同人策略。
