# 《斗罗大陆》前 20 章干净 Run 质量复测

## 结论

- 工程链路通过：新建隔离数据库与产物目录，19/19 Chunk 完成，R1、R2、R3、聚合四步均 `succeeded`。
- R2 显式姓名门禁通过本次样本：唐三、唐昊、素云涛、老杰克各自只绑定自己的显式姓名；没有复现旧 run 的唐三/唐昊跨人物合并。
- 伪年龄门禁通过本次样本：没有出现 `二十六级` 等等级值作为年龄；唐三二十九岁、五六岁，唐昊接近五十岁等显式年龄均保留。
- R3 核心阶段推导通过：唐三生成 `past_life → reincarnated_childhood`，唐昊生成 `age_adulthood`，总计 3 个阶段。
- 同事实精确重复为 0；115 个视觉候选中 112 个通过定位，定位接受率 97.4%。
- 总体语义 Gate 仍为 `review`：真实 run 暴露出少量跨字段语义与 transformation 作用域问题；这些问题已在 run 后修复并加入确定性测试，但尚未再次付费全量复测。

## 运行标识

- source sha256：`8bcb7305a759571b1fec70813b0631f2c884eba79697c3259170a7635d639741`
- novel：`71e10a63-8e73-4904-bdb5-fff5d5b9dac7`
- run：`1bf78020-a912-4dae-be3a-7b41fc904b0b`
- Provider：`deepseek/deepseek-v4-flash`
- 版本：`visual-observation-v3.2`、`visual-extraction-prompt-v2.4`、`entity-resolution-prompt-v1.4`

## 主要计数

| 项目 | 结果 |
|---|---:|
| Chunk | 19 |
| 人物 | 5 |
| active / pending observations | 74 / 0 |
| temporal signals | 16 |
| life phases | 3 |
| appearance states | 29 |
| render profiles | 5 |
| run 当时 conflicts | 5 |
| 记录 Token | 229,840 |

## 真实 Run 暴露的问题与后续修复

1. `face.eye_color` 曾错误接收“黑色短发”和“闪亮目光”。后续加入眼部证据与颜色维度校验：无眼部证据拒绝，只有眼神状态时归到 `face.eyes`。
2. `face.hands`、`age.age_stage` 等错层路径仍可从 Provider 输出。后续加入通用安全归位到 `body.hands`、`age_stage`。
3. `accessories.gloves=狼爪` 属于身体形态而非手套。后续按爪类证据归到 `distinctive_marks.claws`。
4. mention 级 `武魂附体` 曾覆盖同一 Chunk 的年龄、衣服、徽章和变身前黑发，导致 transformation 假冲突。后续改为只关联信号后方、且事实自身明确描述变化/形态的观察；年龄和静态基线不会被附体信号污染。
5. R3 原先把同一阶段内所有事实的起点压到阶段起点，造成“瘦小→结实”等正常变化冲突。后续保留每条 Observation 的实际章节起点，阶段只提供归属与上界。
6. 同时佩戴的多个同类配饰不再被视为互斥值，而以多值列表聚合。

## 验证

- Pytest：157 passed。
- Ruff：`src` 与 `tests` 全仓通过。
- Mypy：115 个源码文件通过。
- Run Inspector：本地浏览器实测 R1 trace、候选、定位事实、时间信号、警告和折叠 JSON；宽/窄布局可读，控制台无 error/warning。

## 下一 Gate

不建议把本报告直接视为最终跨作品质量通过。下一次真实复测需要确认：本报告列出的 6 类后续修复在新 run 中生效、5 个旧假冲突显著下降、素云涛的基础外观与附体形态完全分离，并抽查第 18 个 Chunk 的唐三/大师字段归属。
