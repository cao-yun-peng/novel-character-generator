# M1 Dataset draft 升级与离线重评分交接

## 已完成

- 短集已升级到 v2.3-draft，真实集已升级到 v2.5-draft。
- 已使用 Prompt v2.6 的既有 outputs 离线重评分，没有新 Provider 调用。
- 短集结果为 16/0/0；真实集结果为 2/6/2，硬失败仅 005 与 008。
- 报告与可复验 hash/运行元数据已保存到对应新版本诊断目录。

## 下一步

- 用户复审并批准两套 draft Dataset。
- 批准后冻结测量口径，再针对真实案例 005/008 判断是否需要 Prompt v2.7。
- 在 M1 evidence Gate 通过前，不进入 active Observation，也不重复调用 Provider。
