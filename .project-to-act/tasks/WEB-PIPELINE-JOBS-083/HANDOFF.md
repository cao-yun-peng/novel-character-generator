# WEB-PIPELINE-JOBS-083

已完成：Web 里程碑 B（异步任务与流水线执行）。实现 R09 任务管理核心 + R08 subject 映射基础，贯通"导入小说 → 启动/恢复解析 → 查看任务进度"流程。

交付内容：

- B1 存储层（`store.py`）：DocumentStore（不可变版本、内容寻址）、JobStore（原子写入、事件日志、阶段状态快照）、SubjectIndex（document 级稳定 subject_id，run 发布时建立 character 映射）。
- B2 流水线执行器（`pipeline.py`）：M1→M2→N3→证据聚合→身份裁决→簇救援→本地共指闭包→事实分组→外貌范围→状态转换→标签投影 12 阶段串联；阶段前与进度回调中检查协作式取消；成功后发布产物到 managed registry 并登记 subjects。
- B3 任务服务（`jobs.py`）：线程 worker、幂等键（同键同请求返回已有任务、异请求 409）、cancel/resume、事件游标 `after`、启动时重置遗留 running 状态实现重启恢复。
- B4 HTTP 端点（`app.py`）：`POST /v1/documents`（幂等上传/201/200）、versions、text window、`POST /v1/documents/{id}/runs`（202）、jobs 列表/详情/事件、cancel、resume、subjects；RunRepository 运行时 reload 合并 curated 与 managed 双注册表。
- B5 前端：文档导入页、文档库/详情页、任务详情页（阶段进度 + 事件流 + 取消/恢复按钮）；API 客户端扩展。

验收（2026-09-05）：

- 后端 275 tests / 19 subtests 全绿（含 `test_webapp_jobs.py` 16 项、`test_webapp_api.py` 8 项）。
- 前端 `tsc -b && vite build` 通过（56 modules，gzip 102.85 kB）。
- `scripts/b_milestone_smoke.py` 全流程联调通过：38,251 cp 斗罗原文导入（幂等重放）、unicode_codepoint 文本窗口逐字回放、任务 202/重复提交 409、无 API key 时 m1 阶段 `provider_unconfigured` 失败、事件序列 job_created→job_running→stage_started→stage_failed→job_failed 完整、resume 后同断点重试、subjects 发布前为空、curated run `douluo-20ch-dev13` 共存不受影响。

边界与待办：真实 provider 解析链路（含 managed registry 发布后的 subject 映射消费）待 DEEPSEEK_API_KEY 环境实跑验证；人工决策提交（R11 复核闭环）与 SSE 属里程碑 C 范围。
