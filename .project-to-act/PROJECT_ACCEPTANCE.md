# 项目验收

## 当前验收结论

新项目的设计基线已建立，但运行时尚未开始，不能宣称 M1、N2、M2、N3 已实现。

## 验收标准

| 标准 | 状态 |
|---|---|
| 新流程契约存在且可阅读 | 通过 |
| 机器 Schema 通过 Draft 2020-12 校验 | 通过 |
| exact/describe/null 约束和错误组合拒绝 | 通过（设计/Schema） |
| *女子 等 describe 后缀匹配顺序与归一 trace | 通过（设计） |
| exact×describe M2 归属输出与 N3 消费结果 | 通过（设计/Schema） |
| 当前工作目录不再包含旧源码、旧测试、旧数据和旧文档 | 通过 |
| M1 运行时和提示词 | 未实现 |
| N2/M2/N3 运行时 | 未实现 |
| 人物记忆 | 待设计 |

## 证据索引

- `.project-to-act/tasks/PIPELINE-V3-SIMPLIFIED-039/evidence/`
- `.project-to-act/tasks/PROJECT-V3-CLEAN-START-040/evidence/`
- `.project-to-act/tasks/PIPELINE-MENTION-CLARITY-041/evidence/`
- `.project-to-act/tasks/MENTION-SUFFIX-RULE-042/evidence/`

## 说明

本机仍有一个因 Windows ACL 无法移除的已忽略 `.pytest_cache/` 目录；其副本已移到仓库外备份。它不是源码、文档、依赖或新项目运行资产。

## 验收记录

- 2026-08-30：用户确认 `*女子` 后缀匹配方案；规则、优先级、最小提及拆分和 N2 归一 trace 已冻结。
- 2026-08-30：exact/describe/null 与 describe 循环完成静态契约验收；运行时和模型效果仍未实现。
- 2026-08-30：完成干净重启。旧工程资产退出当前工作目录；新流程仍只有契约和 Schema，运行时未实现。
