# WEB-READONLY-BASE-082

已完成：Web 里程碑 A（只读基座）。FastAPI `/v1` 只读服务 + React/TypeScript/Vite 三栏页面贯通 curated run registry 的展示链路。

交付内容：

- 坐标契约：后端 `offset_unit=unicode_codepoint` 半开 span，绑定 `source_document_version_id`；前端 `web/src/lib/offsets.ts` 提供 code point ↔ UTF-16 映射，禁止 JS `slice` 直接消费后端索引。
- 只读服务：run registry（哈希校验加载）、人物列表、状态区间、位置快照、explain、文本窗口、reviews、trace 投影。
- 前端：运行列表 → 人物列表 → 人物详情（原文高亮 + 快照卡 + StateSegment 时间线 + 证据轨迹树）三栏布局，明确区分原始事实与推断设计。

验收：`tests/test_webapp.py` 15 项 + `tests/test_webapp_api.py` 8 项（与 083 共享扩展）；无模型调用。内部可用版本，未对外发布。

注意：本任务在 session 中断前已完成验收但未登记治理文件，083 登记时补录。EVIDENCE 哈希为 083 交付后的最终文件状态。
