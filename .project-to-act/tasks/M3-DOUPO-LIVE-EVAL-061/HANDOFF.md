# M3-DOUPO-LIVE-EVAL-061

已完成。19/19 个 DeepSeek M3 任务最终成功并生成 `document-character-registry.json`。真实联网首轮成功 18 项，1 项因 4096 输出预算截断；提高该次进程预算到 8192 后恢复 18 项并只重试 1 项。最终得到 17 same、2 uncertain、0 different；11 个全局人物、5 linked、6 singleton、2 review、0 unresolved、0 cannot-link。

36 条 grounded identity quote 全部按绝对 span 回放原文；Schema、trace 脱敏和 109 项回归测试通过。本样本最终 linked 组未发现明显错人，但多个 same 的引用只是两处分别出现同名，没有直接跨上下文身份桥接，尚不能证明同名不同人安全。Stage 5、revision 2 和 F-NEW-IDENTITY-006 继续保持 `in_progress`。
