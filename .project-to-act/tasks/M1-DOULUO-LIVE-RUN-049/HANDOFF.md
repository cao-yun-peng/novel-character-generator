# M1-DOULUO-LIVE-RUN-049

真实运行已完成。源文件为 110,951 bytes / 37,655 Unicode code points；最终采用 2,500 字符窗口、250 字符重叠，共 17 个 Chunk。DeepSeek smoke 返回 HTTP 200；全文首轮完成 16/17，第 3 块因 `max_output_tokens` 截断，随后以 16,384 输出上限断点续跑并完成，最终 17/17 成功。

交付目录为 `runs/m1-douluo-20ch-20260830-v3`。模型输出、grounding、Manifest、逐块 trace、summary 和空失败清单均已保存；API Key 未进入结果、日志或项目账本。当前结论只证明该样本的链路可运行和原文定位门可执行，不代表模型质量已完成人工验收，也不包含跨 Chunk 去重或 M2。
