# E-20260905-SNAPSHOT-APPLICABILITY-079

- 时间：2026-09-05，Asia/Shanghai；runtime 0.1.0.dev29，Schema 3.29.0-draft1。
- 代码版本：工作区含用户既有未提交修改，采用同目录 source-hashes.json 的 SHA-256 绑定实际实现和测试，不用 HEAD 代替工作区。
- 完整回归：`E:/BaiduNetdiskDownload/miniconda/conda/python.exe -m pytest -q -p no:cacheprovider --tb=short`；退出 0；237 passed、19 subtests passed，3.66 秒。
- 新增 26 项 Snapshot 测试，包括衣着独立延续、瞬时过期、同位置顺序、显式关闭、形态恢复、观察/事件引用、Schema、CLI 和旧 API 投影一致性。
- 真实回放：`E:/BaiduNetdiskDownload/miniconda/conda/python.exe .project-to-act/tasks/SNAPSHOT-APPLICABILITY-079/verify_real.py`；退出 0；4 张快照、7 active、42 provisional、71 excluded bindings，Provider 0。
- 确定性：同输入重复构建相等；再次运行脚本只比较保存结果而不覆盖，退出 0。
- 新旧 Schema：真实 CharacterSnapshot、当前 render profiles、历史 dev26 profile 均通过 Draft 2020-12 验证；机器 Schema 本身验证通过。
- 原始输入：6 个源文件 SHA-256 前后不变，完整清单在 runs/douluo-20ch-e2e-dev13-20260831/snapshots-dev29/summary.json。
- 保存快照 SHA-256：87f01d10a19285e1b2edc088d22037e3adaff015eaacb711a332f886d163313d。
- 结果位置：runs/douluo-20ch-e2e-dev13-20260831/snapshots-dev29/；查询和事件契约见 docs/40-character-snapshot-and-applicability.md。
- 有效期：实现、来源、策略或依赖改变后重验；此证据只用于 079 基础切片，不代表 R03 自动语义发现、R02 全冲突或 Stage 6 人工质量 Gate 通过。
- 迁移限制：使用历史 dev18 facts，仅确定性重建保存状态的 relation projection；没有宣称 dev27 M2 修复已贯穿所有下游。

- 附加检查：compileall、git diff --check、文档链接及 source-hashes 一致性检查通过；project-to-act --validate 返回 valid=true、issues=[]。
