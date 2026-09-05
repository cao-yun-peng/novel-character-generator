# E-20260905-AUTO-SEMANTICS-CONFLICT-080

- 时间：2026-09-05 Asia/Shanghai；runtime dev30，Schema 3.30.0-draft1。
- 完整回归：E:/BaiduNetdiskDownload/miniconda/conda/python.exe -m pytest -q -p no:cacheprovider --tb=short，退出 0；259 tests、19 subtests，5.21 秒。
- 工程回归新增 22 项；事件闭环、active conflict/provisional no-conflict/replacement no-conflict、事件类别、两侧证据、去重/歧义、模型 metadata 隔离、预算/请求预检、重放、Provider 失败和 Schema。
- 代码版本以 source-hashes.json 绑定工作区 SHA-256；既有未提交更改保留，不将 HEAD 视为工作区版本。
- 真实样本 preparation：runs/semantic-dev30/douluo-preparation/manifest.json 与 summary.json；52 任务，Provider 0，complete=false/prepared=true。
- 可控模型工程样例：runs/semantic-dev30/scripted-conflict-regression/automatic-semantics.json；provisional.json=0 conflicts，active-conflict.json=1 true_conflict。4 个 scripted provider 响应，真实 Provider 0。非人工 gold，非模型精度证据。
- compileall、git diff --check、project-to-act --validate 与 manage_lifecycle validate 均退出 0；阶段仍为 6/revision 4。
- 有效期：实现、Prompt、Schema、来源或依赖改变后重验。未通过 Stage 6 人工质量 Gate；未执行真实模型调用或发布。
