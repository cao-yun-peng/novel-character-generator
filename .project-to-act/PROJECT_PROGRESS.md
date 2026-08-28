# 项目进度

## 当前任务

| 任务 | 状态 | 结果 |
|---|---|---|
| PIPELINE-V2-DESIGN-012 | completed | V2 总契约与 Schema 完成 |
| PIPELINE-V2-M1-013 | completed | 工程完成，模型质量 5/6 |
| PIPELINE-V2-N2-014 | completed | grounding/context 工程 Gate 通过 |
| PIPELINE-V2-M2-015 | completed | 离线工程 Gate 通过，数据集待审核 |
| CLEANUP-V2-016 | completed | 仓库和项目账本精简为 V2 单一路线 |
| ENV-ISOLATION-017 | completed | 当前仓库可独立导入、测试和静态检查；旧项目目录已删除 |
| REPO-PUBLISH-018 | completed | 独立历史分支 `v2-semantic-pipeline` 已推送并跟踪 GitHub remote |

## 阻塞项

- M1 仍漏掉 1/6 样本中的独立 body fact。
- M2 的 9 条 draft 数据集尚未获得用户审核，也没有真实 Provider 结果。
- M3–M5 尚未实现，端到端 Promotion Gate 不具备执行条件。

## 下一步

1. 用户审核 `tests/evaluation/m2_field_disambiguation_v1.json`。
2. 为 M1 剩余漏召回设计独立实验，不在现有评测集上盲目调参。
3. 前两项具备证据后建立 M3 实现任务。

## 进度历史

- 2026-08-28：当前独立历史已发布到原 GitHub 仓库的 `v2-semantic-pipeline` 分支；未修改或合并 `main`。
- 2026-08-28：当前仓库成为唯一工作区；修复包布局和虚拟环境路径，删除旧项目根目录并完成删除后复验。
- 2026-08-28：完成仓库清理，当前代码与账本统一为 V2 单一路线。
