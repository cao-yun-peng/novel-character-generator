# R1-GOLD-FIX-011 Handoff

- 状态：完成。
- 黄金：默认 seed 升级为 dataset `v1.1` / rubric `visual-observation-seed-v3.1`；31 case、40 required、5 allowed、3 allowed deferred、17 forbidden。真实审计为 6 slice、14 required、11 forbidden。
- 评分：支持受控 owner/surface alias、raw grounded mention 前评分、temporal 窄包含与去重；asserted/deferred 同引文双写为硬失败；无关同字段事实不能遮蔽缺失。
- 离线重评：`report-rescored-v1.1.json`，0 次 Provider 调用。A seed 20/1/10，B seed 22/1/8；B real 2/0/4。
- 决策：v2.6 仍不切换。下一步修 coverage、earring alias、disguise 映射、估龄排他门禁和剩余 Prompt 召回。
