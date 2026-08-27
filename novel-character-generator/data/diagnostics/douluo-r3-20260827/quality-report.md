# 《斗罗大陆》前 20 章真实全链路质量报告

## 结论

本次运行在工程层面成功完成 `导入/切块 → R1 → R2 → R3 → 外观聚合`，但语义质量不通过，当前结果不应直接用于人物定妆或批量生图。

- 工程可运行性：通过
- checkpoint 恢复与幂等续跑：通过
- R1 外观事实质量：部分通过
- R2 人物归属正确性：不通过
- R3 阶段与状态解析：不通过
- 最终画像可直接使用性：不通过

## 运行证据

- source SHA-256：`8bcb7305a759571b1fec70813b0631f2c884eba79697c3259170a7635d639741`
- novel_id：`c8e0d0e0-a9e6-47de-bda6-784a54ec0b63`
- run_id：`ec455a03-9a30-45fe-a7ca-0d2505af7ee9`
- provider/model：`deepseek/deepseek-v4-flash`
- 输入切块：19
- 记录到事件中的 token：输入 198,253，输出 48,380，总计 246,633

token 统计包含开发过程中发生的失败尝试和重试，不能作为修复后的干净成本基线。

## 最终产物概况

| 项目 | 数量 | 评价 |
|---|---:|---|
| 正式人物 | 4 | 唐三、唐昊、素云涛、老杰克 |
| active observations | 59 | 有有效事实，也有错字段、错语义和重复 |
| pending observations | 3 | 均为唐三第 3 Chunk，因时间跳跃未决 |
| temporal signals | 14 | 8 bound、6 unresolved；仅 age/time_jump |
| life phases | 0 | 核心失败项 |
| appearance states | 33 | 过度碎片化，阶段键均为空 |
| render profiles | 4 | 2 draft、2 needs_review，但都缺阶段默认值 |
| conflicts | 5 | 部分是语义近义而非真正冲突 |

## R1 检查

正确样例包括：唐昊的高大魁梧、破损袍子、古铜色皮肤和胡须；老杰克的年龄、瘦长身材和整洁穿着；素云涛的白色劲装、黑色披风和徽章。

主要问题：

1. `二十六级` 被标成 age signal，实际是魂力等级。
2. 素云涛武魂附体后的绿色眼睛、变长灰发、肌肉膨胀和狼爪没有 transformation signal，被当成常驻基础外观；最终 identity anchor 甚至选中了武魂附体后的膨胀肌肉。
3. 狼爪被分别写进 `distinctive_marks.scar` 和 `clothing.coverage`，青光被写成 `clothing.color=青色`。
4. 唐三的“稚嫩小手”写入不存在明确语义的 `face.hands`。
5. 唐三的 `破破烂烂/邋遢` 等 clothing.condition 存在上下文归属或语义误判。
6. 存在 7 组同人物、同章节、同字段、同值的重复结果；其中 4 组来自同一 run 的 resolver v1.2/v1.3 混合产物。

## R2 检查

最终 convergence memory 共 9 条：stable 3、provisional 3、unresolved 3；对应 mention 数分别为 14、36、3。

核心失败是唐三和唐昊发生实体污染：

- stable 的“唐三”记录同时包含 `唐三/唐昊` 两个名字及双方证据。
- 3 条 provisional 记录均绑定到唐三 character_id，却同时包含 `唐三/唐昊` 名称和双方 mention。
- 正式人物表虽然已经存在唐昊，但最终 stable memory 中没有唐昊记录。

这说明 R2 当前不能可靠完成“把 R1 字段归属给正确人物”。本次 run 之后的 R3 和聚合结果虽然能够落库，但其人物归属可信度已经受损。

另外 3 个未决实体是：男孩子、女孩子、大师；低证据时保持未决是正确的 fail-close 行为。

## R3 检查

R3 没有生成任何 life phase。唐三第 0 Chunk 的前世成年状态和第 1 Chunk 之后的六岁状态均落在 `scope_type=unknown`，没有被分成“前世成年/今生幼年”等阶段。

原因表现为：

1. R1 只产出了 age/time_jump，没有产出 life_phase/transformation。
2. 当前 R3 不会从可信 age signal 推导阶段。
3. `十一天过去` 导致唐三第 3 Chunk 的年龄、身体变结实和稚嫩小手全部进入 needs_review，未形成连续阶段。
4. 未识别武魂附体/解除，导致暂态外观不能与基础外观分离。

## 聚合检查

- 唐昊和老杰克的主要身份锚点基本可读。
- 素云涛的默认身份锚点被错误设置为武魂附体后的肌肉膨胀状态。
- 唐三的成年前世、幼年今生、表情、衣着被拆成多个无阶段状态，无法选择稳定默认形象。
- 5 个冲突中，`干净/朴素`、`暗黄色/蜡黄色`、`目光呆滞昏黄/睡眼朦胧` 更接近可合并描述，不应全部要求人工冲突处理。

## 下一轮应达到的验收门槛

1. R2：显式姓名不得跨人物合并；唐三/唐昊污染为 0；最终 stable memory 覆盖全部正式人物。
2. R1：过滤等级类伪年龄；武魂附体必须产出 transformation signal；字段路径必须通过白名单和语义校验。
3. R3：可由 age + reincarnation/time-jump 形成阶段；唐三至少分离前世成年与今生幼年；素云涛至少分离基础态与武魂附体暂态。
4. 聚合：同 run 同事实去重；近义值归一化后再冲突检测；默认 identity anchor 不得取暂态变身特征。
5. 重新用相同 source hash 跑一次全新 run；不得复用本次已污染的 convergence memory，并另测干净 token/调用成本。
