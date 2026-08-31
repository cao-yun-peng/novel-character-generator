# E-20260830-UPSTREAM-NOVEL-CHARACTERS-043

- 时间：2026-08-30，Asia/Shanghai。
- 用户请求：下载 `eternityspring/shuohao-skills/skills/novel-characters` 到项目中作为对照和参考。
- 上游仓库：`https://github.com/eternityspring/shuohao-skills`。
- 固定提交：`4322897e6d2bdaf66365534fd40194360c75a85f`。
- 本地位置：`references/upstream/shuohao-skills/`。
- 文件数：上游副本 19 个文件；加入本地 `UPSTREAM.md` 后该来源目录共 20 个文件。
- 验证方法：对稀疏克隆的 `skills/novel-characters` 与本地 `novel-characters` 执行目录级 `git diff --no-index --exit-code`。
- 验证结果：退出状态 `0`，Skill 目录无差异；`LICENSE`、`README.md`、`README.en.md` 的 SHA-256 分别匹配。
- 本地来源目录清单 SHA-256：`05c2c2b7f81a9a5e7b9764c543e673e4ee80aee7607cd70fee7d983afe58d1bb`。
- 关键文件 SHA-256：`SKILL.md` 为 `4ea2fbbdfa31cde78da6f038c27e6ec4758efe4bcf322a5099b72dae3d0e4da0`；`novel-characters.mjs` 为 `146cef28dbbe21a2f800de61ca10052cf3d13f79375aaae57c25ce398e15b864`；`selftest.mjs` 为 `f227c41d5a05c9c6af977fe98625b282150e98291c6f15bc76a4b53fe27794af`。
- 项目治理验证：`init_project_management.py --validate` 返回 `valid: true`。
- Provider/模型调用：0；未执行上游脚本。
- 结论：上游参考副本导入完成；它不属于运行时代码，当前 V3 路线和 M1 优先级不变。
- 有效期：直到本地副本或固定上游 commit 变化。
