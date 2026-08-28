# E-20260828-PIPELINE-V2-M1-013-REAL1

## 结论

M1 首次真实开发基线已完成。Provider/Schema/服务端契约 15/15 一次成功，但测量修正后的模型语义效果为 11 pass / 0 review / 4 fail，M1 模型质量 Gate 不通过；M2 继续关闭。

## 运行边界

- Provider / 模型：`deepseek` / `deepseek-v4-flash`；
- 契约 / Prompt：`local-observation-contract-v1.1` / `local-observation-discovery-prompt-v1.1`；
- 用户授权数据：`m1-local-observation-v1`，15 case，1 repetition；
- 真实 Provider calls / attempts：15 / 15；
- 原始响应捕获：关闭；数据库写入、迁移、Worker/default route 切换：0；
- 首次 sandbox 网络失败只留作环境诊断，不计模型质量，也没有收到 Provider 响应。

## 测量修正

人工逐项复核发现四处测试边界问题：合法 descriptor `红衣少女`、自然命题表达 `红色的衣服`、最小 transformation 引文 `化作`、可安全表示的局部 descriptor `其中一人`。数据集升为 `m1-local-observation-v1.1-draft2` 并回到 `draft_user_review_required`；同一批输出离线重评，额外 Provider 调用为 0。

修正由本轮输出触发，因此该分数只作为开发诊断。当前 15 case 后续只作回归集，Prompt 修复后的独立验收需要新的用户审核 held-out case。

## 真实结果

- Case：11 pass / 0 review / 4 fail；
- required fact：13/15，recall 86.7%；
- supported fact：13/13，precision 100%；
- quote fidelity / epistemic accuracy：100% / 100%；
- temporal signal：1/4 matched，recall 25%，precision 25%；
- unresolved：0 expected、1 actual、0 matched，当前集未验证正向 recall 且存在一次非视觉误报；
- 失败：两个 age fact 遗漏并错绑 signal、一个非视觉 unresolved、一个 presentation→other_state 误分类；
- 延迟：平均 3.04s，P50 3.09s，P95 4.26s，串行墙钟 45.8s；
- Tokens：input 28,948，cache hit 23,296，cache miss 5,652，output 2,749，total 31,697，reasoning 0。

## 工件与哈希

- dataset draft2：`F11195C8288F0E1B7B2AFA5484E1360F50009524D7B7C875779EA21F129F6AE0`；
- saved outputs：`D3FE30CA510665DA26108262207472C9203C9D71164C06360A41BDD2BE3E5914`；
- corrected report：`DB6A6089829ED0A763A6300009CC7003C8E4B87810367DB9151344AD5E3144A6`；
- run metadata：`82DE69B42BB675CF8B948D6B17CF4B94E48FBD9586A366F16340133381813B9C`；
- Prompt：`DE2D528EBDE6EC042CD50A809EC3CED898FC895BC075B2E11536F67145156BFA`；
- evaluator：`5EC4E986C13232A970121641B06A35E28D52A5B5A6C0ED9E5638254BA593FF58`。

## Gate

- engineering gate：passed；
- dataset gate：`v1.1-draft2` pending user review；
- model quality gate：`failed_pending_dataset_review_and_m1_fix`；
- next allowed increment：审核 draft2，最小修复 age/signal、presentation 与 unresolved 边界，补新 held-out；不得启动 M2。
