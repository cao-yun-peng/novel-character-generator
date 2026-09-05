# 075 人工质量评测协议：第一版候选

版本：annotation-protocol-v1-draft。日期：2026-09-05。对应 R06；本协议和自动回归准备不代表人工标注集或质量 Gate 已完成。

## 1. 数据与隔离

- 每个样本绑定 sample_id、document_version_id、原文 hash、半开 code-point span、layer、split、error_tags。
- 按作品及连续章节分组拆分 development / heldout；重叠 Chunk、同段改写和同人物连续事件不能跨拆分泄漏。小数据不能伪称跨作品一般化。
- 合成反例单列 synthetic_regression，只用于工程回归，不能混入人工 heldout 准确率。
- 两位标注者先独立标注，再由裁决者解决差异；记录各自判断和裁决来源。人员不足时保留 pending，不由模型伪造第二位标注者。
- 初始标注查看原文和标注规则，不以模型答案为锚点；复核阶段才对照模型与 Grounding 结果。
- gold 标签不进入运行时检索、M3 候选生成或模型输入。原始标注、裁决结果与预测分开存放。

## 2. 最小标注记录

每条记录包含：

    sample_id / source_document_version_id / source_hash
    source_span {start, end} / offset_unit=unicode_codepoint
    layer / split / error_tags
    annotations [{annotator_id, decision, evidence_spans, created_at}]
    adjudication {status, adjudicator_id, decision, reason, protocol_version}

status 至少区分 pending / independently_annotated / adjudicated / excluded。excluded 必须有理由并在报告保留计数；未裁决样本不得进入 gold 指标。不存在统一“grounded=true 即正确”的标签。

## 3. 逐层标注与指标

| 层 | 标注对象 | 独立报告指标 |
|---|---|---|
| M1 | 提及文本、exact/describe/null、individual/collective、支持 evidence span；原文存在但漏抽的提及也记录 | mention/evidence precision、recall、类型/范围正确率、Grounding 率 |
| M2 | 事实原文位置、category/attribute/value、所属人物；同原文多 occurrence 分别标注 | 事实 precision/recall、属性值正确率、人物归属正确率、歧义处理正确率 |
| N3/promotion | 可消费位置、多个 exact 冲突、未分配残片、应建立的人物及保留事实 | 错消费/漏消费、建人 precision/recall、事实保留率与错误隔离率 |
| identity | gold 人物簇、局部节点、same/different/uncertain 及支持关系原文 | candidate recall@K、MRR、false merge/split；未召回、被截断、未裁决、错裁决分开 |
| state/transition | 人物、维度、原文变化、有效边界、连续性与未知情况 | 事件 precision/recall、人物绑定与边界正确率、错误延续/提前失效 |
| relation | 属性/部位/状态限定、equivalent/compatible/unclassified 或有依据的不兼容 | 各类别 precision/recall、否定/部分/跨状态误判；不以 unclassified 下降为成功 |
| snapshot | 固定人物、run 与原文位置下的 active/provisional/不适用事实，覆盖及冲突原因 | trait precision/recall、active 误升级率、未来泄漏、跨状态混合、来源回放 |

精确 span 匹配与边界容差指标分开；容差规则必须在评分前固定，不因模型输出调整。零分母标记 not_applicable 并报告分母，不写成 100%。空事实人物和无候选节点不得从分母中静默删除。

## 4. 首批必选错误切片

1. 同一事实原文在一个 evidence 内出现两次；跨生命阶段各出现一次。
2. 多个 evidence 窗口覆盖同一人物、同一绝对事实位置。
3. 同一句原文被两个 describe 候选支持，人物归属不唯一。
4. 高大/不高大、黑色/不是黑色、无/未/非/没否定；不但等保守拒绝样例。
5. 换模型/Prompt/Schema 后误用缓存；仅 Grounding 策略改变时离线重放。
6. 跨段与连续跨章衣着延续、换地点不换衣、叠穿、局部替换、脱衣。
7. 时间跳跃、转生、附体进入/退出、没有退出证据的状态。
8. 同名不同人、远距离别名、泛称、候选预算截断、零事实节点。
9. 浏览器 emoji/扩展汉字/CRLF 坐标与重复 quote 高亮。

077 已将前四类中的可确定反例纳入 tests；其标签是合成工程预期，不是人工 gold。真实标注应覆盖至少两个作品的代表性切片；现有两部节选只能作起始来源，不能声称完整长篇验证。

## 5. Evaluator 与 Gate

后续 evaluator 必须绑定 protocol/dataset/model/prompt/schema/policy 与精确 artifact_set 版本，输出：

- 样本总数、参与评分/待裁决/排除数量及分层分母；
- 每层、每种错误类型的 TP/FP/FN 或适用的分类计数；
- 包含 sample_id、原文 span、预测、gold、差异与来源引用的 error list；
- 候选召回与最终身份质量、程序成功率与模型质量分别报告；
- 需要新增调用的实验预算、实际调用数与已保存输出重放数。

先在 development 上建立 baseline，再在不查看 heldout 结果的条件下确定正式阈值与样本量。无阈值、样本未裁决、版本不匹配或某必测层缺数据时，Gate 返回 not_ready，不能默认通过。075 的人工标注与正式 evaluator 仍待后续切片完成。
