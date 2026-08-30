# 项目总览

## 基本信息

- 项目：Novel Character Generator
- 阶段：Stage 4/5 边界重构完成，等待 v2 协议迁移实现
- 发布状态：未发布
- 当前实现：M1 v2 shadow 主 Prompt v2.8（用户批准条件 Gate）、Source Match Policy v2、Rubric v2.5、v2.3-draft 短评测与 v2.5-draft 真实 Chunk 评测；N2 v2 `GroundedEvidencePacket` 确定性纵向切片已实现；M2 仍为 legacy v1
- 唯一工作区：`E:\project\agent\novel-cahracter-generator`

## 项目目标

从中文小说中发现角色视觉事实，以逐字原文证据、明确人物归属和安全状态门禁形成可评测的结构化结果。

## 范围

### 包含

- M1 v2 视觉相关连续证据发现
- N2 v2 原文定位、证据哈希和局部上下文固化
- M2 v2 局部语义原子化、载体、字段、认知状态和显式信号
- M3–M5 身份、时间和联合复核设计
- 分节点数据集、评分器与真实模型诊断

### 非目标

- Web API、后台任务系统和数据库持久化
- 向量检索和图像生成
- 未通过质量 Gate 前的 active 事实写入

## 当前焦点

完成 N2 v2 工程 Gate 后迁移 M2 v2 与一次性 M1→N2→M2 shadow 组合；M1 的 005 残余风险由 N2 deferred 安全分流，不得进入 active Observation。三段 Gate 具备证据后再启动 M3。

## 数据与安全边界

真实 Provider 调用需要用户明确授权；密钥不得写入代码、诊断工件或项目账本。模型输出必须通过证据与结构校验，未决结果不能升级为 active 事实。
