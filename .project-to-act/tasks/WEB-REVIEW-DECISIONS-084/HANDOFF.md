# WEB-REVIEW-DECISIONS-084

已完成：Web 里程碑 C（人工决策提交闭环）。实现 R11 决策提交/历史/补偿闭环 + R08 subject 指定 run 解析最小版，贯通"查看复核项 → 提交决策 → 查看历史 → 解决冲突"流程。人工决策全部追加式，原始 artifacts 与模型输出不可变。

交付内容：

- C1 决策存储（`store.py`）：ReviewDecisionStore 按 run 分目录的追加式 `decision-log.json`；乐观锁 revision、Idempotency-Key 幂等重放（同键同指纹返回已有决策）、同键异请求 409 `decision_key_conflict`、决策指纹（review_id+action+operator+payload SHA-256）、原子写入。
- C2 决策服务（`decisions.py`）：提交前校验 run/review/conflict 存在性、action ∈ {accept, reject, correct, reopen}、correct 必须携带 new_value、reopen 需已有决策可补偿；reviews 视图融合决策状态（pending/decided/open）与 pending_review_count，不改写原始 review 产物。
- C3 HTTP 端点（`app.py`）：`POST /v1/runs/{run_id}/reviews/{review_id}/decisions`（201 创建/200 幂等重放）、`GET .../decisions` 历史查询、`GET /v1/documents/{document_id}/subjects/{subject_id}?run_id=` 指定 run 映射解析（resolved / unmapped_in_run）。
- C4 前端（`ReviewsPage.tsx`）：复核项决策表单（接受/拒绝/纠正/重开）、决策历史时间线、待办/已决策/已重开状态徽章、版本冲突自动刷新提示；API 客户端与类型扩展。

验收（2026-09-05）：

- 后端 311 tests / 19 subtests 全绿（含 `test_webapp_decisions.py` 12 项：存储层 5、服务层 4、HTTP 端点 3，覆盖 subject 指定 run 解析双路径）。
- 前端 `tsc -b && vite build` 通过（56 modules，gzip 104.43 kB）。
- `scripts/c_milestone_smoke.py` 全流程联调通过：决策校验失败关闭（reopen 未决策 422 / correct 缺值 422 / operator 空 422 / review 不存在 404）、幂等重放与同键冲突 409、乐观锁旧 revision 409 `version_conflict`、conflict 目标 correct 决策（target_kind=conflict）、reopen 补偿回 pending 队列、决策历史 append-only 有序（accept→reopen）、决策后 curated run 仍可查询（不可变验证）；subject 解析路径因当前服务器无已发布 subjects 按边界跳过，端点行为由单测覆盖。

边界与待办：真实 provider 全流程实跑（managed registry 发布后的 subject 映射消费）待 DEEPSEEK_API_KEY 环境；R07 召回评测与 R08 完整合并/拆分迁移不在本里程碑；决策补偿目前仅回退队列状态，不改写下游产物（按不可变原则）。
