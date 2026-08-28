# 项目进度

## 当前任务

| 任务 | 状态 | 结果 |
|---|---|---|
| PIPELINE-V2-DESIGN-012 | completed | V2 总契约与 Schema 完成 |
| PIPELINE-V2-M1-013 | completed | 工程完成，模型质量 5/6 |
| PIPELINE-V2-N2-014 | completed | grounding/context 工程 Gate 通过 |
| PIPELINE-V2-M2-015 | completed | 离线工程 Gate 通过，数据集待审核 |
| CLEANUP-V2-016 | completed | 仓库和项目账本精简为 V2 单一路线 |

## 阻塞项

- M1 仍漏掉 1/6 样本中的独立 body fact。
- M2 的 9 条 draft 数据集尚未获得用户审核，也没有真实 Provider 结果。
- M3–M5 尚未实现，端到端 Promotion Gate 不具备执行条件。
- `data/test-tmp` 仍有约 585.9 MB 被 Windows ACL 拒绝删除；目录已被 Git 忽略，160 个原已跟踪文件均处于删除状态，不影响 V2 代码或测试。

## 下一步

1. 用户审核 `tests/evaluation/m2_field_disambiguation_v1.json`。
2. 为 M1 剩余漏召回设计独立实验，不在现有评测集上盲目调参。
3. 前两项具备证据后建立 M3 实现任务。

## 进度历史

- 2026-08-28：完成仓库清理，当前代码与账本统一为 V2 单一路线。
