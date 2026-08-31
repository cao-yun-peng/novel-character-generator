# PIPELINE-V3-REVIEW-HARDENING-044

V3 主架构保持不变，但实现基线已加固：exact 使用保守稳定指称策略；N2 派生 mention/evidence 关系与 occurrence；M2/N3 使用 source、fragment、claimed、support 四层 span；N3 以 Chunk 绝对 span 仲裁；pair cache 与 pool hash 分别处理幂等和循环；packet hash 使用原始文本与 span。

开源调研额外确认需要版本化重叠分块和显式 complete/truncated 覆盖清单。别名合并、角色档案、Prompt Compiler、角色母版和视觉验收继续后置，不接入当前 M1-N3。

下一步先实现 DocumentChunkManifest、公共 hash/span 工具与 N2 occurrence 展开，再实现 M1/N2 DTO 和测试。当前没有运行时代码或模型质量结果。
