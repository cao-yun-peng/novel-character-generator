# 项目总览

## 基本信息

- 项目：Novel Character Generator
- 分支：`v3-simplified-character-evidence`
- 状态：干净重启，只有新流程契约，尚无运行时代码
- 工作区：`E:\project\agent\novel-cahracter-generator`

## 项目目标

从中文小说 Chunk 中提取人物外貌事实，并确保每条进入后续流程的事实都能追溯到原文证据和对应的局部候选人物。

## 范围

- M1：人物提及标记为 exact/describe/null；明确名称才是 exact，泛称和描述短语由版本化后缀表复核为 describe
- N2：验证 `mention_quote` 和 `evidence_quote` 是否存在于 Chunk
- M2：每个 describe 分别与每个 exact 目标组合解析
- N3：执行证据三态校验、describe 唯一认领、冲突保留、片段消费与剩余池重跑
- 人物记忆：只预留 `local_character_ref -> character_id` 接口

## 当前非目标

- 旧版代码、提示词、测试、评测数据和运行结果复用
- 人物合并与长期记忆的具体策略
- 数据库、Web API、图像生成和生产发布

## 当前焦点

从空工程开始实现 M1，先冻结输入输出、提示词和最小确定性验证，再进入 N2。
