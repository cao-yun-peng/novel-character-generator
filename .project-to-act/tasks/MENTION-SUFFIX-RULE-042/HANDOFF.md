# MENTION-SUFFIX-RULE-042

`红衣女子` 等提及使用版本化后缀表归一为 describe。通配符 `*女子` 在实现中表示 `endswith("女子")`。

匹配顺序为 null、最小明确名称 exact、泛称后缀 describe、其余语义分类。N2 如果用后缀规则修正 M1 类型，只写归一 trace，不删除该块 evidence。
