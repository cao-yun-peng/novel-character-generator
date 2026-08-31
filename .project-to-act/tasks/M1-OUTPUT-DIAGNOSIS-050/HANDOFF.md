# M1-OUTPUT-DIAGNOSIS-050

只读诊断已完成。事实源为 `runs/m1-douluo-20ch-20260830-v3`；报告见 `evidence/E-20260830-M1-OUTPUT-DIAGNOSIS-050.md`。

结论不是“再给 Prompt 加几句话”，而是先修输入覆盖、运行审计、逐字 quote 的安全恢复和 occurrence 绑定，再建立人工标注回归集；之后才用小切片分别比较 Prompt、reasoning effort、分章 Chunk 和模型。上游 `novel-characters` 的两趟扫描、别名归并候选、人工复核、逐字校验和断点续跑值得吸收；其自由文本 note 与推断不能进入 V3 的 grounded 事实层。

本轮没有修改实现、Prompt、Schema 或真实运行结果，没有再次调用模型，也没有推进 Lifecycle Gate。
