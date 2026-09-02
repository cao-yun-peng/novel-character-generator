# DOCUMENT-CHARACTER-PROFILES-062

已完成。新增 `document-character-profiles-v1`、`strict-fact-hash-profile-join-v1`、确定性构建函数和 `build-document-character-profiles` CLI。构建器验证同文档身份、完整事实 hash、Chunk hash、事实/evidence span、引用完整性和单一人物占用；零事实人物、未绑定事实、冲突、review 与 cannot-link 均保留。

斗破既有 registry/evidence 离线组装得到 11 个全局人物、61/61 已分配事实、62 个来源 occurrence、0 未绑定事实、4 个可能冲突、2 个 review。118 项测试、Draft 2020-12 实例 Schema、61/61 事实和 62/62 evidence/Chunk 回放、diff check、治理与 Lifecycle 验证通过。Provider calls=0。Stage 5 保持 `in_progress`，revision 2。
