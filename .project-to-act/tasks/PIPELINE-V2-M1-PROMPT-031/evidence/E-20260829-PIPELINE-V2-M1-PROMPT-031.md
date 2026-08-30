# E-20260829-PIPELINE-V2-M1-PROMPT-031

## 失败归因

- 005 的 `青衫老者` 在 Chunk 中出现两次；模型虽建立 owner，却没有让 evidence quote 自身唯一，触发 deterministic validation failure。
- 005 的月白衣袍外貌停在眼睛载体处，未覆盖后续转折视觉谓语；同 case 还漏掉嵌在观察短语中的少年年龄感脸貌。
- 008 的输出全部逐字且唯一，铁鞋、年龄发辫和金环均命中，但漏掉动作/对话结构中的独立虎牙线索；另一条牙齿/嘴唇视觉证据不能替代该线索。
- 以上属于 Prompt/模型覆盖与边界构造问题，不再归因于 Dataset alias、Rubric 或 Source Match Policy。

## Prompt v2.7 修正

- Prompt 版本升级为 `visual-evidence-discovery-prompt-v2.7`。
- 固化两阶段引文构造：先保留完整 subject-to-predicate 视觉语义及并列/转折/限定延续，再扩展到 evidence quote 在整个 Chunk 中恰好出现一次。
- 明确 owner mention 或 owner_index 不能弥补重复 evidence quote。
- 增加返回前的逐子句全 Chunk 覆盖复扫，不因同一人物已有候选而停止；专门检查观察、动作、对话结构中的年龄感、脸、眼睛、牙齿、疤痕、酒窝、头发、发辫、服饰和配饰短线索。
- 明确不同视觉线索不可互相替代。
- Prompt 文件 SHA-256：`e862fe79027d009ecb559b68905454b55450d069280cddd94ddd0bdceadd4ea4`；运行时 Prompt SHA-256：`b34d45b9193b002640733de21846d5119537ca34175a2a6c0dbde89967ff3cb5`。

## 契约与数据边界

- 模型 wire Schema、Dataset 版本、review status、金标 owner/candidate/span、Rubric v2.5 和 Source Match Policy v2 均未改变。
- 两套 Dataset 仅把被测 Prompt 元数据更新为 v2.7，并明确 v2.7 尚未运行：短集 SHA-256 `174fec6f05363f2bf001cfc13aed5acfa688143d5a3fd5f9d386e99f1826ddda`；真实集 SHA-256 `c08440ad746b9dcc2a809ad762cdffc276bca7ec404139d429fdc66e6c13af08`。
- v2.6 的 16/0/0 与 2/6/2 只保留为历史基线，不使用旧 outputs 评价 v2.7。
- 本任务未调用 Provider、未写数据库、未产生 active Observation。

## 工程验证

- 真实 Dataset 生成器：重建 10 cases，退出 0。
- Prompt 与评测契约定向测试：29 passed。
- 全量 Pytest：89 passed。
- Ruff：通过。
- Mypy：`src scripts` 共 36 source files 无问题。
- `git diff --check`：通过（见任务完成时复验）。
- Project-to-Act validate：通过（见任务完成时复验）。
- `AGENT_LIFECYCLE.json` 的既有 revision 1/current stage 5 历史问题未由本任务修改，本任务只完成工程任务，不宣称 Prompt 质量 Gate 或 lifecycle Gate 通过。
