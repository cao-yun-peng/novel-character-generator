# N2-EXACT-PRECEDENCE-053

任务已完成。实现点位于 N2 Grounding 与 mention type 归一之后、最终 packet 输出之前。M1 model output 保持不变；当前 Chunk 全部有效 exact 建立 raw quote 索引，所有 describe scope 删除同文 evidence，空块删除，部分过滤块重算 hash。

策略版本为 `exact-evidence-precedence-v1`；packet v5 顶层显式输出策略版本，hash 输入也包含策略版本。批次升级为 chunk result v3、summary v2，并独立生成 `n2-grounding-traces.json`。运行时升级到 `0.1.0.dev6`，Schema 升级到 `3.6.0-draft1`。

57 项测试、Draft 2020-12 Schema、Project-to-Act、Lifecycle 与 diff 检查通过。斗破已有 M1 输出离线重放显示 94→57 evidence bindings、37→24 grounded mentions，删除 37 条 describe 副本和 13 个空 describe block；Provider 调用 0，旧 runs 未修改。Stage 5 保持 in_progress，未执行 Gate。
