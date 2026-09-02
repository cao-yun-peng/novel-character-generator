# 斗罗 M3 残余 cluster-level DeepSeek 实跑证据

- 证据 ID：`E-20260901-M3-IDENTITY-RESCUE-LIVE-065`
- 日期：2026-09-01
- runtime/schema：`0.1.0.dev15` / `3.15.0-draft1`
- 输入：`tests/小说/斗罗大陆前20章.txt`
- 来源：`runs/douluo-20ch-e2e-dev13-20260831/identity`
- 输出：`runs/douluo-20ch-e2e-dev13-20260831/identity-rescue-live-dev15`
- 有效期：直到模型、Prompt、Schema、关系上下文策略或输入文档变化

## 执行结果

- 受限网络预尝试：5/5 `ProviderTransientError`，无成功 HTTP；失败保存在追加式 run history。
- 允许联网后：5/5 HTTP 200，4 `same_character`、1 `different_characters`、0 uncertain、0 Grounding issue。
- 运行时间约 53.3 秒；输入 17,656 tokens（其中 cached 1,920）、输出 5,813、reasoning 5,416、总计 23,469。
- 第二次运行：5/5 从任务缓存恢复，新增 Provider 调用 0。

## 裁决摘要

1. 唐三→唐三：same/same_surface，原文明确“眼前的这个孩子，正是当初……的唐三”及今世仍名唐三。
2. 唐三→唐三：same/same_surface，同一转生和取名关系原文。
3. 小三→唐三：same/name_variant，唐昊先称“小三”且下一句直接出现唐三。
4. 素云涛→战魂大师/年轻人/青年：same/name_variant，“年轻人微笑道：我叫素云涛”。
5. 男孩儿→唐三：different，前述孩子没有魂力，而唐三为先天满魂力。

## Grounding 验证

- grounded decisions：5
- grounded identity evidence：8
- 文档绝对 span 逐字回放：8/8
- 所选候选 `relationship_context_quotes` 证据域匹配：8/8
- 非所选/普通 context 取证：0
- Grounding errors/issues：0

## 注册表变化与缺口

- global characters：12 → 9
- unresolved：3 → 2
- review：13 → 12
- cannot-link：1 → 2
- appearance fact refs：129 → 129

仍有两个确定性后处理缺口，不归因于本次模型输出：

1. 唐三候选簇生成了反向重复任务；单轮同边合并后仍保留两个唐三全局簇，需要候选图规范化或迭代到固定点。
2. 男孩儿→唐三的 different 已安全形成 cannot-link，但原 base uncertain 仍被 unresolved 统计，需要 supplemental decisive relation 覆盖相同关系的旧 uncertain 状态。

因此本次真实调用与证据域 Gate 通过；“所有可解决残余均被最终关闭”的聚合 Gate 未通过，需后续确定性修复。

## 工件哈希

- `cluster-rescue-model-outputs.json`：`fb6d6e60e72494f84bb7a572356fd09f2df159973e28ca795f345788a1f0b9fc`
- `grounded-cluster-rescue-decisions.json`：`14f8516c8c4cfd44db60af0b252e6dec4c0878bd1337e26fa8bbde7861bc6599`
- `document-character-registry.json`：`f48930bb0b02ff08519ca3c9f0e2ebd16c116116ceb714fd286e9d2fc4c12cf4`
- `provider-traces.json`：`1fb27e97eed156b045c912539a113e35ca41653dd6574114df1dc0f156e01858`
- `run-history.json`：`93c48838f9773518f357e9386f881906a34fcf087954cbdd3a734c83d208ecd5`
