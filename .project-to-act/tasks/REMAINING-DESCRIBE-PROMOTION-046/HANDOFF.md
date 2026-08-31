# REMAINING-DESCRIBE-PROMOTION-046

M2 现在有两个模式。第一模式由 E 个 exact 分别批量判断全部 D 个 describe。N3 消费已经唯一归属 exact 的片段后，未被任何 exact 认领的 describe 不再回到 exact 循环；每个剩余 describe 单独结合 `chunk_text` 进入 promotion 模式，一个输入池允许输出多个角色。

模型只拆分人物、人物原文标签、认领片段和外貌事实。代码验证不同新人物的 claimed span 不重叠后，为每个人生成独立 `PromotedDescribeCharacterRef`。跨 Chunk 全局 `character_id` 仍由后续人物记忆处理。
