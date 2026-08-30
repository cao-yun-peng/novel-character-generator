# M1 Prompt v2.8 候选颗粒度修正证据

## 归因

- v2.7 真实运行工件位于 `data/diagnostics/m1-v2.7-real-v2.5-draft/`，真实集结果为 2 pass / 6 review / 2 fail。
- case 005 把两个本地人物的外观谓词合入一个候选并绑定给其中一个 owner，少年脸貌与青衫管家服饰未形成各自的 owner-aligned candidate。
- case 009 召回了连续变形内容，但按身体部位和子句拆成大量小候选；当前复合金标未被完整候选覆盖，同时纯动作候选降低 precision。
- 用户选择继续修改 Prompt，因此本任务固定 Dataset 金标、Rubric v2.5 和 Source Match Policy v2，只改变 Prompt 候选颗粒度。

## Prompt v2.8 修正

- 版本升级为 `visual-evidence-discovery-prompt-v2.8`。
- owner 转换是候选硬边界；一个候选最多包含一个本地人物的外观事实，跨人物句必须拆为各自 owner-aligned candidate。
- 同一人物连续的 appearance profile、transformation 或 presentation-change event 保持一个复合候选，不按身体部位、维度或子句原子化。
- 二次覆盖复扫只检查未覆盖事实；不得为复合候选内已有事实增加重复子候选，也不得把纯动作、纯话语或纯情绪提升为候选。
- 同一描述在不同外观段落重复出现时，各段仍分别保留完整且唯一定位的逐字候选。

## 版本与不可变边界

- 短集仍为 `m1-visual-evidence-short-v2.3-draft`，真实集仍为 `m1-visual-evidence-real-v2.5-draft`；两者只更新被测 Prompt 元数据并注明 v2.8 尚未运行。
- Rubric 保持 `visual-evidence-evaluation-rubric-v2.5`，Source Match Policy 保持 `visual-evidence-source-match-policy-v2`。
- 短集 expected-only SHA-256：`afc8ca6fb036f111a966ca95f48779d557a35ac4fb89a21968da53815e93d5db`。
- 真实集 expected-only SHA-256：`32c4965f3741eb915242be7e479047d9e62aabf26e7883ce56a11d3e5c812142`。
- Prompt 文件 SHA-256：`a52b719959f51e6e15765e1f859fcc06bc120f8166432e25bc08a3d1a046f885`；运行时去除首尾空白后的 SHA-256：`3d0a85a66b3a52c78304556643dd71cea58f873796fee9ff46c5919a16418543`。
- 短集文件 SHA-256：`4877dc3f4a4fdaf95f75305437deb96f2297a2f9bb0b0269ba29494334d399c7`；真实集文件 SHA-256：`1ad18fde6809d6c90296f8324cac1d19e02b5d72462270b64b28864e99d0ce22`。

## 验证

- 真实 Dataset 由构建脚本重建成功：10 cases。
- Prompt/评测定向测试：29 passed。
- 全量测试：89 passed。
- Ruff：passed。
- Mypy：36 source files passed。
- JSON 解析：短集 16 cases、真实集 10 cases，均引用 Prompt v2.8。
- `git diff --check`：passed（仅既有 LF/CRLF warning）。
- Project-to-Act validate：`valid: true`。
- Agent lifecycle validate 仍报告既有 revision 1 账本的旧状态枚举、目录 artifact、revision 单调性问题；本任务未修改 `AGENT_LIFECYCLE.json`，也未据此声称通过 lifecycle Gate。

## 质量边界

- 本任务没有调用外部 Provider，没有产生 v2.8 outputs、分数或 token usage。
- v2.7 保存 outputs 只用于根因归纳，不能作为 v2.8 的效果证据。
- 因此 v2.8 仅通过工程验收，005/009 是否修复以及短集是否无回归必须由新的双集 Provider 运行验证。
