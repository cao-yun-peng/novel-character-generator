# M1 Prompt v2.9 双集 Provider 检查证据

## 授权与范围

- 用户明确确认将短集 16 条和真实集 10 条 Chunk 文本发送至 `.env` 配置的外部 LLM Provider。
- Provider/model：DeepSeek / `deepseek-v4-flash`；wire API `chat_completions`；reasoning effort `none`；最终完整运行使用 `max_output_tokens=4096`。
- 无数据库写入、无 active Observation、无生产路由变更；未保存 API key 或原始 Provider 响应。

## 运行结果

### 短集 `m1-visual-evidence-short-v2.3-draft`

- 工件目录：`data/diagnostics/m1-v2.9-short-v2.3-draft/`
- 16/16 pass，0 review，0 fail。
- evidence recall、candidate precision、quote fidelity、required owner recall、owner binding precision、must-be-null accuracy 均为 1.0。
- 全部 case 成功完成 deterministic validation；无 validation failure。

### 真实集 `m1-visual-evidence-real-v2.5-draft`

- 工件目录：`data/diagnostics/m1-v2.9-real-v2.5-draft/`
- 1 pass，6 review，3 fail；10/10 case 已完成 Provider 尝试或明确失败落盘。
- evidence recall `0.8076923076923077`；candidate precision `0.4489795918367347`；quote fidelity `0.9882352941176471`；required owner recall `0.7727272727272727`；owner binding precision `0.4489795918367347`；must-be-null accuracy `1.0`。
- deterministic validation：005 为 `visual_evidence_quote_not_unique_in_chunk`；007 为 Provider `provider_finish_length`，运行器记录为 `provider_failed` 并继续后续 case。

## 重点判读

- 005：Prompt v2.9 的通用唯一性规则在本次模型输出中仍未稳定遵守；模型继续输出重复裸描述，并漏掉 `young_face`。当前金标的唯一引用仍正确，不修改 Dataset。
- 006、009：用户此前已确认没有实质问题；本次报告中 006 为 review、009 为 review，不作为 Prompt 缺陷。
- 007：Provider 完成长度异常，不应直接归因 Prompt 质量；运行器已改善为逐条失败关闭，避免整批中止。
- 与 v2.8 对比：短集保持 16/0/0；真实集由 2/5/3 变为 1/6/3。由于 Provider 随机/完成异常与 additional-candidate 分布变化，不能把此结果解释为 Prompt 单变量质量下降；005 的非唯一引文则是稳定复现的待解决问题。

## 工件哈希

- v2.9 Prompt runtime SHA-256：`a55cc18e274e7f3eb17ef9c61cbfb201d7e46993fff24fe9d70ec37e35688b13`。
- Short outputs/report/run SHA-256：`8b5a0240a3c0bfbdedb2cafe6b6f209e534ef7f9cb5d6707344c136210885520` / `5083ff83a0624cd7baba8bd1fe05710849efe7fb7d322c128cbbd17729c835c6` / `e2ff26801029390b8119066716e4333cfc205d2cd56479f94153f88005fcc72f`。
- Real outputs/report/run SHA-256：`c434fb26991290f4e8af863dc041aab05b0a27c4ced8319cc0835c5c9be0ba0e` / `4fb9acc1342c48abb11e48bceb75d594748c470b928ca328709329b8e4c06089` / `6b735db9de85182e4d39f8237f6708fc47611aefcf035213e33a9dd0f6446b59`。
- Real manifest records model config version `visual-evidence-model-config-v2:4a16eeec596fd2c9`, Rubric v2.5 and Source Match Policy v2 hashes.

## 工程验证与 Gate

- 全量测试：89 passed。
- Ruff：passed；Mypy：36 source files passed；Project-to-Act validate：valid；`git diff --check`：passed（仅既有 LF/CRLF warning）。
- M1 evidence Gate：仍 `blocked_pending_user_review`；不能产生 active Observation 或宣称发布就绪。
