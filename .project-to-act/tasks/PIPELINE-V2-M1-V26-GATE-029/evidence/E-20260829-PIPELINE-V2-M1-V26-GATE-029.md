# E-20260829-PIPELINE-V2-M1-V26-GATE-029

## 配置与规则

- Prompt：`visual-evidence-discovery-prompt-v2.6`；文件 SHA-256 `b9f230b826296ff0162e870c22e527db0907c1053f18e2a1764a7279de058ff0`；运行时 hash `cbb889fe0703b5fe964fce4e2d99696561093a6d0aa4b4b23051e4b8bfafc844`。
- Source Match Policy：`visual-evidence-source-match-policy-v2`；实现 SHA-256 `2d1f9318085bc7755777004a292962c84a81a8db8f769a0b01e9a61cf8b9745e`。
- Rubric：`visual-evidence-evaluation-rubric-v2.5`；最终实现 SHA-256 `9f74c9ea65dc24932d1b11845f90d044ec426bc703e3801eb70044ffb4de3f88`。
- 规则只删除 Unicode whitespace 进行匹配；全部非空白字符及标点必须逐字同序，且归一化后唯一。成功后回填 Chunk 原始切片，真正改写或多重匹配失败。
- 旧 v2.5 真实 outputs 在新规则下重评分为 1 pass / 6 review / 3 fail；004 从 fail 变为 review，required 2/2、quote 6/6，证明仅空白差异已被正确回填。

## Prompt v2.6 短集运行

- Dataset：`m1-visual-evidence-short-v2.2-approved`；SHA-256 `5579c8533a304b338eddf564a91acfc102137f42ed4edfb3670701dbf389166d`。
- Provider/model：DeepSeek / `deepseek-v4-flash`；16 次调用完成，12 succeeded、4 completed_with_warnings（均为空结果边界样本）；总 token 23,024。
- 最终 Rubric v2.5 重评分：15 pass / 0 review / 1 fail；recall `0.923076923076923`、precision `0.923076923076923`、quote fidelity `1.0`、owner required recall `0.875`、owner binding precision `0.916666666666667`。
- 唯一 fail：003 输出逐字、唯一且语义有效的“一个红衣少女”，但 approved owners/evidence 只接受“红衣少女”；作为数据测量缺口待人工审核，不自动改 approved Dataset。
- Outputs SHA-256 `c07c08474bb1bc3fd2691d63d06996a8044b3e798f97dbd64c883c33ed39fe15`；最终报告 SHA-256 `7f41199c7479048cadccff99b80bb8352de05f062fb1fd0876b5a05642727219`；Provider run manifest SHA-256 `5beb7398d6bd7d5bcce0d79ae9939f042112d0a43870a4ad38cb8cc7ab95e03d`。
- Provider run 完成后按用户已确认的混合引文规则修正 forbidden；因此保留原 run/report，同时使用相同 outputs 和最终 Rubric hash 生成 `report-rubric-v2.5-final.json`，未重复调用模型。

## Prompt v2.6 真实集运行

- Dataset：`m1-visual-evidence-real-v2.4-draft`；SHA-256 `94f7f216ccf0d6d84a2960b834c781b53f1312fda14c19f28cb1236ebaf92a91`。
- Provider/model：DeepSeek / `deepseek-v4-flash`；10 次调用完成；9 succeeded，005 为 `visual_evidence_quote_not_unique_in_chunk`；总 token 22,868。
- 原始 Rubric v2.5：2 pass / 3 review / 5 fail；recall `0.615384615384615`、precision `0.326923076923077`、quote fidelity `0.989010989010989`、owner required recall `0.590909090909091`、owner binding precision `0.326923076923077`。
- Pass：007、010。Review：001、002、006。Fail：003、004、005、008、009。
- 006 已召回少女相对年龄并由 fail 改善为 review；008 已召回脱鞋 presentation，但 raw score 仍受年龄/金环 alias/跨度及虎牙漏召回影响。
- 003/004/008/009 含有效但未被 draft Dataset 接受的 owner alias 或逐字跨度，须人工审核后离线重评分，不能直接归因为 Prompt 失败。
- Outputs SHA-256 `6f491b89bdea8c90522ef8e6f46a8b2a0ac0d931b9307249c1e592f79c633d5d`；报告 SHA-256 `80816c9531ac7ca32c7bde75330ca8608eae3d20a5f1dab293bdfc24f72b15c6`；run manifest SHA-256 `f832a7e53336dbe8287e9510216843883b09fea447f86d2e04f5b046a6357060`。

## 工程 Gate

- Pytest：89 passed。
- Ruff：通过。
- Mypy：36 source files 无问题。
- `git diff --check`：通过。
- Project-to-Act validate：`valid=true`，无 issues。
- Agent lifecycle validate：失败；原因是既有 ledger 的 stage 0–4 状态枚举、目录 artifact、重复 revision 等历史问题。该 ledger 在任务开始前即为 revision 1/current stage 5，本任务未修改也未伪造 transition；因此不得据本任务宣称阶段 Gate 通过。
- 用户已在当前轮明确授权两套 Provider 运行；未记录 API key，未写数据库，未产生 active Observation。
- `AGENT_LIFECYCLE.json` 保持 preexisting revision 1/current stage 5，不手工伪造阶段 Gate。
